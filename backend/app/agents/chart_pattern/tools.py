"""
Chart Pattern Agent — Tools
Pulls OHLCV and produces a structural summary that the LLM can interpret
into pattern names. We deliberately keep math here lightweight (POC):
candlestick basics, swing highs/lows, recent range.
"""

import pandas as pd
import numpy as np
from app.services.yfinance_service import get_ohlcv_3y
from app.core.horizon_params import chart_pattern_params, normalize_horizon
from app.core.config import logger


def _safe_last(series, default=None):
    try:
        v = series.iloc[-1]
        if hasattr(v, "iloc"):
            v = v.iloc[0]
        return float(v)
    except Exception:
        return default


def _swings(df: pd.DataFrame, window: int = 10) -> dict:
    try:
        highs = df["High"].rolling(window).max().dropna().tail(40).tolist()
        lows = df["Low"].rolling(window).min().dropna().tail(40).tolist()
        return {
            "recent_swing_highs": [round(float(x), 2) for x in highs[-5:]],
            "recent_swing_lows": [round(float(x), 2) for x in lows[-5:]],
        }
    except Exception:
        return {"recent_swing_highs": [], "recent_swing_lows": []}


def _candle_tags(df: pd.DataFrame) -> list[str]:
    """Very light candlestick tags from the last 3 candles."""
    tags: list[str] = []
    try:
        last = df.tail(3)
        for _, row in last.iterrows():
            o = float(row["Open"])
            c = float(row["Close"])
            h = float(row["High"])
            l = float(row["Low"])
            body = abs(c - o)
            rng = max(h - l, 1e-9)
            upper = h - max(o, c)
            lower = min(o, c) - l
            if body / rng < 0.1:
                tags.append("doji")
            elif lower > 2 * body and upper < body:
                tags.append("hammer")
            elif upper > 2 * body and lower < body:
                tags.append("shooting_star")
            elif c > o and body / rng > 0.6:
                tags.append("bull_marubozu")
            elif c < o and body / rng > 0.6:
                tags.append("bear_marubozu")
    except Exception:
        pass
    return tags


def get_chart_pattern_data(symbol: str, horizon: str | None = None) -> dict:
    """Build a flat dict the chart-pattern prompt can format into.

    The OHLCV lookback and swing-detection window are tuned per horizon so
    SHORT/MID/LONG genuinely see different structure (6mo/1y/3y).
    """
    horizon = normalize_horizon(horizon)
    cparams = chart_pattern_params(horizon)
    out: dict = {
        "symbol": symbol,
        "horizon": horizon,
        "ohlcv_period": cparams["ohlcv_period"],
        "trading_days": 0,
        "current_price": None,
        "high_52w": None,
        "low_52w": None,
        "dist_from_high_pct": None,
        "dist_from_low_pct": None,
        "candle_tags": [],
        "recent_swing_highs": [],
        "recent_swing_lows": [],
        "weekly_close": None,
        "weekly_change_8w_pct": None,
    }

    try:
        df = get_ohlcv_3y(symbol, period=cparams["ohlcv_period"])
        if df is None or df.empty:
            return out
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.loc[:, ~df.columns.duplicated()]
        df = df.dropna(subset=["Close"])

        out["trading_days"] = len(df)
        out["current_price"] = round(_safe_last(df["Close"], default=0.0), 2)

        one_year = df.index[-1] - pd.Timedelta(days=365)
        yearly = df[df.index >= one_year]
        if not yearly.empty:
            out["high_52w"] = round(float(yearly["High"].max()), 2)
            out["low_52w"] = round(float(yearly["Low"].min()), 2)
            cp = out["current_price"] or 0.0
            if out["high_52w"]:
                out["dist_from_high_pct"] = round(
                    ((cp - out["high_52w"]) / out["high_52w"]) * 100, 2
                )
            if out["low_52w"]:
                out["dist_from_low_pct"] = round(
                    ((cp - out["low_52w"]) / out["low_52w"]) * 100, 2
                )

        out.update(_swings(df, window=cparams["swing_window"]))
        out["candle_tags"] = _candle_tags(df)

        # Weekly snapshot (resample)
        try:
            weekly = df["Close"].resample("W").last().dropna()
            if len(weekly) >= 8:
                out["weekly_close"] = round(float(weekly.iloc[-1]), 2)
                w0 = float(weekly.iloc[-8])
                w1 = float(weekly.iloc[-1])
                if w0 > 0:
                    out["weekly_change_8w_pct"] = round(((w1 - w0) / w0) * 100, 2)
        except Exception:
            pass

    except Exception as e:
        logger.warning(f"[yellow]Chart Pattern data failed for {symbol}: {e}[/yellow]")

    return out
