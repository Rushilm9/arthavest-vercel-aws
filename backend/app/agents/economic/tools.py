"""
Economic Agent — Tools (MCP-first)

Primary:  economic.get_full_snapshot from deployed MCP server
Fallback: direct yfinance calls (original implementation)
"""

try:
    import yfinance as yf
except ImportError:
    yf = None
from typing import Optional
from app.core.config import logger
from app.services.mcp_client import mcp_safe


def fetch_economic_indicators() -> dict:
    """
    Returns a basket of macro indicators for the Economic Agent's LLM prompt.

    Market-priced data (USD/INR, Brent, gold, US 10Y, VIX, Nifty) is ALWAYS
    fetched live from yfinance — the MCP snapshot returned these in mixed
    units (MCX INR crude labeled as Brent USD) and omitted VIX/Nifty/10Y
    entirely, so the regime LLM was reasoning over nulls and unit garbage.

    Official India statistics that have no free live API (RBI repo rate, CPI,
    GDP, FII/DII, Fed rate, fiscal deficit) still come from MCP
    economic.get_full_snapshot — but with their as-of dates passed through so
    the LLM can discount stale prints (the MCP WPI is from 2022; GDP can lag
    ~a year) instead of citing them as current conditions.
    """
    live = _fetch_live_market_data()

    snap = mcp_safe("economic.get_full_snapshot")
    if snap and isinstance(snap, dict):
        logger.info(
            "[green]Economic tools: MCP stats + live yfinance market data[/green]"
        )
    else:
        logger.warning(
            "[yellow]Economic tools: MCP unavailable — India macro stats will be null[/yellow]"
        )
        snap = {}

    repo = snap.get("repo_rate", {}) or {}
    cpi = snap.get("cpi", {}) or {}
    gdp = snap.get("gdp_growth", {}) or {}
    fii_dii = snap.get("fii_dii", {}) or {}
    fed = snap.get("us_fed_rate", {}) or {}
    fiscal = snap.get("fiscal_deficit", {}) or {}

    # If yfinance is down, salvage USD/INR from MCP (it sources yfinance too).
    usd_inr = live.get("usd_inr") or _safe((snap.get("usd_inr", {}) or {}).get("rate"))

    # MCX-style ₹/10g proxy derived from live COMEX gold — kept for the
    # EconomicSnapshots.gold_price column whose history is in ₹/10g.
    gold_usd = live.get("gold_usd_oz")
    gold_inr_proxy = (
        round(gold_usd * usd_inr / 3.110348, 2)  # $/ozt → ₹/10g
        if gold_usd and usd_inr
        else _safe((snap.get("gold", {}) or {}).get("price"))
    )

    return {
        # Live market data (yfinance)
        "usd_inr": usd_inr,
        "usd_inr_1m_change_pct": live.get("usd_inr_1m_change_pct")
        or _safe((snap.get("usd_inr", {}) or {}).get("change_1m_pct")),
        "crude_oil_brent": live.get("crude_oil_brent"),  # USD/bbl
        "crude_1m_change_pct": live.get("crude_1m_change_pct"),
        "gold_usd_oz": gold_usd,
        "gold_1m_change_pct": live.get("gold_1m_change_pct"),
        "gold_inr_proxy": gold_inr_proxy,
        "us_10y_yield": live.get("us_10y_yield"),
        "india_vix": live.get("india_vix"),
        "nifty_level": live.get("nifty_level"),
        "nifty_1m_change_pct": live.get("nifty_1m_change_pct"),
        # Official India statistics (MCP) + as-of dates for staleness awareness
        "rbi_repo_rate": _safe(repo.get("rate")),
        "rbi_repo_as_of": repo.get("last_changed") or "unknown",
        "india_cpi_yoy": _safe(cpi.get("yoy_change")),
        "india_cpi_as_of": cpi.get("month") or "unknown",
        "india_gdp_yoy": _safe(gdp.get("growth_pct")),
        "india_gdp_as_of": gdp.get("quarter") or "unknown",
        "fii_flows_inr_cr": _safe(fii_dii.get("fii_net")),
        "dii_flows_inr_cr": _safe(fii_dii.get("dii_net")),
        "us_fed_rate": _safe(fed.get("rate")),
        "fiscal_deficit_pct": _safe(fiscal.get("deficit_pct_gdp")),
        "fiscal_deficit_as_of": fiscal.get("year") or "unknown",
    }


def _fetch_live_market_data() -> dict:
    """Fetch the market-priced indicators from yfinance in parallel (~3s)."""
    from concurrent.futures import ThreadPoolExecutor

    jobs = {
        "usd_inr": lambda: _last_close("INR=X"),
        "usd_inr_1m_change_pct": lambda: _pct_change("INR=X", "1mo"),
        "crude_oil_brent": lambda: _last_close("BZ=F"),
        "crude_1m_change_pct": lambda: _pct_change("BZ=F", "1mo"),
        "gold_usd_oz": lambda: _last_close("GC=F"),
        "gold_1m_change_pct": lambda: _pct_change("GC=F", "1mo"),
        "us_10y_yield": lambda: _last_close("^TNX"),
        "india_vix": lambda: _last_close("^INDIAVIX"),
        "nifty_level": lambda: _last_close("^NSEI"),
        "nifty_1m_change_pct": lambda: _pct_change("^NSEI", "1mo"),
    }
    out: dict = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {k: pool.submit(fn) for k, fn in jobs.items()}
        for k, fut in futures.items():
            try:
                out[k] = fut.result(timeout=30)
            except Exception as e:
                logger.warning(
                    f"[yellow]Economic tools: live fetch failed for {k}: {e}[/yellow]"
                )
                out[k] = None
    return out


# ── Helpers ──────────────────────────────────────────────────────────────────


def _safe(val) -> Optional[float]:
    if val is None:
        return None
    try:
        import math

        f = float(val)
        return None if math.isnan(f) else round(f, 4)
    except (TypeError, ValueError):
        return None


def _last_close(ticker: str, period: str = "5d") -> Optional[float]:
    if yf is None:
        logger.warning(
            f"[yellow]yfinance is not installed; skipping fallback fetch for {ticker}[/yellow]"
        )
        return None
    try:
        df = yf.download(ticker, period=period, interval="1d", progress=False)
        if df is None or df.empty:
            return None
        val = df["Close"].iloc[-1]
        if hasattr(val, "iloc"):
            val = val.iloc[0]
        return round(float(val), 4)
    except Exception as e:
        logger.warning(f"[yellow]Economic fallback: failed {ticker}: {e}[/yellow]")
        return None


def _pct_change(ticker: str, period: str = "1mo") -> Optional[float]:
    if yf is None:
        return None
    try:
        df = yf.download(ticker, period=period, interval="1d", progress=False)
        if df is None or df.empty or len(df) < 2:
            return None
        first = float(
            df["Close"].iloc[0].iloc[0]
            if hasattr(df["Close"].iloc[0], "iloc")
            else df["Close"].iloc[0]
        )
        last = float(
            df["Close"].iloc[-1].iloc[0]
            if hasattr(df["Close"].iloc[-1], "iloc")
            else df["Close"].iloc[-1]
        )
        if first == 0:
            return None
        return round(((last - first) / first) * 100, 2)
    except Exception as e:
        logger.warning(
            f"[yellow]Economic fallback: pct_change failed {ticker}: {e}[/yellow]"
        )
        return None
