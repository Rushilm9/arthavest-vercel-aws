"""
Market Pulse Agent — Tools (MCP-first)

Primary:  market.get_vix_nifty + market.get_advance_decline from MCP
Fallback: local yfinance + screener_service
"""

from app.core.config import logger
from app.services.mcp_client import mcp_safe


def get_pulse_data() -> dict:
    """
    Fetches VIX, Nifty, and A/D ratio.
    Tries MCP first (better data quality), falls back to local services.
    """
    indices = _get_vix_nifty_mcp()
    advance_decline = _get_advance_decline_mcp()
    return {"indices": indices, "advance_decline": advance_decline}


# ── VIX + Nifty ──────────────────────────────────────────────────────────────


def _get_vix_nifty_mcp() -> dict:
    result = mcp_safe("market.get_vix_nifty")
    if result and isinstance(result, dict):
        return {
            "india_vix": result.get("vix"),
            "nifty_level": result.get("nifty_level"),
            "nifty_change": result.get("nifty_change_pct"),
        }

    # Fallback
    logger.warning(
        "[yellow]Market Pulse: MCP vix_nifty failed, using yfinance[/yellow]"
    )
    from app.services.yfinance_service import get_vix_nifty

    return get_vix_nifty()


# ── Advance / Decline ─────────────────────────────────────────────────────────


def _get_advance_decline_mcp() -> dict:
    result = mcp_safe("market.get_advance_decline")
    if result and isinstance(result, dict):
        return {
            "advancing": result.get("advancing", 0),
            "declining": result.get("declining", 0),
            "ad_ratio": result.get("ratio", 1.0),
            "sector_breakdown": result.get("sector_breakdown", {}),
        }

    # Fallback
    logger.warning(
        "[yellow]Market Pulse: MCP advance_decline failed, using screener[/yellow]"
    )
    from app.services.screener_service import get_advance_decline

    return get_advance_decline()
