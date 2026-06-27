"""
Planner Agent — Node (F1 Stage 5)

LLM-driven strategy generator. Reads the day's regime / economic /
market-pulse / news context from state and emits a per-horizon playbook
that drives Discovery Stage 8 and the F2 Decision agent.

Authority: the LLM decides EVERYTHING — agent weights, discovery filters,
sector tilts, conviction thresholds, AND which horizons are active today.

Retry strategy: PRO → PRO → PRO (3 attempts with 3s spacing).
There is NO rules-based fallback — if all retries fail, the pipeline
fails. This is by design: a degraded rule-based plan can mask broken
upstream context and produce silently-wrong recommendations.
"""

import json
import re
import time
from langchain_core.messages import HumanMessage

from app.agents.state import AnalysisState
from app.agents.planner.prompts import PLANNER_PROMPT
from app.core.model_router import get_model, ModelTier
from app.core.llm import extract_content
from app.core.config import logger
from app.services.failure_log import log_failure


_VALID_HORIZONS = ("SHORT", "MID", "LONG")
_VALID_RISK = {
    "AGGRESSIVE",
    "MODERATE",
    "BALANCED",
    "DEFENSIVE",
    "CONSERVATIVE",
    "FORTRESS",
}
_VALID_CAUTION = {"NORMAL", "CAUTIOUS", "ELEVATED", "CRISIS"}
_CAUTION_ORDER = ["NORMAL", "CAUTIOUS", "ELEVATED", "CRISIS"]

# Retry chain — same tier (PRO) on all attempts; user wants LLM-only, quality-first.
_TIER_CHAIN = [ModelTier.PRO, ModelTier.PRO, ModelTier.PRO]
_RETRY_DELAY_SECS = 3


def _is_retryable(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(
        code in msg
        for code in (
            "503",
            "429",
            "unavailable",
            "overloaded",
            "resource_exhausted",
            "high demand",
            "timeout",
            "deadline",
        )
    )


def _parse_planner_json(raw: str) -> dict:
    """Extract JSON from the LLM response — strip code fences, slice braces."""
    text = (raw or "").strip()
    if text.startswith("```"):
        lines = [l for l in text.split("\n") if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    candidates = [text]
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last != -1 and last > first:
        candidates.append(text[first : last + 1])

    for cand in candidates:
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            try:
                cleaned = re.sub(r",(\s*[}\]])", r"\1", cand)
                return json.loads(cleaned)
            except json.JSONDecodeError:
                continue

    raise ValueError(
        f"Planner LLM returned unparseable JSON (len={len(raw)}): {raw[:300]!r}"
    )


def _validate_plan(plan: dict) -> None:
    """Raise ValueError on shape or semantic violations. Retry will trigger."""
    if not isinstance(plan, dict):
        raise ValueError(f"Plan is not a dict: {type(plan).__name__}")

    active = plan.get("active_horizons")
    if not isinstance(active, list) or not active:
        raise ValueError(f"active_horizons missing or empty: {active!r}")
    for h in active:
        if h not in _VALID_HORIZONS:
            raise ValueError(f"active_horizons contains invalid horizon: {h!r}")

    overall_caution = plan.get("overall_caution", "NORMAL")
    if overall_caution not in _VALID_CAUTION:
        raise ValueError(f"overall_caution invalid: {overall_caution!r}")

    for h in _VALID_HORIZONS:
        block = plan.get(h)
        if h in active:
            if not isinstance(block, dict):
                raise ValueError(
                    f"Horizon {h} is in active_horizons but its block is missing or not a dict"
                )
            if not block.get("active", False):
                raise ValueError(
                    f"Horizon {h} is in active_horizons but block.active is false"
                )

            weights = block.get("agent_weights") or {}
            for key in ("technical", "fundamental", "sentiment", "chart_pattern"):
                if key not in weights:
                    raise ValueError(f"{h}.agent_weights missing '{key}'")
            wsum = sum(
                float(weights[k])
                for k in ("technical", "fundamental", "sentiment", "chart_pattern")
            )
            if not (0.99 <= wsum <= 1.01):
                raise ValueError(
                    f"{h}.agent_weights sum to {wsum:.3f}, must be 1.0 (±0.01)"
                )

            rt = block.get("risk_tolerance")
            if rt not in _VALID_RISK:
                raise ValueError(f"{h}.risk_tolerance invalid: {rt!r}")
            cl = block.get("caution_level")
            if cl not in _VALID_CAUTION:
                raise ValueError(f"{h}.caution_level invalid: {cl!r}")

            mc = block.get("min_conviction")
            try:
                mc_f = float(mc)
            except (TypeError, ValueError):
                raise ValueError(f"{h}.min_conviction not numeric: {mc!r}")
            if not (40 <= mc_f <= 80):
                raise ValueError(f"{h}.min_conviction out of range [40,80]: {mc_f}")

            mp = block.get("max_positions")
            try:
                mp_i = int(mp)
            except (TypeError, ValueError):
                raise ValueError(f"{h}.max_positions not numeric: {mp!r}")
            if not (1 <= mp_i <= 20):
                raise ValueError(f"{h}.max_positions out of range [1,20]: {mp_i}")

            if not isinstance(block.get("discovery_filters", {}), dict):
                raise ValueError(f"{h}.discovery_filters must be a dict")
            if not isinstance(block.get("preferred_sectors", []), list):
                raise ValueError(f"{h}.preferred_sectors must be a list")
            if not isinstance(block.get("avoid_sectors", []), list):
                raise ValueError(f"{h}.avoid_sectors must be a list")
        else:
            # Not active — force-clear the block so downstream stages skip it.
            plan[h] = {}


def _add_legacy_flat_weights(plan: dict) -> None:
    """Decision agent reads top-level technical_weight / fundamental_weight / ...
    as a fallback path. Populate them from the first active horizon's weights."""
    active = plan.get("active_horizons", [])
    default_block = next(
        (
            plan[h]
            for h in ("MID", "LONG", "SHORT")
            if h in active
            and isinstance(plan.get(h), dict)
            and plan[h].get("agent_weights")
        ),
        None,
    )
    if default_block:
        w = default_block["agent_weights"]
        plan["technical_weight"] = float(w.get("technical", 0.30))
        plan["fundamental_weight"] = float(w.get("fundamental", 0.30))
        plan["sentiment_weight"] = float(w.get("sentiment", 0.25))
        plan["chart_pattern_weight"] = float(w.get("chart_pattern", 0.15))
        plan["discovery_filters"] = default_block.get("discovery_filters", {})
    else:
        plan["technical_weight"] = 0.30
        plan["fundamental_weight"] = 0.30
        plan["sentiment_weight"] = 0.25
        plan["chart_pattern_weight"] = 0.15
        plan["discovery_filters"] = {}


import datetime

_daily_cache = {}


def planner_node(state: AnalysisState) -> dict:
    logger.info(
        "[bold cyan]>>> Planner Agent (LLM): Building per-horizon strategy...[/bold cyan]"
    )
    start_time = time.time()
    errors: list[str] = []

    today = str(datetime.date.today())
    if today in _daily_cache:
        logger.info(f"[dim]>>> Planner Agent: Using cached data for {today}...[/dim]")
        return dict(_daily_cache[today])

    regime = (state.get("macro_regime") or "SIDEWAYS").upper()
    valid_regimes = {"BULL", "SIDEWAYS", "BEAR", "CRISIS", "VOLATILE"}
    if regime not in valid_regimes:
        regime = "SIDEWAYS"

    prompt = PLANNER_PROMPT.format(
        macro_regime=regime,
        macro_confidence=state.get("macro_confidence", "unknown"),
        economic_regime=state.get("economic_regime", "STABLE"),
        economic_score=state.get("economic_score", 50),
        overweight_sectors=state.get("overweight_sectors", []) or [],
        underweight_sectors=state.get("underweight_sectors", []) or [],
        economic_positives=state.get("economic_positives", []) or [],
        economic_risks=state.get("economic_risks", []) or [],
        market_pulse_score=state.get("market_pulse_score", 50),
        india_vix=state.get("india_vix", "unknown"),
        ad_ratio=state.get("advance_decline_ratio", "unknown"),
        breadth_signal=state.get("breadth_signal", "unknown"),
        market_health=state.get("market_health", "unknown"),
        market_sentiment=state.get("market_sentiment", 0.0),
        hot_sectors=state.get("hot_sectors", []) or [],
        avoid_sectors=state.get("avoid_sectors", []) or [],
        anomaly_alerts=state.get("anomaly_alerts", []) or [],
    )

    last_error: Exception | None = None
    for attempt, tier in enumerate(_TIER_CHAIN):
        try:
            if attempt > 0:
                logger.warning(
                    f"[yellow]Planner: attempt {attempt + 1}/{len(_TIER_CHAIN)} "
                    f"using {tier.value} (previous: {last_error})[/yellow]"
                )
                time.sleep(_RETRY_DELAY_SECS)

            llm = get_model(tier, json_mode=True)
            response = llm.invoke([HumanMessage(content=prompt)])
            raw = extract_content(response)
            plan = _parse_planner_json(raw)
            _validate_plan(plan)

            # Merge in additional context that downstream code expects.
            plan["regime"] = regime
            _add_legacy_flat_weights(plan)

            elapsed = round(time.time() - start_time, 2)
            tier_label = f" (retry #{attempt})" if attempt > 0 else ""
            logger.info(
                f"[bold green]>>> Planner Agent: Done in {elapsed}s{tier_label}. "
                f"Regime={regime}, Active={plan['active_horizons']}, "
                f"Caution={plan.get('overall_caution', 'NORMAL')}[/bold green]"
            )
            result = {"planner_plan": plan, "errors": []}
            _daily_cache[today] = result
            return result

        except Exception as retry_err:
            last_error = retry_err
            if not _is_retryable(retry_err) and isinstance(
                retry_err, (json.JSONDecodeError, ValueError)
            ):
                # Parse / validation error — worth retrying (LLM may emit better JSON next attempt).
                continue
            if not _is_retryable(retry_err):
                # Non-transient API error — no point retrying.
                break

    # All retries exhausted — propagate. No rule-based fallback by design.
    elapsed = round(time.time() - start_time, 2)
    errors.append(
        f"Planner Agent: all {len(_TIER_CHAIN)} LLM attempts failed: {last_error}"
    )
    logger.error(
        f"[bold red]>>> Planner Agent: FAILED in {elapsed}s — {last_error}[/bold red]"
    )
    log_failure(
        "agent.planner_node",
        "llm_invoke",
        last_error or RuntimeError("planner exhausted retries"),
        run_id=state.get("run_id", ""),
        elapsed_sec=elapsed,
    )
    raise RuntimeError(
        f"Planner Agent failed after {len(_TIER_CHAIN)} LLM attempts: {last_error}"
    ) from last_error
