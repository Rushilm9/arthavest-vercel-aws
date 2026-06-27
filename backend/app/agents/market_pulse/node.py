"""
Market Pulse Agent — Node function
Calculates mathematical momentum score of the overall market.
No LLM is used.
"""

from app.agents.state import AnalysisState
from app.agents.market_pulse.tools import get_pulse_data
from app.core.config import logger
from app.services.failure_log import log_failure
import time

import datetime

_daily_cache = {}


def market_pulse_node(state: AnalysisState) -> dict:
    """
    LangGraph Node: Market Pulse.
    Evaluates India VIX and Breadth to generate a simple health score 0-100.
    """
    today = str(datetime.date.today())
    if today in _daily_cache:
        logger.info(
            f"[dim]>>> Market Pulse Agent: Using cached data for {today}...[/dim]"
        )
        return dict(_daily_cache[today])

    logger.info("[bold cyan]>>> Market Pulse Agent: Computing scores...[/bold cyan]")
    start_time = time.time()
    errors: list[str] = []

    try:
        data = get_pulse_data()
        ad_ratio = data["advance_decline"].get("ad_ratio", 1.0)
        vix = data["indices"].get("india_vix", 15.0)
        nifty = data["indices"].get("nifty_level", 0.0)

        # Simple Math Score Logic (1-100)
        # Baseline is 50. High VIX (> 20) reduces score. High A/D (> 1.2) increases score.
        score = 50

        # VIX adjustments
        if vix is not None:
            if vix > 25:
                score -= 20
            elif vix > 20:
                score -= 10
            elif vix < 13:
                score += 10

        # A/D Ratio adjustments
        if ad_ratio > 2.0:
            score += 20
        elif ad_ratio > 1.2:
            score += 10
        elif ad_ratio < 0.5:
            score -= 20
        elif ad_ratio < 0.8:
            score -= 10

        # Clamp between 0 and 100
        score = max(0, min(100, score))

        elapsed = round(time.time() - start_time, 2)
        logger.info(
            f"[bold green]>>> Market Pulse Agent: Done in {elapsed}s. Score: {score}/100[/bold green]"
        )

        result = {
            "market_pulse_score": score,
            "india_vix": vix or 0.0,
            "nifty_level": nifty or 0.0,
            "advance_decline_ratio": ad_ratio,
            "errors": [],
        }
        _daily_cache[today] = result
        return result

    except Exception as e:
        elapsed = round(time.time() - start_time, 2)
        error_msg = f"Market Pulse Agent crashed: {str(e)}"
        errors.append(error_msg)
        logger.error(
            f"[bold red]>>> Market Pulse Agent: FAILED in {elapsed}s — {e}[/bold red]"
        )

        log_failure(
            "agent.market_pulse_node",
            "data_fetch",
            e,
            run_id=state.get("run_id", ""),
            elapsed_sec=elapsed,
        )
        return {
            "market_pulse_score": 50,
            "india_vix": 0.0,
            "nifty_level": 0.0,
            "advance_decline_ratio": 1.0,
            "sector_strength": [],
            "breadth_signal": "NEUTRAL",
            "market_health": "MODERATE",
            "errors": errors,
        }
