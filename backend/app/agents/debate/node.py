"""
Debate Agent — Node (F2 Stage 3)
ALWAYS runs. Reads RAW evidence and produces an adversarial reading.
If the debate's independent signal disagrees with the consensus, we set
max_decision_confidence = 0.70 so Decision can't run away with it.

Retry strategy: PRO_THINK → PRO_THINK → PRO_THINK (3 attempts, 3s spacing).
No silent "agrees=True" fallback — that would disable the 70% confidence
cap on the very runs that need it most.
"""

import json
import re
import time
from langchain_core.messages import HumanMessage

from app.agents.state import AnalysisState
from app.agents.debate.tools import merge_worker_signals
from app.agents.debate.prompts import DEBATE_PROMPT
from app.core.model_router import get_model, get_model_id, ModelTier
from app.core.llm import extract_content
from app.core.config import logger
from app.services.failure_log import log_failure
from app.services.run_log import log_agent_run


_MAX_ATTEMPTS = 3
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


def debate_node(state: AnalysisState) -> dict:
    symbol = state.get("stock_symbol", "UNKNOWN")
    logger.info(
        f"[bold cyan]>>> Debate Agent: Adversarial review of {symbol}...[/bold cyan]"
    )
    start_time = time.time()

    tech = state.get("technical_output", {}) or {}
    fund = state.get("fundamental_output", {}) or {}
    sent = state.get("sentiment_output", {}) or {}
    chart = state.get("chart_pattern_output", {}) or {}
    merged = merge_worker_signals(tech, fund, sent)

    # Consensus signal — simple majority of the four.
    # Specialist HOLD (their neutral stance) counts as WAIT: the verdict
    # label space is BUY/SELL/WAIT only.
    consensus_votes = {
        "BUY": 0,
        "SELL": 0,
        "WAIT": 0,
    }
    for o in (tech, fund, sent, chart):
        sig = (o.get("signal") or "WAIT").upper()
        if sig not in consensus_votes:
            sig = "WAIT"
        consensus_votes[sig] += 1
    consensus_signal = max(consensus_votes, key=consensus_votes.get)

    prompt = DEBATE_PROMPT.format(
        symbol=symbol,
        final_horizon=state.get("final_horizon")
        or state.get("suggested_horizon")
        or "MID",
        macro_regime=state.get("macro_regime", "SIDEWAYS"),
        market_pulse_score=state.get("market_pulse_score", 50),
        tech_signal=tech.get("signal", "HOLD"),
        tech_confidence=tech.get("confidence", 0.0),
        fund_signal=fund.get("signal", "HOLD"),
        fund_confidence=fund.get("confidence", 0.0),
        fund_score=fund.get("weighted_score", 0.0),
        sent_signal=sent.get("signal", "HOLD"),
        sent_confidence=sent.get("confidence", 0.0),
        sent_score=sent.get("aggregate_score", 0.0),
        chart_signal=chart.get("signal", "HOLD"),
        chart_confidence=chart.get("confidence", 0.0),
        raw_indicators=_truncate(tech.get("raw_data", {}), 1500),
        raw_fundamentals=_truncate(fund.get("raw_data", {}), 1500),
        raw_headlines=_truncate(
            sent.get("scores", []) or sent.get("key_themes", []), 1500
        ),
        raw_patterns=_truncate(chart.get("raw_data", {}), 1000),
    )

    last_error: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            if attempt > 0:
                logger.warning(
                    f"[yellow]Debate Agent: attempt {attempt + 1}/{_MAX_ATTEMPTS} "
                    f"(previous: {last_error})[/yellow]"
                )
                time.sleep(_RETRY_DELAY_SECS)

            llm = get_model(ModelTier.PRO_THINK)
            response = llm.invoke([HumanMessage(content=prompt)])
            raw_response_text = extract_content(response)
            parsed = _parse(raw_response_text)

            ind_signal = (parsed.get("independent_signal") or "").upper()
            if ind_signal == "HOLD":
                ind_signal = "WAIT"  # legacy label — neutral maps to WAIT
            if ind_signal not in ("BUY", "SELL", "WAIT"):
                raise ValueError(
                    f"Debate Agent: invalid independent_signal {ind_signal!r}"
                )
            try:
                ind_conf = max(
                    0.0, min(1.0, float(parsed.get("independent_confidence")))
                )
            except (TypeError, ValueError):
                raise ValueError(
                    f"Debate Agent: independent_confidence not numeric: "
                    f"{parsed.get('independent_confidence')!r}"
                )

            agrees = parsed.get("agrees_with_consensus")
            if not isinstance(agrees, bool):
                # Derive if missing — agrees if LLM's signal matches the specialist majority
                agrees = ind_signal == consensus_signal

            missed_risks = parsed.get("missed_risks", []) or []

            debate_output = {
                "bull_case": parsed.get("bull_case", ""),
                "bear_case": parsed.get("bear_case", ""),
                "missed_risks": missed_risks,
                "evidence_citations": parsed.get("evidence_citations", []) or [],
                "independent_signal": ind_signal,
                "independent_confidence": ind_conf,
                "agrees_with_consensus": bool(agrees),
                "synthesis": parsed.get("synthesis", ""),
                # Legacy fields kept for backward compat with older Decision code
                "dominant_signal": ind_signal,
                "dominant_confidence": ind_conf,
                "conflict_resolved": True,
            }

            # ── Graded disagreement: cap only on STRONG dissent ──────
            # PRO_THINK debate finds at least 1 missed risk on nearly every stock,
            # which used to peg final confidence at 70 across the board. Cap now fires
            # only when the disagreement is materially against the trade direction:
            #   • independent_signal opposite to consensus (BUY vs SELL only), OR
            #   • ≥ 2 missed risks flagged
            # Mild "agrees=false" with a single soft caveat no longer triggers the cap.
            opposite_pairs = {("BUY", "SELL"), ("SELL", "BUY")}
            ind_vs_cons = (ind_signal, consensus_signal)
            opposite_signals = ind_vs_cons in opposite_pairs
            many_missed_risks = len(missed_risks) >= 2
            strong_dissent = (not agrees) and (opposite_signals or many_missed_risks)
            max_conf = 0.70 if strong_dissent else 1.0

            elapsed = round(time.time() - start_time, 2)
            tier_label = f" (retry #{attempt})" if attempt > 0 else ""
            logger.info(
                f"[bold green]>>> Debate Agent: ind_signal={ind_signal} consensus={consensus_signal} "
                f"agrees={agrees} missed_risks={len(missed_risks)} strong_dissent={strong_dissent} "
                f"max_conf={max_conf} in {elapsed}s{tier_label}[/bold green]"
            )

            # Rich-capture log row for the /agentlogs detail UI.
            # Stores rendered prompt, raw LLM JSON, parsed reasoning, signal, confidence.
            try:
                log_agent_run(
                    run_id=state.get("run_id", "") or "",
                    agent_name="debate_llm",
                    agent_type="F2_DEBATE_LLM",
                    status="SUCCESS",
                    latency_ms=elapsed * 1000.0,
                    model_used=get_model_id(ModelTier.PRO_THINK),
                    signal=ind_signal,
                    confidence=ind_conf,
                    retry_count=attempt,
                    prompt_template=prompt,
                    raw_llm_response=raw_response_text,
                    output=debate_output,
                    reasoning={
                        "bull_case": debate_output.get("bull_case"),
                        "bear_case": debate_output.get("bear_case"),
                        "synthesis": debate_output.get("synthesis"),
                        "missed_risks": debate_output.get("missed_risks"),
                        "evidence_citations": debate_output.get("evidence_citations"),
                        "consensus_signal": consensus_signal,
                        "agrees_with_consensus": agrees,
                        "strong_dissent": strong_dissent,
                        "max_decision_confidence": max_conf,
                    },
                )
            except Exception:
                pass

            return {
                "merged_signals": merged,
                "debate_triggered": True,
                "debate_output": debate_output,
                "debate_disagreement": strong_dissent,
                "max_decision_confidence": max_conf,
                "errors": [],
            }

        except Exception as retry_err:
            last_error = retry_err
            if isinstance(retry_err, (json.JSONDecodeError, ValueError)):
                continue
            if not _is_retryable(retry_err):
                break

    # All retries exhausted — propagate. No silent "agrees=True, max_conf=1.0" fallback;
    # that would disable the adversarial confidence cap on the runs that need it most.
    elapsed = round(time.time() - start_time, 2)
    logger.error(
        f"[bold red]>>> Debate Agent: FAILED in {elapsed}s — {last_error}[/bold red]"
    )
    log_failure(
        "agent.debate_node",
        "llm_invoke",
        last_error or RuntimeError("debate exhausted retries"),
        run_id=state.get("run_id", ""),
        symbol=symbol,
        elapsed_sec=elapsed,
    )
    raise RuntimeError(
        f"Debate Agent failed after {_MAX_ATTEMPTS} LLM attempts: {last_error}"
    ) from last_error


def _truncate(obj, char_limit: int) -> str:
    s = str(obj)
    if len(s) <= char_limit:
        return s
    return s[:char_limit] + "...[truncated]"


def _parse(raw: str) -> dict:
    cleaned = (raw or "").strip()
    if cleaned.startswith("```"):
        lines = [l for l in cleaned.split("\n") if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)
    candidates = [cleaned]
    first = cleaned.find("{")
    last = cleaned.rfind("}")
    if first != -1 and last != -1 and last > first:
        candidates.append(cleaned[first : last + 1])
    for cand in candidates:
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            try:
                return json.loads(re.sub(r",(\s*[}\]])", r"\1", cand))
            except json.JSONDecodeError:
                continue
    raise ValueError(
        f"Debate Agent: unparseable LLM JSON (len={len(raw)}): {raw[:200]!r}"
    )
