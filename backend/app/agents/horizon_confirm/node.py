"""
Horizon Confirmation — Node (F2 Stage 2)

Pure deterministic — no LLM. Reads sub_scores from the four specialists
and either confirms F1's suggested horizon or overrides it when another
horizon scores ≥ 20% higher (per F2_final §8).
"""

import time
from app.agents.state import AnalysisState
from app.core.config import logger


def _ss(d: dict, key: str, default: float = 0.0) -> float:
    """Safely extract a sub_score value as float (0-100)."""
    if not d:
        return default
    sub = d.get("sub_scores", {}) or {}
    val = sub.get(key, default)
    try:
        v = float(val)
        if v <= 1.0:  # specialists may return 0-1
            v = v * 100.0
        return max(0.0, min(100.0, v))
    except (TypeError, ValueError):
        return default


def horizon_confirm_node(state: AnalysisState) -> dict:
    logger.info("[bold cyan]>>> Horizon Confirmation: Scoring horizons...[/bold cyan]")
    start_time = time.time()
    errors: list[str] = []

    tech = state.get("technical_output", {}) or {}
    fund = state.get("fundamental_output", {}) or {}
    sent = state.get("sentiment_output", {}) or {}
    chart = state.get("chart_pattern_output", {}) or {}

    raw_horizon = state.get("suggested_horizon")
    suggested = (
        (raw_horizon or "MID").upper() if isinstance(raw_horizon, str) else "MID"
    )
    if suggested not in ("SHORT", "MID", "LONG"):
        suggested = "MID"
    if not raw_horizon:
        errors.append("suggested_horizon missing — defaulted to MID")

    try:
        # Per F2_final §8 — combine relevant sub_scores
        short_score = (
            _ss(tech, "short_term_momentum")
            + _ss(sent, "recent_48h_catalyst")
            + _ss(chart, "intraday_breakout")
        )
        mid_score = (
            _ss(fund, "earnings_cycle")
            + _ss(tech, "weekly_structure")
            + _ss(sent, "theme_consistency_30d")
        )
        long_score = (
            _ss(fund, "compounding_track_record")
            + _ss(fund, "structural_tailwind")
            + _ss(chart, "weekly_base")
        )

        scores = {"SHORT": short_score, "MID": mid_score, "LONG": long_score}
        winner = max(scores, key=scores.get)
        suggested_score = scores[suggested]

        final = suggested
        reason = "Confirmed (LLM/F1 horizon retained)."
        total_evidence = sum(scores.values())
        # Require at least 25% of max possible evidence (3 sub_scores × 100 = 300 per horizon)
        # before allowing any override — prevents noisy single-specialist flips
        sufficient_evidence = total_evidence >= 75.0
        # Override only if winner exceeds suggested by ≥ 20% and we have sufficient evidence
        if sufficient_evidence and winner != suggested and suggested_score > 0:
            uplift = (scores[winner] - suggested_score) / max(suggested_score, 1)
            if uplift >= 0.20:
                final = winner
                reason = (
                    f"Override {suggested}→{winner}: "
                    f"{winner} score {scores[winner]:.0f} vs {suggested} {suggested_score:.0f} "
                    f"({uplift * 100:.0f}% uplift)."
                )
        elif (
            sufficient_evidence
            and winner != suggested
            and suggested_score == 0
            and scores[winner] > 0
        ):
            # Suggested has no support at all
            final = winner
            reason = f"Override {suggested}→{winner}: suggested horizon had no supporting evidence."

        elapsed = round(time.time() - start_time, 2)
        logger.info(
            f"[bold green]>>> Horizon Confirmation: {suggested}→{final} in {elapsed}s "
            f"(SHORT={short_score:.0f}, MID={mid_score:.0f}, LONG={long_score:.0f})[/bold green]"
        )

        return {
            "final_horizon": final,
            "horizon_override_reason": reason,
            "errors": [],
        }

    except Exception as e:
        elapsed = round(time.time() - start_time, 2)
        errors.append(f"Horizon Confirmation crashed: {e}")
        logger.error(
            f"[bold red]>>> Horizon Confirmation: FAILED in {elapsed}s — {e}[/bold red]"
        )
        return {
            "final_horizon": suggested,
            "horizon_override_reason": f"Error: {e}",
            "errors": errors,
        }
