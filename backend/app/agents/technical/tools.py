"""
Technical Agent â€” Tools (MCP-first)
Data-fetching and indicator computation. No LLM here.
Step 1: MCP market.get_indicators (RSI, MACD, ADX, EMA, BB, VWAP, ATR, Stoch, CCI)
Step 1b: TradingView screener fallback for live indicators
Step 2: MCP market.get_ohlcv (3y OHLCV for pivots, 52W, ATR fallback)
Step 2b: yfinance fallback for OHLCV
Step 3: MCP market.get_vix_nifty for Nifty relative strength (or yfinance)
"""

import pandas as pd
import numpy as np
from app.services.screener_service import get_stock_fundamentals
from app.core.config import logger
from app.services.mcp_client import mcp_safe
from app.core.horizon_params import technical_params, normalize_horizon
from typing import Optional
import math


def get_technical_data(symbol: str, horizon: str | None = None) -> dict:
    """
    Gathers ALL technical data for a single stock.
    Returns a flat dict ready for prompt formatting.

    `horizon` (SHORT/MID/LONG) tunes the OHLCV lookback and the
    pivot/return analysis windows so the data genuinely differs per horizon.
    Live indicators (RSI/MACD/EMA from MCP get_indicators) are point-in-time
    and horizon-independent by design.
    """
    horizon = normalize_horizon(horizon)
    hp = technical_params(horizon)
    result = {
        "symbol": symbol,
        "horizon": horizon,
        "ohlcv_period": hp["ohlcv_period"],
        "current_price": None,
        "atr": None,
        "ema20": None,
        "ema50": None,
        "ema200": None,
        "rsi": None,
        "rsi7": None,
        "macd": None,
        "adx": None,
        "stoch_k": None,
        "stoch_d": None,
        "cci": None,
        "momentum": None,
        "bb_upper": None,
        "bb_lower": None,
        "vwap": None,
        "perf_w": None,
        "perf_1m": None,
        "perf_3m": None,
        "perf_6m": None,
        "perf_y": None,
        "high_52w": None,
        "low_52w": None,
        "resistance_levels": [],
        "support_levels": [],
        "trading_days": 0,
        "price_vs_ema20": "N/A",
        "price_vs_ema50": "N/A",
        "price_vs_ema200": "N/A",
        "dist_from_high": None,
        # NOTE: stock_3m_return / nifty_3m_return now span the horizon-tuned
        # window (return_window_days), not a fixed 3 months. Keys kept for
        # backward-compat with the prompt/node; the window is reported below.
        "return_window_days": hp["return_days"],
        "stock_3m_return": None,
        "nifty_3m_return": None,
        "relative_strength": "N/A",
    }

    bare_symbol = symbol.replace(".NS", "").replace(".BO", "")
    # â”€â”€ Step 1: MCP market.get_indicators (live indicators) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    mcp_ind = mcp_safe("market.get_indicators", {"symbol": bare_symbol})
    if mcp_ind and isinstance(mcp_ind, dict):
        result["current_price"] = _safe_float(
            mcp_ind.get("close") or mcp_ind.get("price")
        )
        result["atr"] = _safe_float(mcp_ind.get("ATR"))
        result["ema20"] = _safe_float(mcp_ind.get("EMA20"))
        result["ema50"] = _safe_float(mcp_ind.get("EMA50"))
        result["ema200"] = _safe_float(mcp_ind.get("EMA200"))
        result["rsi"] = _safe_float(mcp_ind.get("RSI"))
        result["rsi7"] = _safe_float(mcp_ind.get("RSI7"))
        result["macd"] = _safe_float(mcp_ind.get("MACD") or mcp_ind.get("MACD.macd"))
        result["adx"] = _safe_float(mcp_ind.get("ADX"))
        result["stoch_k"] = _safe_float(mcp_ind.get("Stoch.K"))
        result["stoch_d"] = _safe_float(mcp_ind.get("Stoch.D"))
        result["cci"] = _safe_float(mcp_ind.get("CCI") or mcp_ind.get("CCI20"))
        result["momentum"] = _safe_float(mcp_ind.get("Mom"))
        result["bb_upper"] = _safe_float(mcp_ind.get("BB.upper"))
        result["bb_lower"] = _safe_float(mcp_ind.get("BB.lower"))
        result["vwap"] = _safe_float(mcp_ind.get("VWAP"))
        result["perf_w"] = _safe_float(mcp_ind.get("Perf.W"))
        result["perf_1m"] = _safe_float(mcp_ind.get("Perf.1M"))
        result["perf_3m"] = _safe_float(mcp_ind.get("Perf.3M"))
        result["perf_6m"] = _safe_float(mcp_ind.get("Perf.6M"))
        result["perf_y"] = _safe_float(mcp_ind.get("Perf.Y"))
        logger.info(f"[green]Technical: live indicators from MCP for {symbol}[/green]")
    else:
        # â”€â”€ Step 1b: TradingView screener fallback â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        logger.warning(
            f"[yellow]Technical: MCP indicators failed for {symbol}, trying TradingView[/yellow]"
        )
        tv_data = get_stock_fundamentals(symbol)
        if tv_data:
            result["current_price"] = _safe_float(tv_data.get("close"))
            result["atr"] = _safe_float(tv_data.get("ATR"))
            result["ema20"] = _safe_float(tv_data.get("EMA20"))
            result["ema50"] = _safe_float(tv_data.get("EMA50"))
            result["ema200"] = _safe_float(tv_data.get("EMA200"))
            result["rsi"] = _safe_float(tv_data.get("RSI"))
            result["rsi7"] = _safe_float(tv_data.get("RSI7"))
            result["macd"] = _safe_float(tv_data.get("MACD.macd"))
            result["adx"] = _safe_float(tv_data.get("ADX"))
            result["stoch_k"] = _safe_float(tv_data.get("Stoch.K"))
            result["stoch_d"] = _safe_float(tv_data.get("Stoch.D"))
            result["cci"] = _safe_float(tv_data.get("CCI20"))
            result["momentum"] = _safe_float(tv_data.get("Mom"))
            result["bb_upper"] = _safe_float(tv_data.get("BB.upper"))
            result["bb_lower"] = _safe_float(tv_data.get("BB.lower"))
            result["vwap"] = _safe_float(tv_data.get("VWAP"))
            result["perf_w"] = _safe_float(tv_data.get("Perf.W"))
            result["perf_1m"] = _safe_float(tv_data.get("Perf.1M"))
            result["perf_3m"] = _safe_float(tv_data.get("Perf.3M"))
            result["perf_6m"] = _safe_float(tv_data.get("Perf.6M"))
            result["perf_y"] = _safe_float(tv_data.get("Perf.Y"))

    # Price vs EMA relationships (computed from whatever source populated them)
    price = result["current_price"]
    if price:
        if result["ema20"]:
            result["price_vs_ema20"] = "ABOVE" if price > result["ema20"] else "BELOW"
        if result["ema50"]:
            result["price_vs_ema50"] = "ABOVE" if price > result["ema50"] else "BELOW"
        if result["ema200"]:
            result["price_vs_ema200"] = "ABOVE" if price > result["ema200"] else "BELOW"

    # â”€â”€ Step 2: OHLCV for pivots / 52W / ATR fallback â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    ohlcv = _get_ohlcv(symbol, period=hp["ohlcv_period"])
    if ohlcv is not None and not ohlcv.empty:
        result["trading_days"] = len(ohlcv)

        if isinstance(ohlcv.columns, pd.MultiIndex):
            ohlcv.columns = ohlcv.columns.get_level_values(0)
        ohlcv = ohlcv.loc[:, ~ohlcv.columns.duplicated()]

        # Price fallback
        if result["current_price"] is None:
            try:
                close_val = ohlcv["Close"].iloc[-1]
                if isinstance(close_val, pd.Series):
                    close_val = close_val.iloc[0]
                result["current_price"] = _safe_float(close_val)
                logger.info(
                    f"[yellow]Technical: Using OHLCV fallback price for {symbol}[/yellow]"
                )
            except Exception:
                pass

        # RSI fallback from OHLCV
        if result["rsi"] is None and len(ohlcv) >= 15:
            try:
                delta = ohlcv["Close"].diff()
                gain = delta.where(delta > 0, 0).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                rs = gain / loss.replace(0, np.nan)
                result["rsi"] = round(float((100 - (100 / (1 + rs))).iloc[-1]), 2)
            except Exception:
                pass

        if result["ema20"] is None:
            try:
                result["ema20"] = round(
                    float(ohlcv["Close"].ewm(span=20).mean().iloc[-1]), 2
                )
            except Exception:
                pass
        if result["ema50"] is None:
            try:
                result["ema50"] = round(
                    float(ohlcv["Close"].ewm(span=50).mean().iloc[-1]), 2
                )
            except Exception:
                pass
        if result["ema200"] is None:
            try:
                result["ema200"] = round(
                    float(ohlcv["Close"].ewm(span=200).mean().iloc[-1]), 2
                )
            except Exception:
                pass

        if result["atr"] is None and len(ohlcv) >= 15:
            try:
                h = ohlcv["High"]
                l = ohlcv["Low"]
                c = ohlcv["Close"]
                tr = pd.concat(
                    [h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1
                ).max(axis=1)
                result["atr"] = round(float(tr.rolling(14).mean().iloc[-1]), 2)
            except Exception:
                pass

        # Re-compute price vs EMA after any OHLCV fills
        price = result["current_price"]
        if price:
            if result["ema20"]:
                result["price_vs_ema20"] = (
                    "ABOVE" if price > result["ema20"] else "BELOW"
                )
            if result["ema50"]:
                result["price_vs_ema50"] = (
                    "ABOVE" if price > result["ema50"] else "BELOW"
                )
            if result["ema200"]:
                result["price_vs_ema200"] = (
                    "ABOVE" if price > result["ema200"] else "BELOW"
                )

        # 52-week high/low
        one_year_ago = ohlcv.index[-1] - pd.Timedelta(days=365)
        yearly_data = ohlcv[ohlcv.index >= one_year_ago]
        if not yearly_data.empty:
            result["high_52w"] = round(float(yearly_data["High"].max()), 2)
            result["low_52w"] = round(float(yearly_data["Low"].min()), 2)
            if result["current_price"] and result["high_52w"]:
                result["dist_from_high"] = round(
                    (
                        (result["current_price"] - result["high_52w"])
                        / result["high_52w"]
                    )
                    * 100,
                    2,
                )

        # Support/Resistance from pivot points (window tuned per horizon)
        result["resistance_levels"] = _compute_resistance_levels(
            ohlcv, window=hp["pivot_window"]
        )
        result["support_levels"] = _compute_support_levels(
            ohlcv, window=hp["pivot_window"]
        )

        # Stock return over the horizon-appropriate lookback
        lookback_days = hp["return_days"]
        lookback_start = ohlcv.index[-1] - pd.Timedelta(days=lookback_days)
        lookback_data = ohlcv[ohlcv.index >= lookback_start]
        if len(lookback_data) >= 2:
            s = float(lookback_data["Close"].iloc[0])
            e = float(lookback_data["Close"].iloc[-1])
            if s > 0:
                result["stock_3m_return"] = round(((e - s) / s) * 100, 2)

    # â”€â”€ Step 3: Nifty relative strength â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    nifty_ohlcv = _get_nifty_ohlcv()
    if nifty_ohlcv is not None and not nifty_ohlcv.empty:
        if isinstance(nifty_ohlcv.columns, pd.MultiIndex):
            nifty_ohlcv.columns = nifty_ohlcv.columns.get_level_values(0)
        # Match the same lookback window used for the stock so the comparison
        # is apples-to-apples for this horizon.
        nifty_lookback_start = nifty_ohlcv.index[-1] - pd.Timedelta(
            days=hp["return_days"]
        )
        nifty_3m = nifty_ohlcv[nifty_ohlcv.index >= nifty_lookback_start]
        if len(nifty_3m) >= 2:
            n_start = float(nifty_3m["Close"].iloc[0])
            n_end = float(nifty_3m["Close"].iloc[-1])
            if n_start > 0:
                result["nifty_3m_return"] = round(
                    ((n_end - n_start) / n_start) * 100, 2
                )

    if result["stock_3m_return"] is not None and result["nifty_3m_return"] is not None:
        diff = result["stock_3m_return"] - result["nifty_3m_return"]
        if diff > 5:
            result["relative_strength"] = f"OUTPERFORMING Nifty by {diff:.1f}%"
        elif diff < -5:
            result["relative_strength"] = f"UNDERPERFORMING Nifty by {abs(diff):.1f}%"
        else:
            result["relative_strength"] = f"IN LINE with Nifty (diff: {diff:.1f}%)"

    # Final sanitization
    for key, val in result.items():
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            result[key] = None

    return result


# â”€â”€ Data fetch helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def _get_ohlcv(symbol: str, period: str = "3y") -> Optional[pd.DataFrame]:
    """Try MCP market.get_ohlcv first, fall back to yfinance. `period` is
    horizon-tuned by the caller (floored at 1y to protect 52W/ema200)."""
    bare_symbol = symbol.replace(".NS", "").replace(".BO", "")
    mcp_data = mcp_safe("market.get_ohlcv", {"symbol": bare_symbol, "period": period})
    if mcp_data and isinstance(mcp_data, dict) and "data" in mcp_data:
        try:
            df = pd.DataFrame(mcp_data["data"])
            if not df.empty:
                df.index = pd.to_datetime(
                    df.index
                    if df.index.dtype == "datetime64[ns]"
                    else df.get("Date", df.index)
                )
                df = df.sort_index()
                # Normalise column names
                df.columns = [c.capitalize() for c in df.columns]
                return df
        except Exception as e:
            logger.warning(
                f"[yellow]Technical: MCP OHLCV parse failed for {symbol}: {e}[/yellow]"
            )

    # yfinance fallback
    from app.services.yfinance_service import get_ohlcv_3y

    return get_ohlcv_3y(symbol, period=period)


def _get_nifty_ohlcv() -> Optional[pd.DataFrame]:
    """Try MCP market.get_ohlcv for ^NSEI, fall back to yfinance."""
    mcp_data = mcp_safe("market.get_ohlcv", {"symbol": "NIFTY", "period": "1y"})
    if mcp_data and isinstance(mcp_data, dict) and "data" in mcp_data:
        try:
            df = pd.DataFrame(mcp_data["data"])
            if not df.empty:
                df.index = pd.to_datetime(df.index)
                df.columns = [c.capitalize() for c in df.columns]
                return df.sort_index()
        except Exception:
            pass

    try:
        import yfinance as yf

        df = yf.download("^NSEI", period="6mo", interval="1d", progress=False)
        return df if not df.empty else None
    except Exception as e:
        logger.warning(f"[yellow]Technical: Nifty OHLCV failed: {e}[/yellow]")
        return None


# â”€â”€ Pivot helpers (unchanged) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def _compute_resistance_levels(df: pd.DataFrame, window: int = 60) -> list[float]:
    try:
        highs = df["High"].rolling(window=window, center=True).max()
        recent = highs.tail(130).dropna().unique()
        levels = sorted(set(round(float(h), 2) for h in recent), reverse=True)
        return _cluster_levels(levels)[:3]
    except Exception:
        return []


def _compute_support_levels(df: pd.DataFrame, window: int = 60) -> list[float]:
    try:
        lows = df["Low"].rolling(window=window, center=True).min()
        recent = lows.tail(130).dropna().unique()
        levels = sorted(set(round(float(l), 2) for l in recent))
        return _cluster_levels(levels)[:3]
    except Exception:
        return []


def _cluster_levels(levels: list[float], threshold: float = 0.01) -> list[float]:
    if not levels:
        return []
    clustered = [levels[0]]
    for level in levels[1:]:
        if abs(level - clustered[-1]) / max(clustered[-1], 1) > threshold:
            clustered.append(level)
    return clustered


def _safe_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        f = float(val)
        return None if math.isnan(f) else round(f, 2)
    except (ValueError, TypeError):
        return None
