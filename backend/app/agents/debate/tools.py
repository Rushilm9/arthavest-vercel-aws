"""
Debate Agent — Tools
Pure Python conflict detection. O(1), zero Gemini cost.
Ref: final-arch.md Agent 8 (The Devil's Advocate)
"""

from app.core.config import logger


def detect_conflict(
    tech_signal: str,
    fund_signal: str,
    sent_signal: str,
    sent_score: float,
    market_pulse_score: int,
) -> tuple[bool, str]:
    """
    Detects conflict between worker agent signals.
    Pure Python — O(1), no LLM call.

    Returns:
        (has_conflict: bool, conflict_description: str)
    """
    conflicts = []

    # Rule 1: Technical and Fundamental disagree
    if tech_signal != fund_signal:
        conflicts.append(
            f"Technical ({tech_signal}) contradicts Fundamental ({fund_signal})"
        )

    # Rule 2: Strong sentiment contradicts technical
    if abs(sent_score) > 0.5 and sent_signal != tech_signal:
        conflicts.append(
            f"Strong sentiment ({sent_signal}, score={sent_score:.2f}) "
            f"contradicts Technical ({tech_signal})"
        )

    # Rule 3: Market health is poor but technical says BUY
    if market_pulse_score < 30 and tech_signal == "BUY":
        conflicts.append(
            f"Market pulse is weak ({market_pulse_score}/100) but Technical says BUY"
        )

    # Rule 4: All three signals differ
    signals = {tech_signal, fund_signal, sent_signal}
    if len(signals) == 3:
        conflicts.append(
            f"All three agents disagree: Tech={tech_signal}, "
            f"Fund={fund_signal}, Sent={sent_signal}"
        )

    has_conflict = len(conflicts) > 0
    description = " | ".join(conflicts) if conflicts else "No conflict detected"

    if has_conflict:
        logger.info(f"[yellow]Debate: Conflict detected — {description}[/yellow]")
    else:
        logger.info("[green]Debate: No conflict — skipping debate[/green]")

    return has_conflict, description


def merge_worker_signals(
    tech_output: dict,
    fund_output: dict,
    sent_output: dict,
) -> dict:
    """
    Merge all three worker outputs into a single merged_signals dict.
    Used by both Debate and Decision agents.
    """
    return {
        "technical": {
            "signal": tech_output.get("signal", "HOLD"),
            "confidence": tech_output.get("confidence", 0.0),
            "narrative": tech_output.get("narrative", ""),
        },
        "fundamental": {
            "signal": fund_output.get("signal", "HOLD"),
            "confidence": fund_output.get("confidence", 0.0),
            "weighted_score": fund_output.get("weighted_score", 0.0),
            "narrative": fund_output.get("narrative", ""),
        },
        "sentiment": {
            "signal": sent_output.get("signal", "HOLD"),
            "confidence": sent_output.get("confidence", 0.0),
            "aggregate_score": sent_output.get("aggregate_score", 0.0),
            "anomaly_count": sent_output.get("anomaly_count", 0),
            "narrative": sent_output.get("narrative", ""),
        },
    }
