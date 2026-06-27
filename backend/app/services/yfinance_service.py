"""
yfinance Service — Wraps yfinance for OHLCV, fundamentals, and ownership data.
Ref: research_results.md
"""

import time

try:
    import yfinance as yf

    _YFINANCE_AVAILABLE = True
except ImportError:
    yf = None
    _YFINANCE_AVAILABLE = False
import pandas as pd
from app.core.config import logger
from typing import Optional

# Max concurrent yfinance downloads are implicitly throttled by the dispatcher's
# MAX_CONCURRENT=5. This retry wrapper handles transient 401/429 from Yahoo.
_YF_MAX_RETRIES = 3
_YF_BASE_DELAY = 1.0  # seconds; doubles on each retry


def _ensure_ns_suffix(symbol: str) -> str:
    """Ensure the symbol has .NS suffix for NSE tickers."""
    symbol = symbol.upper().strip()
    if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
        symbol = f"{symbol}.NS"
    return symbol


def _download_with_retry(ticker: str, **kwargs) -> pd.DataFrame:
    """Wrapper around yf.download that retries on HTTP 401/429 with backoff."""
    if yf is None:
        logger.warning(
            f"[yellow]yfinance is not installed; skipping download for {ticker}[/yellow]"
        )
        return pd.DataFrame()
    last_err = None
    for attempt in range(_YF_MAX_RETRIES):
        try:
            df = yf.download(ticker, progress=False, **kwargs)
            return df
        except Exception as e:
            err_str = str(e)
            # Retry on auth/rate-limit errors from Yahoo
            if "401" in err_str or "429" in err_str or "Unauthorized" in err_str:
                delay = _YF_BASE_DELAY * (2**attempt)
                logger.warning(
                    f"[yellow]yfinance {ticker}: {err_str[:80]}… retrying in {delay}s "
                    f"(attempt {attempt + 1}/{_YF_MAX_RETRIES})[/yellow]"
                )
                last_err = e
                time.sleep(delay)
                continue
            raise  # non-retryable error
    # All retries exhausted — return empty DataFrame so callers can fallback
    logger.error(
        f"[red]yfinance {ticker}: all {_YF_MAX_RETRIES} retries exhausted: {last_err}[/red]"
    )
    return pd.DataFrame()


def get_ohlcv_3y(symbol: str, period: str = "3y") -> Optional[pd.DataFrame]:
    """
    Download daily OHLCV for a symbol.
    `period` defaults to 3y for backward compatibility but accepts any
    yfinance period (e.g. "1y", "2y", "3y") so callers can fetch a
    horizon-appropriate lookback. Kept the name `get_ohlcv_3y` to avoid
    breaking existing imports.
    Returns DataFrame with columns: Open, High, Low, Close, Volume
    Close IS already split-adjusted (confirmed in research).
    """
    ticker = _ensure_ns_suffix(symbol)
    try:
        df = _download_with_retry(ticker, period=period, interval="1d")
        if df.empty:
            # Try BSE (.BO) fallback
            alt_ticker = ticker.replace(".NS", ".BO")
            logger.warning(
                f"[yellow]{ticker} returned empty. Trying {alt_ticker}[/yellow]"
            )
            df = _download_with_retry(alt_ticker, period=period, interval="1d")

        if df.empty:
            logger.error(f"[red]No OHLCV data for {symbol}[/red]")
            return None

        logger.info(
            f"[green]OHLCV {symbol}: {len(df)} rows ({df.index[0].strftime('%Y-%m-%d')} to {df.index[-1].strftime('%Y-%m-%d')})[/green]"
        )
        return df

    except Exception as e:
        logger.error(f"[red]yfinance OHLCV failed for {symbol}: {e}[/red]")
        return None


def get_stock_info(symbol: str) -> Optional[dict]:
    """
    Get fundamental info from yfinance .info
    Returns fields like revenueGrowth, earningsGrowth, margins, EV/EBITDA, beta.
    """
    if yf is None:
        logger.warning(
            f"[yellow]yfinance is not installed; skipping info fetch for {symbol}[/yellow]"
        )
        return None
    ticker_str = _ensure_ns_suffix(symbol)
    try:
        ticker = yf.Ticker(ticker_str)
        info = ticker.info

        # Extract the fields we care about
        fields = [
            "marketCap",
            "trailingPE",
            "forwardPE",
            "priceToBook",
            "debtToEquity",
            "dividendYield",
            "enterpriseToEbitda",
            "earningsGrowth",
            "revenueGrowth",
            "profitMargins",
            "operatingMargins",
            "grossMargins",
            "sector",
            "industry",
            "fiftyTwoWeekHigh",
            "fiftyTwoWeekLow",
            "beta",
        ]

        result = {}
        for field in fields:
            result[field] = info.get(field)

        return result

    except Exception as e:
        logger.error(f"[red]yfinance .info failed for {symbol}: {e}[/red]")
        return None


def get_ownership_data(symbol: str) -> Optional[dict]:
    """
    Get promoter holding (insidersPercentHeld) and institutional data.
    Confirmed working in research for Indian stocks.
    """
    if yf is None:
        logger.warning(
            f"[yellow]yfinance is not installed; skipping ownership fetch for {symbol}[/yellow]"
        )
        return None
    ticker_str = _ensure_ns_suffix(symbol)
    try:
        ticker = yf.Ticker(ticker_str)
        holders = ticker.major_holders

        if holders is None or holders.empty:
            return None

        result = {}
        # major_holders has columns: ['Breakdown', 'Value'] (or index-based)
        for _, row in holders.iterrows():
            key = row.iloc[0] if isinstance(row.iloc[0], str) else str(row.name)
            val = row.iloc[1] if len(row) > 1 else row.iloc[0]
            result[key] = val

        return result

    except Exception as e:
        logger.error(f"[red]yfinance ownership failed for {symbol}: {e}[/red]")
        return None


def get_vix_nifty() -> dict:
    """
    Fetch current India VIX and Nifty 50 levels.
    Used by Market Pulse Agent.
    """
    result = {"india_vix": None, "nifty_level": None, "nifty_change": None}
    if yf is None:
        logger.warning(
            "[yellow]yfinance is not installed; skipping VIX/Nifty fetch[/yellow]"
        )
        return result

    try:
        vix_df = yf.download("^INDIAVIX", period="5d", interval="1d", progress=False)
        if not vix_df.empty:
            result["india_vix"] = round(float(vix_df["Close"].iloc[-1].item()), 2)
    except Exception as e:
        logger.warning(f"[yellow]Failed to fetch India VIX: {e}[/yellow]")

    try:
        nifty_df = yf.download("^NSEI", period="5d", interval="1d", progress=False)
        if not nifty_df.empty:
            result["nifty_level"] = round(float(nifty_df["Close"].iloc[-1].item()), 2)
            if len(nifty_df) >= 2:
                prev = float(nifty_df["Close"].iloc[-2].item())
                curr = float(nifty_df["Close"].iloc[-1].item())
                result["nifty_change"] = round(((curr - prev) / prev) * 100, 2)
    except Exception as e:
        logger.warning(f"[yellow]Failed to fetch Nifty 50: {e}[/yellow]")

    return result


def get_financial_statements(symbol: str) -> Optional[dict]:
    """
    Get Interest Coverage and FCF from yfinance .financials + .balance_sheet.
    Research confirmed: 50 line items × 4 years in .financials,
    77 line items × 4 years in .balance_sheet.

    Returns:
        dict with interest_coverage, free_cash_flow, or None on failure.
    """
    if yf is None:
        logger.warning(
            f"[yellow]yfinance is not installed; skipping financials fetch for {symbol}[/yellow]"
        )
        return None
    ticker_str = _ensure_ns_suffix(symbol)
    try:
        ticker = yf.Ticker(ticker_str)
        result = {"interest_coverage": None, "free_cash_flow": None}

        # Interest Coverage = EBIT / Interest Expense
        financials = ticker.financials
        if financials is not None and not financials.empty:
            # Get the most recent year column
            latest = financials.columns[0] if len(financials.columns) > 0 else None
            if latest is not None:
                ebit = None
                interest_expense = None

                # Try multiple row name variants
                for name in ["EBIT", "Operating Income"]:
                    if name in financials.index:
                        ebit = financials.loc[name, latest]
                        break

                for name in ["Interest Expense", "Interest Expense Non Operating"]:
                    if name in financials.index:
                        interest_expense = financials.loc[name, latest]
                        break

                if ebit is not None and interest_expense is not None:
                    ie = abs(float(interest_expense))
                    if ie > 0:
                        result["interest_coverage"] = round(float(ebit) / ie, 2)
                    else:
                        result["interest_coverage"] = 99.0  # No interest expense

        # Free Cash Flow = Operating Cash Flow - CapEx
        cashflow = ticker.cashflow
        if cashflow is not None and not cashflow.empty:
            latest_cf = cashflow.columns[0] if len(cashflow.columns) > 0 else None
            if latest_cf is not None:
                ocf = None
                capex = None

                for name in [
                    "Total Cash From Operating Activities",
                    "Operating Cash Flow",
                ]:
                    if name in cashflow.index:
                        ocf = cashflow.loc[name, latest_cf]
                        break

                for name in ["Capital Expenditures", "Capital Expenditure"]:
                    if name in cashflow.index:
                        capex = cashflow.loc[name, latest_cf]
                        break

                if ocf is not None and capex is not None:
                    result["free_cash_flow"] = round(
                        float(ocf) + float(capex), 2
                    )  # CapEx is negative

        return result

    except Exception as e:
        logger.warning(f"[yellow]yfinance financials failed for {symbol}: {e}[/yellow]")
        return None
