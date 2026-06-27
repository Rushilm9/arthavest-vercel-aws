"""
Macro Context Agent — Node (F1 Stage 4)
Reads Economic + Market Pulse + News from state, calls Gemini for the
final regime label: BULL / SIDEWAYS / BEAR / CRISIS.

Retry strategy: PRO → PRO → PRO (3 attempts, 3s spacing). No rule-based fallback —
if all retries fail, the pipeline fails. A silent SIDEWAYS default masks BULL/BEAR/CRISIS
and yields silently-wrong recommendations downstream.
"""

import time
from langchain_core.messages import HumanMessage

from app.agents.state import AnalysisState
from app.agents.macro_context.tools import fetch_macro_context
from app.agents.macro_context.prompts import REGIME_CLASSIFICATION_PROMPT
from app.core.model_router import get_model, ModelTier
from app.core.llm import extract_content
from app.core.config import logger
from app.services.failure_log import log_failure


VALID_REGIMES = {"BULL", "SIDEWAYS", "BEAR", "CRISIS", "VOLATILE"}

# LLM-only quality policy — retry PRO, never fall back to a weaker tier or rules.
_TIER_CHAIN = [ModelTier.PRO, ModelTier.PRO, ModelTier.PRO]
_RETRY_DELAY_SECS = 3


def _is_retryable(exc: Exception) -> bool:
    """Check if the exception is a transient 503/429 that warrants a retry."""
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
        )
    )


import datetime

_daily_cache = {}


def macro_context_node(state: AnalysisState) -> dict:
    logger.info(
        "[bold cyan]>>> Macro Context Agent: Synthesizing regime...[/bold cyan]"
    )
    start_time = time.time()

    today = str(datetime.date.today())
    if today in _daily_cache:
        logger.info(
            f"[dim]>>> Macro Context Agent: Using cached data for {today}...[/dim]"
        )
        return dict(_daily_cache[today])

    vix = state.get("india_vix", 15.0)
    nifty = state.get("nifty_level", 0.0)
    ad_ratio = state.get("advance_decline_ratio", 1.0)
    pulse_score = state.get("market_pulse_score", 50)

    try:
        macro_data = fetch_macro_context()
        usd_inr = macro_data["economy"].get("usd_inr", "Unknown")
        headlines = macro_data["headlines"][:20]
        headlines_str = (
            "\n".join(f"- {h}" for h in headlines) if headlines else "- No recent news"
        )

        prompt = REGIME_CLASSIFICATION_PROMPT.format(
            vix=vix,
            nifty=nifty,
            ad_ratio=ad_ratio,
            pulse_score=pulse_score,
            economic_score=state.get("economic_score", 50),
            economic_regime=state.get("economic_regime", "STABLE"),
            overweight_sectors=state.get("overweight_sectors", []),
            underweight_sectors=state.get("underweight_sectors", []),
            market_sentiment=state.get("market_sentiment", 0.0),
            hot_sectors=state.get("hot_sectors", []),
            avoid_sectors=state.get("avoid_sectors", []),
            anomaly_alerts=state.get("anomaly_alerts", []),
            usd_inr=usd_inr,
            headlines=headlines_str,
        )

        # ── Retry chain: PRO → PRO → PRO. No tier or rule fallback. ──
        last_error = None
        for attempt, tier in enumerate(_TIER_CHAIN):
            try:
                if attempt > 0 and last_error is not None:
                    logger.warning(
                        f"[yellow]Macro Context: attempt {attempt + 1}/{len(_TIER_CHAIN)} "
                        f"using {tier.value} (previous: {last_error})[/yellow]"
                    )
                    time.sleep(_RETRY_DELAY_SECS)

                llm = get_model(tier)
                response = llm.invoke([HumanMessage(content=prompt)])
                import json

                raw = extract_content(response)
                reasoning = ""
                try:
                    cleaned = raw.strip()
                    if cleaned.startswith("```"):
                        lines = [
                            l
                            for l in cleaned.split("\n")
                            if not l.strip().startswith("```")
                        ]
                        cleaned = "\n".join(lines)
                    parsed = json.loads(cleaned)
                    regime = parsed.get("regime", "").upper()
                    confidence = float(parsed.get("confidence", 0.0))
                    triggers = parsed.get("triggers", {})
                    reasoning = parsed.get("reasoning", "")
                except Exception as e:
                    # Fallback if JSON fails
                    regime = raw.upper().split()[0] if raw else ""
                    confidence = 0.0
                    triggers = {}
                    reasoning = "Failed to parse macro context reasoning."

                if regime not in VALID_REGIMES:
                    # Invalid regime is a parsing failure — retry the LLM, do not silently default.
                    raise ValueError(
                        f"Macro Context: invalid regime '{regime}' (not in {VALID_REGIMES})"
                    )

                elapsed = round(time.time() - start_time, 2)
                tier_label = f" (retry #{attempt})" if attempt > 0 else ""
                logger.info(
                    f"[bold green]>>> Macro Context Agent: {regime} (conf={confidence}%) in {elapsed}s{tier_label}[/bold green]"
                )

                # Coherence check — log a warning for unusual economic/macro combinations
                eco = state.get("economic_regime", "STABLE")
                _INCOHERENT = {
                    ("EXPANSION", "BEAR"),
                    ("EXPANSION", "CRISIS"),
                    ("CONTRACTION", "BULL"),
                }
                if (eco, regime) in _INCOHERENT:
                    logger.warning(
                        f"[yellow]Macro Context: incoherent regime pair — "
                        f"economic_regime={eco} but macro_regime={regime}. "
                        f"Check economic/market-pulse data quality.[/yellow]"
                    )

                result = {
                    "macro_regime": regime,
                    "macro_confidence": confidence,
                    "macro_triggers": triggers,
                    "macro_reasoning": reasoning,
                    "errors": [],
                }
                _daily_cache[today] = result
                return result

            except Exception as retry_err:
                last_error = retry_err
                # Parse/validation errors (ValueError) are worth retrying — LLM may emit a valid regime next.
                if isinstance(retry_err, ValueError):
                    continue
                if not _is_retryable(retry_err):
                    # Non-transient API error — no point retrying.
                    break

        # All retries exhausted — propagate. No SIDEWAYS fallback by design.
        elapsed = round(time.time() - start_time, 2)
        logger.error(
            f"[bold red]>>> Macro Context Agent: FAILED in {elapsed}s — {last_error}[/bold red]"
        )
        log_failure(
            "agent.macro_context_node",
            "llm_invoke",
            last_error or RuntimeError("macro_context exhausted retries"),
            run_id=state.get("run_id", ""),
            elapsed_sec=elapsed,
        )
        raise RuntimeError(
            f"Macro Context Agent failed after {len(_TIER_CHAIN)} LLM attempts: {last_error}"
        ) from last_error

    except RuntimeError:
        # Already logged inside the retry block — just propagate.
        raise
    except Exception as e:
        # fetch_macro_context() or prompt-formatting error before the retry loop — also propagate.
        elapsed = round(time.time() - start_time, 2)
        logger.error(
            f"[bold red]>>> Macro Context Agent: FAILED in {elapsed}s — {e}[/bold red]"
        )
        log_failure(
            "agent.macro_context_node",
            "pre_llm",
            e,
            run_id=state.get("run_id", ""),
            elapsed_sec=elapsed,
        )
        raise
