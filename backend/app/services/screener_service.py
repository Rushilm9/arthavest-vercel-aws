"""
Screener Service — Wraps `tradingview-screener` for Indian market.
All field names are research-validated (see research_results.md).
"""

try:
    from tradingview_screener import Query, Column

    _TV_SCREENER_AVAILABLE = True
except ImportError:
    Query = None
    Column = None
    _TV_SCREENER_AVAILABLE = False
from app.core.config import logger
import pandas as pd
from typing import Optional


# ── Validated Field Name Constants ─────────────────────────────
# These are the EXACT field names confirmed working for set_markets("india")
# Ref: final-arch.md Section 9

FUNDAMENTAL_FIELDS = [
    "price_earnings_ttm",  # P/E Ratio
    "price_book_fq",  # Price-to-Book
    "enterprise_value_ebitda_ttm",  # EV/EBITDA (None for some stocks)
    "return_on_equity",  # ROE %
    "return_on_assets",  # ROA %
    "return_on_invested_capital",  # ROCE %
    "operating_margin_ttm",  # Operating Margin %
    "after_tax_margin",  # Net Profit Margin %
    "debt_to_equity",  # Debt/Equity ratio
    "current_ratio",  # Current Ratio (None for some)
    "dividend_yield_recent",  # Dividend Yield %
    "market_cap_basic",  # Market Cap (INR)
    "enterprise_value_fq",  # Enterprise Value
    "number_of_employees",  # Employee count
    "float_shares_outstanding",  # Float shares
]

TECHNICAL_FIELDS = [
    "RSI",
    "RSI7",
    "MACD.macd",
    "ADX",
    "EMA20",
    "EMA50",
    "EMA200",
    "BB.upper",
    "BB.lower",
    "VWAP",
    "ATR",
    "Stoch.K",
    "Stoch.D",
    "CCI20",
    "Mom",
]

PERFORMANCE_FIELDS = [
    "Perf.W",
    "Perf.1M",
    "Perf.3M",
    "Perf.6M",
    "Perf.YTD",
    "Perf.Y",
]

VOLUME_FIELDS = [
    "volume",
    "relative_volume_10d_calc",
    "average_volume_10d_calc",
    "average_volume_30d_calc",
    "average_volume_60d_calc",
]

META_FIELDS = [
    "close",
    "change",
    "change_abs",
    "high",
    "low",
    "open",
    "sector",
    "industry",
    "exchange",
    "type",
    "currency",
    "description",
]


def get_discovery_scan(
    min_market_cap: float = 50_000_000_000,  # Rs 5,000 Cr
    min_relative_volume: float = 1.5,
    rsi_min: float = 40,
    rsi_max: float = 65,
    limit: int = 30,
    **kwargs,
) -> Optional[pd.DataFrame]:
    """
    Discovery Agent's primary scan.
    Fetches stocks with unusual volume, healthy RSI, and reasonable valuations.
    Returns a DataFrame with the top `limit` stocks sorted by relative volume.
    """
    if not _TV_SCREENER_AVAILABLE:
        logger.warning(
            "[yellow]tradingview-screener is not installed; skipping discovery scan[/yellow]"
        )
        return None
    try:
        # Build the fields we want to SELECT
        select_fields = [
            "close",
            "change",
            "volume",
            "relative_volume_10d_calc",
            "RSI",
            "VWAP",
            "price_earnings_ttm",
            "price_book_fq",
            "return_on_equity",
            "market_cap_basic",
            "EMA20",
            "EMA50",
            "EMA200",
            "sector",
            "industry",
            "Perf.W",
            "Perf.1M",
            "Perf.3M",
            "ATR",
            "debt_to_equity",
            "after_tax_margin",
            "dividend_yield_recent",
        ]

        query = (
            Query()
            .set_markets("india")
            .select(*select_fields)
            .where(
                Column("relative_volume_10d_calc") > min_relative_volume,
                Column("close") > Column("VWAP"),
                Column("RSI") > rsi_min,
                Column("RSI") < rsi_max,
                Column("market_cap_basic") > min_market_cap,
            )
            .order_by("relative_volume_10d_calc", ascending=False)
            .limit(limit)
        )

        count, df = query.get_scanner_data()
        logger.info(
            f"[green]Discovery scan: {len(df)} stocks found (out of {count} matching)[/green]"
        )
        return df

    except Exception as e:
        logger.error(f"[red]Discovery scan failed: {e}[/red]")
        return None


def get_advance_decline() -> dict:
    """
    Market Pulse Agent's breadth scan.
    Returns advancing, declining, unchanged counts and A/D ratio.
    """
    if not _TV_SCREENER_AVAILABLE:
        logger.warning(
            "[yellow]tradingview-screener is not installed; skipping advance-decline scan[/yellow]"
        )
        return {
            "total_stocks": 0,
            "advancing": 0,
            "declining": 0,
            "unchanged": 0,
            "ad_ratio": 0.0,
            "market_health": "UNKNOWN",
            "sector_breakdown": {},
            "error": "tradingview-screener not installed",
        }
    try:
        query = (
            Query().set_markets("india").select("close", "change", "sector").limit(3000)
        )
        count, df = query.get_scanner_data()

        advancing = int((df["change"] > 0).sum())
        declining = int((df["change"] < 0).sum())
        unchanged = int((df["change"] == 0).sum())
        ratio = round(advancing / max(declining, 1), 2)

        # Sector breakdown
        sector_health = {}
        if "sector" in df.columns:
            for sector, group in df.groupby("sector"):
                sector_adv = int((group["change"] > 0).sum())
                sector_dec = int((group["change"] < 0).sum())
                sector_health[sector] = {
                    "advancing": sector_adv,
                    "declining": sector_dec,
                    "ratio": round(sector_adv / max(sector_dec, 1), 2),
                }

        result = {
            "total_stocks": len(df),
            "total_available": count,
            "advancing": advancing,
            "declining": declining,
            "unchanged": unchanged,
            "ad_ratio": ratio,
            "market_health": "HEALTHY"
            if ratio > 1.5
            else ("WEAK" if ratio < 0.7 else "NEUTRAL"),
            "sector_breakdown": sector_health,
        }

        logger.info(f"[green]A/D Ratio: {ratio} ({advancing}↑ / {declining}↓)[/green]")
        return result

    except Exception as e:
        logger.error(f"[red]Advance/Decline scan failed: {e}[/red]")
        return {
            "total_stocks": 0,
            "advancing": 0,
            "declining": 0,
            "unchanged": 0,
            "ad_ratio": 0.0,
            "market_health": "UNKNOWN",
            "sector_breakdown": {},
            "error": str(e),
        }


def get_stock_fundamentals(ticker_tv: str) -> Optional[dict]:
    """
    Fetch fundamental data for a SINGLE stock from TradingView.
    ticker_tv format: "NSE:RELIANCE" or just pass "RELIANCE" and we prefix it.
    """
    if not _TV_SCREENER_AVAILABLE:
        logger.warning(
            f"[yellow]tradingview-screener is not installed; skipping fundamentals fetch for {ticker_tv}[/yellow]"
        )
        return None
    try:
        # Strip yfinance suffixes
        clean_ticker = ticker_tv.upper().replace(".NS", "").replace(".BO", "")

        if ":" not in clean_ticker:
            clean_ticker = f"NSE:{clean_ticker}"

        fields = (
            FUNDAMENTAL_FIELDS
            + TECHNICAL_FIELDS
            + PERFORMANCE_FIELDS
            + VOLUME_FIELDS
            + META_FIELDS
        )

        query = (
            Query()
            .set_markets("india")
            .select(*fields)
            .where(Column("name") == clean_ticker.split(":")[1])
            .limit(1)
        )
        count, df = query.get_scanner_data()

        if df.empty:
            return None

        return df.iloc[0].to_dict()

    except Exception as e:
        logger.error(f"[red]Failed to get fundamentals for {ticker_tv}: {e}[/red]")
        return None
