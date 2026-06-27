"""
Fundamental Agent — Tools (MCP-first)
Primary:  MCP market.get_fundamentals + market.get_ownership + market.get_financials
Fallback: TradingView screener + yfinance (original logic)
Scoring logic is unchanged — only the data-fetching layer is updated.
"""

from app.services.mcp_client import mcp_safe
from app.services.screener_service import get_stock_fundamentals
from app.services.yfinance_service import (
    get_stock_info,
    get_ownership_data,
    get_financial_statements,
)
from app.core.horizon_params import fundamental_weights
from app.core.config import logger
from typing import Optional


def get_fundamental_data(symbol: str) -> dict:
    """
    Gathers ALL fundamental data for a single stock.
    Returns a flat dict with all metrics.
    """
    result = {
        "symbol": symbol,
        "sector": "Unknown",
        "pe_ratio": None,
        "price_to_book": None,
        "ev_ebitda": None,
        "roe": None,
        "roce": None,
        "roa": None,
        "net_margin": None,
        "operating_margin": None,
        "debt_to_equity": None,
        "current_ratio": None,
        "dividend_yield": None,
        "market_cap": None,
        "market_cap_cr": None,
        "revenue_growth": None,
        "earnings_growth": None,
        "promoter_holding": None,
        "institutional_holding": None,
        "interest_coverage": None,
    }

    bare_symbol = symbol.replace(".NS", "").replace(".BO", "")
    # ── Source 1: MCP market.get_fundamentals ────────────────────────────────
    mcp_fund = mcp_safe("market.get_fundamentals", {"symbol": bare_symbol})
    if mcp_fund and isinstance(mcp_fund, dict):
        result["pe_ratio"] = _safe_float(mcp_fund.get("PE") or mcp_fund.get("pe_ratio"))
        result["price_to_book"] = _safe_float(
            mcp_fund.get("PB") or mcp_fund.get("price_to_book")
        )
        result["roe"] = _safe_float(mcp_fund.get("ROE") or mcp_fund.get("roe"))
        result["roce"] = _safe_float(mcp_fund.get("ROCE") or mcp_fund.get("roce"))
        result["roa"] = _safe_float(mcp_fund.get("ROA") or mcp_fund.get("roa"))
        result["net_margin"] = _safe_float(mcp_fund.get("net_margin"))
        result["operating_margin"] = _safe_float(mcp_fund.get("operating_margin"))
        result["debt_to_equity"] = _safe_float(
            mcp_fund.get("DE") or mcp_fund.get("debt_to_equity")
        )
        result["current_ratio"] = _safe_float(mcp_fund.get("current_ratio"))
        result["dividend_yield"] = _safe_float(mcp_fund.get("dividend_yield"))
        result["market_cap"] = _safe_float(mcp_fund.get("market_cap"))
        result["sector"] = mcp_fund.get("sector") or "Unknown"
        result["ev_ebitda"] = _safe_float(mcp_fund.get("ev_ebitda"))
        result["revenue_growth"] = _safe_float(mcp_fund.get("revenue_growth"))
        result["earnings_growth"] = _safe_float(mcp_fund.get("earnings_growth"))
        if result["market_cap"]:
            result["market_cap_cr"] = round(result["market_cap"] / 10_000_000, 0)
        logger.info(f"[green]Fundamental: data from MCP for {symbol}[/green]")
    else:
        # ── Fallback: TradingView ────────────────────────────────────────────
        logger.warning(
            f"[yellow]Fundamental: MCP failed for {symbol}, using TradingView[/yellow]"
        )
        tv_data = get_stock_fundamentals(symbol)
        if tv_data:
            result["pe_ratio"] = _safe_float(tv_data.get("price_earnings_ttm"))
            result["price_to_book"] = _safe_float(tv_data.get("price_book_fq"))
            result["roe"] = _safe_float(tv_data.get("return_on_equity"))
            result["roce"] = _safe_float(tv_data.get("return_on_invested_capital"))
            result["roa"] = _safe_float(tv_data.get("return_on_assets"))
            result["net_margin"] = _safe_float(tv_data.get("after_tax_margin"))
            result["operating_margin"] = _safe_float(
                tv_data.get("operating_margin_ttm")
            )
            result["debt_to_equity"] = _safe_float(tv_data.get("debt_to_equity"))
            result["current_ratio"] = _safe_float(tv_data.get("current_ratio"))
            result["dividend_yield"] = _safe_float(tv_data.get("dividend_yield_recent"))
            result["market_cap"] = _safe_float(tv_data.get("market_cap_basic"))
            result["sector"] = tv_data.get("sector", "Unknown") or "Unknown"
            if result["market_cap"]:
                result["market_cap_cr"] = round(result["market_cap"] / 10_000_000, 0)

        # yfinance supplement
        yf_info = get_stock_info(symbol)
        if yf_info:
            result["ev_ebitda"] = _safe_float(yf_info.get("enterpriseToEbitda"))
            result["revenue_growth"] = _pct(yf_info.get("revenueGrowth"))
            result["earnings_growth"] = _pct(yf_info.get("earningsGrowth"))
            if result["pe_ratio"] is None:
                result["pe_ratio"] = _safe_float(yf_info.get("trailingPE"))
            if result["price_to_book"] is None:
                result["price_to_book"] = _safe_float(yf_info.get("priceToBook"))
            if result["sector"] == "Unknown":
                result["sector"] = yf_info.get("sector", "Unknown") or "Unknown"

    # ── Source 2: MCP market.get_ownership ──────────────────────────────────
    # get_ownership accepts .NS/.BO suffix (unlike get_fundamentals/get_indicators)
    mcp_own = mcp_safe("market.get_ownership", {"symbol": symbol})
    if mcp_own and isinstance(mcp_own, dict):
        result["promoter_holding"] = _safe_float(mcp_own.get("promoter_pct"))
        result["institutional_holding"] = _safe_float(mcp_own.get("institutional_pct"))
    else:
        # Fallback: yfinance major_holders
        ownership = get_ownership_data(symbol)
        if ownership:
            for key, val in ownership.items():
                key_lower = str(key).lower()
                if "insider" in key_lower or "promoter" in key_lower:
                    result["promoter_holding"] = _pct(val)
                elif "institution" in key_lower:
                    result["institutional_holding"] = _pct(val)

    # ── Source 3: Interest Coverage / FCF from MCP market.get_financials ────
    mcp_fin = mcp_safe("market.get_financials", {"symbol": bare_symbol})
    if mcp_fin and isinstance(mcp_fin, dict):
        # MCP returns income_stmt, balance_sheet, cashflow as dicts
        # Try to extract interest coverage if present
        ic = mcp_fin.get("interest_coverage")
        if ic is not None:
            result["interest_coverage"] = _safe_float(ic)
        fcf = mcp_fin.get("free_cash_flow")
        if fcf is not None:
            result["free_cash_flow"] = _safe_float(fcf)
    else:
        # Fallback: yfinance financials
        fin_data = get_financial_statements(symbol)
        if fin_data:
            if fin_data.get("interest_coverage") is not None:
                result["interest_coverage"] = fin_data["interest_coverage"]
            if fin_data.get("free_cash_flow") is not None:
                result["free_cash_flow"] = fin_data["free_cash_flow"]

    # Estimate IC if still missing
    if result.get("interest_coverage") is None:
        if result["operating_margin"] and result["debt_to_equity"]:
            de = result["debt_to_equity"]
            result["interest_coverage"] = (
                round(result["operating_margin"] / de, 2) if de > 0 else 99.0
            )

    return result


def compute_fundamental_score(data: dict, horizon: str | None = None) -> float:
    """
    Weighted scoring system from final-arch.md, now HORIZON-AWARE.

    The same raw metrics are weighted differently per horizon (see
    app/core/horizon_params._FUNDAMENTAL_WEIGHTS):
        SHORT — fundamentals matter little; growth/quality de-emphasised.
        MID   — balanced (the original 3x/2x/1x weighting).
        LONG  — quality, growth, moat and balance-sheet strength dominate.

    Each metric scores 0-4 points based on the SAME quality thresholds; only
    the per-metric multiplier changes. The result is normalised to /40 against
    the actual weights used, so the score (and therefore the signal) shifts
    with horizon even though the underlying numbers are identical.

    Returns: float score out of 40.
    """
    weights = fundamental_weights(horizon)

    def w(metric: str) -> float:
        return weights.get(metric, 1.0)

    total_score = 0.0
    total_weight = 0.0

    # ── Crisis-sensitive solvency metrics ─────────────────────
    # Debt/Equity: lower is better
    de = data.get("debt_to_equity")
    if de is not None:
        wt = w("debt_to_equity")
        if de < 0.5:
            total_score += 4 * wt
        elif de < 1.0:
            total_score += 3 * wt
        elif de < 1.5:
            total_score += 2 * wt
        elif de < 2.5:
            total_score += 1 * wt
        # else 0
        total_weight += wt

    # Interest Coverage: higher is better
    ic = data.get("interest_coverage")
    if ic is not None:
        wt = w("interest_coverage")
        if ic > 10:
            total_score += 4 * wt
        elif ic > 5:
            total_score += 3 * wt
        elif ic > 2:
            total_score += 2 * wt
        elif ic > 1:
            total_score += 1 * wt
        total_weight += wt

    # ── Quality / growth metrics ──────────────────────────────
    # ROE: higher is better
    roe = data.get("roe")
    if roe is not None:
        wt = w("roe")
        if roe > 20:
            total_score += 4 * wt
        elif roe > 15:
            total_score += 3 * wt
        elif roe > 10:
            total_score += 2 * wt
        elif roe > 5:
            total_score += 1 * wt
        total_weight += wt

    # Revenue Growth: higher is better
    rg = data.get("revenue_growth")
    if rg is not None:
        wt = w("revenue_growth")
        if rg > 20:
            total_score += 4 * wt
        elif rg > 10:
            total_score += 3 * wt
        elif rg > 5:
            total_score += 2 * wt
        elif rg > 0:
            total_score += 1 * wt
        total_weight += wt

    # P/E: lower is better (but not negative)
    pe = data.get("pe_ratio")
    if pe is not None and pe > 0:
        wt = w("pe_ratio")
        if pe < 15:
            total_score += 4 * wt
        elif pe < 25:
            total_score += 3 * wt
        elif pe < 35:
            total_score += 2 * wt
        elif pe < 50:
            total_score += 1 * wt
        total_weight += wt

    # ROCE: higher is better
    roce = data.get("roce")
    if roce is not None:
        wt = w("roce")
        if roce > 20:
            total_score += 4 * wt
        elif roce > 12:
            total_score += 3 * wt
        elif roce > 8:
            total_score += 2 * wt
        elif roce > 4:
            total_score += 1 * wt
        total_weight += wt

    # Net Margin: higher is better
    nm = data.get("net_margin")
    if nm is not None:
        wt = w("net_margin")
        if nm > 20:
            total_score += 4 * wt
        elif nm > 12:
            total_score += 3 * wt
        elif nm > 6:
            total_score += 2 * wt
        elif nm > 0:
            total_score += 1 * wt
        total_weight += wt

    # Earnings Growth: higher is better
    eg = data.get("earnings_growth")
    if eg is not None:
        wt = w("earnings_growth")
        if eg > 25:
            total_score += 4 * wt
        elif eg > 10:
            total_score += 3 * wt
        elif eg > 0:
            total_score += 2 * wt
        elif eg > -10:
            total_score += 1 * wt
        total_weight += wt

    # Promoter Holding: higher is better
    ph = data.get("promoter_holding")
    if ph is not None:
        wt = w("promoter_holding")
        if ph > 60:
            total_score += 4 * wt
        elif ph > 45:
            total_score += 3 * wt
        elif ph > 30:
            total_score += 2 * wt
        elif ph > 15:
            total_score += 1 * wt
        total_weight += wt

    # Dividend Yield: presence is a positive signal
    dy = data.get("dividend_yield")
    if dy is not None:
        wt = w("dividend_yield")
        if dy > 3:
            total_score += 4 * wt
        elif dy > 2:
            total_score += 3 * wt
        elif dy > 1:
            total_score += 2 * wt
        elif dy > 0:
            total_score += 1 * wt
        total_weight += wt

    # Normalize to a score out of 40
    if total_weight > 0:
        # Max possible per unit weight = 4, so max = total_weight * 4
        max_possible = total_weight * 4
        normalized = (total_score / max_possible) * 40
        return round(normalized, 1)

    return 20.0  # Neutral fallback if no data


def score_to_signal(score: float) -> str:
    """Convert fundamental score to BUY/SELL/HOLD signal."""
    if score > 24:
        return "BUY"
    elif score >= 14:
        return "HOLD"
    else:
        return "SELL"


def _safe_float(val) -> Optional[float]:
    """Convert to float safely."""
    if val is None:
        return None
    try:
        import math

        f = float(val)
        return None if math.isnan(f) else round(f, 2)
    except (ValueError, TypeError):
        return None


def _pct(val) -> Optional[float]:
    """Convert decimal ratio (0.104) to percentage (10.4)."""
    if val is None:
        return None
    try:
        import math

        f = float(val)
        if math.isnan(f):
            return None
        # If value looks like a decimal ratio (< 5), convert to percentage
        if -5 < f < 5:
            return round(f * 100, 2)
        return round(f, 2)
    except (ValueError, TypeError):
        return None
