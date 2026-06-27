"""
Smart Money Concepts (SMC) — Tools
Pure Python math for: Fair Value Gap, Liquidity Sweeps, Order Flow (CMF),
Anchored VWAP, and Volume Profile.

All computations use Daily OHLCV data (from yfinance) and pandas/numpy.
Designed for Swing Trading (2–6 week holds).
"""

import pandas as pd
import numpy as np
from app.services.yfinance_service import get_ohlcv_3y
from app.core.config import logger
from typing import Optional


# ══════════════════════════════════════════════════════════════
# MASTER ENTRY POINT
# ══════════════════════════════════════════════════════════════


def run_smc_analysis(
    symbol: str,
    strategies: list[str],
) -> dict:
    """
    Run selected SMC strategies on a single stock.

    Args:
        symbol: Stock ticker (e.g. "RELIANCE")
        strategies: List of strategy keys to run. Valid keys:
            "fvg", "liquidity_sweep", "order_flow", "avwap", "volume_profile"

    Returns:
        dict with results per strategy + overall SMC score.
    """
    logger.info(
        f"[bold cyan]SMC Analysis: Starting for {symbol} | Strategies: {strategies}[/bold cyan]"
    )

    result = {
        "symbol": symbol,
        "strategies_requested": strategies,
        "strategies_results": {},
        "smc_score": 0,
        "smc_signal": "NEUTRAL",
        "current_price": None,
        "error": None,
    }

    # ── Fetch OHLCV data (shared across all strategies) ───────
    df = get_ohlcv_3y(symbol)
    if df is None or df.empty:
        result["error"] = f"No OHLCV data available for {symbol}"
        logger.error(f"[red]SMC: No data for {symbol}[/red]")
        return result

    # Flatten multi-level columns if present (yfinance returns MultiIndex)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    # Deduplicate column names (yfinance can return duplicate 'Close', etc.)
    df = df.loc[:, ~df.columns.duplicated()]

    # Drop rows where all OHLCV are NaN
    df = df.dropna(subset=["Close", "High", "Low", "Open"], how="all")

    # Trim to last 6 months for SMC swing analysis
    six_months_ago = df.index[-1] - pd.Timedelta(days=180)
    df_6m = df[df.index >= six_months_ago].copy()

    # Fill any remaining NaN in Volume with 0
    df_6m["Volume"] = df_6m["Volume"].fillna(0)
    # Forward-fill small price gaps, then drop any remaining NaN rows
    df_6m[["Open", "High", "Low", "Close"]] = df_6m[
        ["Open", "High", "Low", "Close"]
    ].ffill()
    df_6m = df_6m.dropna(subset=["Close", "High", "Low"])

    if len(df_6m) < 30:
        result["error"] = (
            f"Insufficient data for {symbol} (need >= 30 days, got {len(df_6m)})"
        )
        return result

    try:
        close_val = df_6m["Close"].iloc[-1]
        if isinstance(close_val, pd.Series):
            close_val = close_val.iloc[0]
        result["current_price"] = round(float(close_val), 2)
    except Exception:
        pass

    # ── Run each selected strategy ────────────────────────────
    total_score = 0
    strategies_run = 0

    strategy_map = {
        "fvg": ("Fair Value Gap", find_fair_value_gaps),
        "liquidity_sweep": ("Liquidity Sweep", detect_liquidity_sweeps),
        "order_flow": ("Order Flow (CMF)", calculate_order_flow),
        "avwap": ("Anchored VWAP", calculate_anchored_vwap),
        "volume_profile": ("Volume Profile", calculate_volume_profile),
    }

    for key in strategies:
        key_lower = key.lower().strip()
        if key_lower not in strategy_map:
            logger.warning(f"[yellow]SMC: Unknown strategy '{key}', skipping[/yellow]")
            continue

        name, func = strategy_map[key_lower]
        try:
            strategy_result = func(df_6m)
            result["strategies_results"][key_lower] = strategy_result
            total_score += strategy_result.get("score", 0)
            strategies_run += 1
            logger.info(
                f"[green]SMC: {name} completed for {symbol} → score {strategy_result.get('score', 0)}[/green]"
            )
        except Exception as e:
            logger.error(f"[red]SMC: {name} failed for {symbol}: {e}[/red]")
            result["strategies_results"][key_lower] = {"error": str(e), "score": 0}

    # ── Compute overall SMC score (0-100) ─────────────────────
    if strategies_run > 0:
        # Each strategy scores 0-100; average them
        result["smc_score"] = round(total_score / strategies_run, 1)

    # Determine signal based on score
    score = result["smc_score"]
    if score >= 70:
        result["smc_signal"] = "STRONG_BUY"
    elif score >= 55:
        result["smc_signal"] = "BUY"
    elif score >= 40:
        result["smc_signal"] = "NEUTRAL"
    elif score >= 25:
        result["smc_signal"] = "SELL"
    else:
        result["smc_signal"] = "STRONG_SELL"

    logger.info(
        f"[bold green]SMC Analysis Done: {symbol} → "
        f"Score: {result['smc_score']}, Signal: {result['smc_signal']}[/bold green]"
    )
    return result


# ══════════════════════════════════════════════════════════════
# 1. FAIR VALUE GAP (FVG)
# ══════════════════════════════════════════════════════════════


def find_fair_value_gaps(df: pd.DataFrame) -> dict:
    """
    Detect Bullish and Bearish Fair Value Gaps (3-candle imbalance).

    Bullish FVG: Day3.Low > Day1.High (gap between Day1 High and Day3 Low)
    Bearish FVG: Day3.High < Day1.Low (gap between Day1 Low and Day3 High)

    Also checks if gaps are "mitigated" (price has since revisited the zone).

    Returns:
        dict with bullish_fvgs, bearish_fvgs, active count, and score.
    """
    highs = df["High"].values
    lows = df["Low"].values
    closes = df["Close"].values
    dates = df.index

    bullish_fvgs = []
    bearish_fvgs = []

    for i in range(2, len(df)):
        # Bullish FVG: gap up — Day3 Low is above Day1 High
        if lows[i] > highs[i - 2]:
            gap_top = lows[i]
            gap_bottom = highs[i - 2]
            gap_size_pct = round(((gap_top - gap_bottom) / gap_bottom) * 100, 2)

            # Check if mitigated (any subsequent candle dipped into the gap)
            mitigated = False
            if i + 1 < len(df):
                future_lows = lows[i + 1 :]
                if len(future_lows) > 0 and np.any(future_lows <= gap_top):
                    mitigated = True

            bullish_fvgs.append(
                {
                    "date": str(dates[i].date()),
                    "gap_top": round(float(gap_top), 2),
                    "gap_bottom": round(float(gap_bottom), 2),
                    "gap_size_pct": gap_size_pct,
                    "mitigated": mitigated,
                }
            )

        # Bearish FVG: gap down — Day3 High is below Day1 Low
        if highs[i] < lows[i - 2]:
            gap_top = lows[i - 2]
            gap_bottom = highs[i]
            gap_size_pct = round(((gap_top - gap_bottom) / gap_top) * 100, 2)

            mitigated = False
            if i + 1 < len(df):
                future_highs = highs[i + 1 :]
                if len(future_highs) > 0 and np.any(future_highs >= gap_bottom):
                    mitigated = True

            bearish_fvgs.append(
                {
                    "date": str(dates[i].date()),
                    "gap_top": round(float(gap_top), 2),
                    "gap_bottom": round(float(gap_bottom), 2),
                    "gap_size_pct": gap_size_pct,
                    "mitigated": mitigated,
                }
            )

    # Only keep the most recent 10 FVGs
    bullish_fvgs = bullish_fvgs[-10:]
    bearish_fvgs = bearish_fvgs[-10:]

    active_bullish = sum(1 for f in bullish_fvgs if not f["mitigated"])
    active_bearish = sum(1 for f in bearish_fvgs if not f["mitigated"])

    # Score: bullish FVGs = positive, bearish FVGs = negative
    # More unmitigated bullish → higher score
    current_price = float(closes[-1])
    nearby_bullish = sum(
        1
        for f in bullish_fvgs
        if not f["mitigated"] and f["gap_top"] <= current_price * 1.05
    )
    nearby_bearish = sum(
        1
        for f in bearish_fvgs
        if not f["mitigated"] and f["gap_bottom"] >= current_price * 0.95
    )

    if nearby_bullish > 0 and nearby_bearish == 0:
        score = min(80 + nearby_bullish * 5, 100)
    elif nearby_bearish > 0 and nearby_bullish == 0:
        score = max(20 - nearby_bearish * 5, 0)
    elif nearby_bullish > nearby_bearish:
        score = 60 + (nearby_bullish - nearby_bearish) * 5
    elif nearby_bearish > nearby_bullish:
        score = 40 - (nearby_bearish - nearby_bullish) * 5
    else:
        score = 50

    return {
        "bullish_fvgs": bullish_fvgs,
        "bearish_fvgs": bearish_fvgs,
        "active_bullish_count": active_bullish,
        "active_bearish_count": active_bearish,
        "nearby_bullish": nearby_bullish,
        "nearby_bearish": nearby_bearish,
        "score": max(0, min(100, score)),
        "interpretation": (
            f"{active_bullish} unmitigated bullish FVGs, "
            f"{active_bearish} unmitigated bearish FVGs. "
            f"{'Bullish bias — price near demand zones.' if score > 55 else 'Bearish bias — price near supply zones.' if score < 45 else 'Neutral — no dominant FVG bias.'}"
        ),
    }


# ══════════════════════════════════════════════════════════════
# 2. LIQUIDITY SWEEPS
# ══════════════════════════════════════════════════════════════


def detect_liquidity_sweeps(df: pd.DataFrame, pivot_window: int = 20) -> dict:
    """
    Detect Liquidity Sweeps: wicks that pierce swing highs/lows but
    fail to close beyond them (stop hunts).

    Bullish Sweep: Wick below swing low, close above it (buy-side grab).
    Bearish Sweep: Wick above swing high, close below it (sell-side grab).

    Returns:
        dict with sweeps list, recent activity, and score.
    """
    highs = df["High"].values
    lows = df["Low"].values
    closes = df["Close"].values
    opens = df["Open"].values
    dates = df.index

    # Compute rolling pivot highs and lows
    rolling_high = pd.Series(highs).rolling(window=pivot_window).max().values
    rolling_low = pd.Series(lows).rolling(window=pivot_window).min().values

    bullish_sweeps = []
    bearish_sweeps = []

    for i in range(pivot_window, len(df)):
        prev_swing_low = rolling_low[i - 1]
        prev_swing_high = rolling_high[i - 1]

        # Bullish Sweep: wick goes below the swing low, but closes above it
        if lows[i] < prev_swing_low and closes[i] > prev_swing_low:
            sweep_depth = round(((prev_swing_low - lows[i]) / prev_swing_low) * 100, 3)
            bullish_sweeps.append(
                {
                    "date": str(dates[i].date()),
                    "sweep_low": round(float(lows[i]), 2),
                    "pivot_level": round(float(prev_swing_low), 2),
                    "close": round(float(closes[i]), 2),
                    "sweep_depth_pct": sweep_depth,
                    "type": "bullish",
                }
            )

        # Bearish Sweep: wick goes above the swing high, but closes below it
        if highs[i] > prev_swing_high and closes[i] < prev_swing_high:
            sweep_depth = round(
                ((highs[i] - prev_swing_high) / prev_swing_high) * 100, 3
            )
            bearish_sweeps.append(
                {
                    "date": str(dates[i].date()),
                    "sweep_high": round(float(highs[i]), 2),
                    "pivot_level": round(float(prev_swing_high), 2),
                    "close": round(float(closes[i]), 2),
                    "sweep_depth_pct": sweep_depth,
                    "type": "bearish",
                }
            )

    # Keep recent 10
    bullish_sweeps = bullish_sweeps[-10:]
    bearish_sweeps = bearish_sweeps[-10:]

    # Check for very recent sweeps (last 5 trading days)
    recent_bullish = sum(
        1 for s in bullish_sweeps if s["date"] >= str(dates[-5].date())
    )
    recent_bearish = sum(
        1 for s in bearish_sweeps if s["date"] >= str(dates[-5].date())
    )

    # Score
    if recent_bullish > 0 and recent_bearish == 0:
        score = 75 + recent_bullish * 5
    elif recent_bearish > 0 and recent_bullish == 0:
        score = 25 - recent_bearish * 5
    elif len(bullish_sweeps) > len(bearish_sweeps):
        score = 60
    elif len(bearish_sweeps) > len(bullish_sweeps):
        score = 40
    else:
        score = 50

    return {
        "bullish_sweeps": bullish_sweeps,
        "bearish_sweeps": bearish_sweeps,
        "recent_bullish": recent_bullish,
        "recent_bearish": recent_bearish,
        "total_bullish": len(bullish_sweeps),
        "total_bearish": len(bearish_sweeps),
        "score": max(0, min(100, score)),
        "interpretation": (
            f"{len(bullish_sweeps)} bullish sweeps, {len(bearish_sweeps)} bearish sweeps detected. "
            f"{'Recent bullish sweep — institutions may be accumulating.' if recent_bullish > 0 else ''}"
            f"{'Recent bearish sweep — distribution possible.' if recent_bearish > 0 else ''}"
            f"{'No recent sweep activity.' if recent_bullish == 0 and recent_bearish == 0 else ''}"
        ),
    }


# ══════════════════════════════════════════════════════════════
# 3. ORDER FLOW (Chaikin Money Flow Approximation)
# ══════════════════════════════════════════════════════════════


def calculate_order_flow(df: pd.DataFrame, period: int = 20) -> dict:
    """
    Approximate institutional order flow using Chaikin Money Flow (CMF).

    CMF = Sum(MF Volume, period) / Sum(Volume, period)
    where MF Multiplier = ((Close - Low) - (High - Close)) / (High - Low)
    and MF Volume = MF Multiplier × Volume

    CMF > +0.05: Institutional accumulation (buying)
    CMF < -0.05: Institutional distribution (selling)

    Returns:
        dict with CMF value, trend direction, and score.
    """
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    close = df["Close"].astype(float)
    volume = df["Volume"].astype(float)

    # Money Flow Multiplier
    hl_range = high - low
    hl_range = hl_range.replace(0, np.nan)  # Avoid division by zero
    mf_multiplier = ((close - low) - (high - close)) / hl_range
    mf_multiplier = mf_multiplier.fillna(0)

    # Money Flow Volume
    mf_volume = mf_multiplier * volume

    # CMF = Rolling Sum(MF Volume) / Rolling Sum(Volume)
    cmf = mf_volume.rolling(window=period).sum() / volume.rolling(window=period).sum()
    cmf = cmf.fillna(0)

    current_cmf = round(float(cmf.iloc[-1]), 4)
    prev_cmf = round(float(cmf.iloc[-5]) if len(cmf) >= 5 else 0, 4)
    cmf_trend = "RISING" if current_cmf > prev_cmf else "FALLING"

    # CMF history (last 20 values for charting)
    cmf_history = [
        {"date": str(df.index[i].date()), "cmf": round(float(cmf.iloc[i]), 4)}
        for i in range(max(0, len(cmf) - 20), len(cmf))
        if not np.isnan(cmf.iloc[i])
    ]

    # Score
    if current_cmf > 0.15:
        score = 90
        flow = "HEAVY_ACCUMULATION"
    elif current_cmf > 0.05:
        score = 70
        flow = "ACCUMULATION"
    elif current_cmf > -0.05:
        score = 50
        flow = "NEUTRAL"
    elif current_cmf > -0.15:
        score = 30
        flow = "DISTRIBUTION"
    else:
        score = 10
        flow = "HEAVY_DISTRIBUTION"

    # Bonus for rising CMF
    if cmf_trend == "RISING" and current_cmf > 0:
        score = min(score + 10, 100)
    elif cmf_trend == "FALLING" and current_cmf < 0:
        score = max(score - 10, 0)

    return {
        "cmf_current": current_cmf,
        "cmf_previous": prev_cmf,
        "cmf_trend": cmf_trend,
        "flow_type": flow,
        "cmf_history": cmf_history,
        "score": score,
        "interpretation": (
            f"CMF at {current_cmf:.4f} ({cmf_trend}). "
            f"{'Institutions are actively buying — strong demand.' if flow == 'HEAVY_ACCUMULATION' else ''}"
            f"{'Moderate institutional buying detected.' if flow == 'ACCUMULATION' else ''}"
            f"{'No clear institutional bias.' if flow == 'NEUTRAL' else ''}"
            f"{'Institutions appear to be selling.' if flow == 'DISTRIBUTION' else ''}"
            f"{'Heavy institutional selling — avoid.' if flow == 'HEAVY_DISTRIBUTION' else ''}"
        ),
    }


# ══════════════════════════════════════════════════════════════
# 4. ANCHORED VWAP (AVWAP)
# ══════════════════════════════════════════════════════════════


def calculate_anchored_vwap(df: pd.DataFrame) -> dict:
    """
    Compute Anchored VWAP from the highest volume day in the last 90 trading days.

    AVWAP = Cumulative(Typical Price × Volume) / Cumulative(Volume)
    where Typical Price = (High + Low + Close) / 3

    Returns:
        dict with anchor date, AVWAP level, price position, and score.
    """
    # Find anchor: highest volume day in last 90 trading sessions
    lookback = min(90, len(df))
    recent = df.tail(lookback).copy()

    # Clean volume data — fill NaN and ensure float
    recent["Volume"] = pd.to_numeric(recent["Volume"], errors="coerce").fillna(0)
    df_clean = df.copy()
    df_clean["Volume"] = pd.to_numeric(df_clean["Volume"], errors="coerce").fillna(0)
    for col in ["High", "Low", "Close"]:
        df_clean[col] = pd.to_numeric(df_clean[col], errors="coerce")
    df_clean = df_clean.dropna(subset=["High", "Low", "Close"])

    anchor_idx = recent["Volume"].idxmax()
    anchor_pos = df_clean.index.get_loc(anchor_idx)

    # Compute AVWAP from anchor forward
    avwap_slice = df_clean.iloc[anchor_pos:].copy()
    typical_price = (
        avwap_slice["High"].astype(float)
        + avwap_slice["Low"].astype(float)
        + avwap_slice["Close"].astype(float)
    ) / 3
    vol_float = avwap_slice["Volume"].astype(float)
    cum_tp_vol = (typical_price * vol_float).cumsum()
    cum_vol = vol_float.cumsum()

    # Guard against division by zero
    cum_vol = cum_vol.replace(0, np.nan)
    avwap = cum_tp_vol / cum_vol
    avwap = avwap.ffill().fillna(0)

    current_avwap = round(float(avwap.iloc[-1]), 2)
    current_price = round(float(df_clean["Close"].iloc[-1]), 2)

    # Guard against NaN/zero AVWAP
    if current_avwap == 0 or np.isnan(current_avwap):
        return {
            "anchor_date": str(anchor_idx.date())
            if hasattr(anchor_idx, "date")
            else str(anchor_idx),
            "anchor_volume": 0,
            "avwap_level": 0,
            "current_price": current_price,
            "position": "UNKNOWN",
            "distance_pct": 0,
            "avwap_history": [],
            "score": 50,
            "interpretation": "AVWAP calculation failed — insufficient volume data.",
        }

    # Price position relative to AVWAP
    distance_pct = round(((current_price - current_avwap) / current_avwap) * 100, 2)

    if current_price > current_avwap:
        position = "ABOVE"
    else:
        position = "BELOW"

    # AVWAP history for charting (skip NaN values)
    avwap_history = []
    for i in range(max(0, len(avwap) - 30), len(avwap)):
        val = float(avwap.iloc[i])
        if not np.isnan(val) and val > 0:
            avwap_history.append(
                {"date": str(avwap.index[i].date()), "avwap": round(val, 2)}
            )

    # Score
    if position == "ABOVE" and abs(distance_pct) < 2:
        score = 80
    elif position == "ABOVE" and distance_pct > 2:
        score = 65
    elif position == "BELOW" and abs(distance_pct) < 2:
        score = 35
    elif position == "BELOW":
        score = 20
    else:
        score = 50

    # Safely convert anchor volume
    try:
        anchor_vol = int(float(recent.loc[anchor_idx, "Volume"]))
    except (ValueError, TypeError):
        anchor_vol = 0

    return {
        "anchor_date": str(anchor_idx.date())
        if hasattr(anchor_idx, "date")
        else str(anchor_idx),
        "anchor_volume": anchor_vol,
        "avwap_level": current_avwap,
        "current_price": current_price,
        "position": position,
        "distance_pct": distance_pct,
        "avwap_history": avwap_history,
        "score": score,
        "interpretation": (
            f"AVWAP anchored from {str(anchor_idx.date()) if hasattr(anchor_idx, 'date') else anchor_idx} "
            f"(highest volume day). Current AVWAP: ₹{current_avwap}. "
            f"Price is {position} by {abs(distance_pct):.1f}%. "
            f"{'Strong support — price holding above AVWAP.' if position == 'ABOVE' and distance_pct < 3 else ''}"
            f"{'Price extended above AVWAP — may revert.' if position == 'ABOVE' and distance_pct >= 3 else ''}"
            f"{'Bearish — price trading below institutional average cost.' if position == 'BELOW' else ''}"
        ),
    }


# ══════════════════════════════════════════════════════════════
# 5. VOLUME PROFILE
# ══════════════════════════════════════════════════════════════


def calculate_volume_profile(df: pd.DataFrame, num_bins: int = 50) -> dict:
    """
    Compute Volume Profile over the last 6 months of daily data.

    Divides the price range into `num_bins` equal bins, distributes
    each day's volume across the bins, and identifies the:
    - Point of Control (POC): price level with highest volume
    - Value Area High (VAH): upper bound of 70% volume zone
    - Value Area Low (VAL): lower bound of 70% volume zone

    Returns:
        dict with POC, VA, profile data, and score.
    """
    # Clean data — convert to numeric and drop NaN
    df_vp = df.copy()
    for col in ["High", "Low", "Close", "Volume"]:
        df_vp[col] = pd.to_numeric(df_vp[col], errors="coerce")
    df_vp["Volume"] = df_vp["Volume"].fillna(0)
    df_vp = df_vp.dropna(subset=["High", "Low", "Close"])

    if len(df_vp) < 10:
        return {"error": "Insufficient clean data for volume profile", "score": 50}

    prices_high = df_vp["High"].astype(float).values
    prices_low = df_vp["Low"].astype(float).values
    prices_close = df_vp["Close"].astype(float).values
    volumes = df_vp["Volume"].astype(float).values

    price_min = float(np.nanmin(prices_low))
    price_max = float(np.nanmax(prices_high))

    if np.isnan(price_min) or np.isnan(price_max) or price_max <= price_min:
        return {"error": "No valid price range to compute profile", "score": 50}

    # Create price bins
    bin_edges = np.linspace(price_min, price_max, num_bins + 1)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
    bin_volumes = np.zeros(num_bins)

    # Distribute each day's volume across its price range
    for i in range(len(df_vp)):
        day_low = prices_low[i]
        day_high = prices_high[i]
        day_vol = volumes[i]

        # Skip NaN rows
        if np.isnan(day_low) or np.isnan(day_high) or np.isnan(day_vol):
            continue

        # Find which bins this day's range covers
        low_bin = int(np.searchsorted(bin_edges, day_low, side="right")) - 1
        high_bin = int(np.searchsorted(bin_edges, day_high, side="right")) - 1

        low_bin = max(0, min(low_bin, num_bins - 1))
        high_bin = max(0, min(high_bin, num_bins - 1))

        # Distribute volume equally across covered bins
        num_covered = high_bin - low_bin + 1
        if num_covered > 0:
            vol_per_bin = day_vol / num_covered
            bin_volumes[low_bin : high_bin + 1] += vol_per_bin

    # Point of Control (POC) = bin with max volume
    poc_idx = int(np.argmax(bin_volumes))
    poc_price = round(float(bin_centers[poc_idx]), 2)

    # Value Area: find the bins containing 70% of total volume
    total_volume = np.sum(bin_volumes)
    target_volume = total_volume * 0.70

    # Expand outward from POC
    va_low_idx = poc_idx
    va_high_idx = poc_idx
    current_volume = bin_volumes[poc_idx]

    while current_volume < target_volume and (
        va_low_idx > 0 or va_high_idx < num_bins - 1
    ):
        expand_low = bin_volumes[va_low_idx - 1] if va_low_idx > 0 else 0
        expand_high = bin_volumes[va_high_idx + 1] if va_high_idx < num_bins - 1 else 0

        if expand_low >= expand_high and va_low_idx > 0:
            va_low_idx -= 1
            current_volume += bin_volumes[va_low_idx]
        elif va_high_idx < num_bins - 1:
            va_high_idx += 1
            current_volume += bin_volumes[va_high_idx]
        else:
            va_low_idx -= 1
            current_volume += bin_volumes[va_low_idx]

    val_price = round(float(bin_centers[va_low_idx]), 2)  # Value Area Low
    vah_price = round(float(bin_centers[va_high_idx]), 2)  # Value Area High

    current_price = round(float(prices_close[-1]), 2)

    # Build profile data (top 20 bins by volume for the response)
    profile_data = []
    sorted_indices = np.argsort(-bin_volumes)[:20]
    for idx in sorted(sorted_indices):
        profile_data.append(
            {
                "price_level": round(float(bin_centers[idx]), 2),
                "volume": round(float(bin_volumes[idx]), 0),
                "is_poc": bool(idx == poc_idx),
                "in_value_area": bool(va_low_idx <= idx <= va_high_idx),
            }
        )

    # Score based on price position relative to POC and Value Area
    if val_price <= current_price <= vah_price:
        # Inside value area
        if abs(current_price - poc_price) / poc_price < 0.01:
            score = 50  # Right at POC, could go either way
        elif current_price > poc_price:
            score = 60  # Above POC but inside VA
        else:
            score = 40  # Below POC but inside VA
    elif current_price > vah_price:
        # Above value area = bullish breakout
        dist = ((current_price - vah_price) / vah_price) * 100
        score = min(75 + int(dist * 2), 95)
    else:
        # Below value area = bearish breakdown
        dist = ((val_price - current_price) / val_price) * 100
        score = max(25 - int(dist * 2), 5)

    return {
        "poc_price": poc_price,
        "value_area_high": vah_price,
        "value_area_low": val_price,
        "current_price": current_price,
        "price_position": (
            "ABOVE_VA"
            if current_price > vah_price
            else "BELOW_VA"
            if current_price < val_price
            else "INSIDE_VA"
        ),
        "profile_data": profile_data,
        "score": score,
        "interpretation": (
            f"POC: ₹{poc_price}, Value Area: ₹{val_price} – ₹{vah_price}. "
            f"{'Price ABOVE Value Area — bullish breakout territory.' if current_price > vah_price else ''}"
            f"{'Price BELOW Value Area — bearish, looking for support.' if current_price < val_price else ''}"
            f"{'Price INSIDE Value Area — consolidation zone, watch for breakout direction.' if val_price <= current_price <= vah_price else ''}"
        ),
    }
