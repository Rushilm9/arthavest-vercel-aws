"""
Macro Service — Wraps economic indicators.
(Refactored to focus solely on the Indian Market context).
"""

import yfinance as yf
from app.core.config import logger


def get_indian_macro_data() -> dict:
    """
    Fetches the USD/INR exchange rate as a primary macro indicator for India.
    """
    result = {"usd_inr": None}
    try:
        df = yf.download("INR=X", period="5d", interval="1d", progress=False)
        if not df.empty:
            result["usd_inr"] = round(float(df["Close"].iloc[-1].item()), 2)
    except Exception as e:
        logger.warning(f"[yellow]Failed to fetch USD/INR: {e}[/yellow]")

    return result
