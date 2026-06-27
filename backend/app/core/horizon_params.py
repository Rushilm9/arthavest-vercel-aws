"""
Horizon → data-fetch parameters (single source of truth).

The F1/F2 pipeline classifies each idea as SHORT / MID / LONG. Until now the
specialist tools fetched the SAME raw data regardless of horizon (hardcoded
period="3y", days=7), so the test-agent debugger showed identical Input Data
for every horizon — the bug this module fixes.

The deployed MCP server (market.get_ohlcv, news.get_stock_news) already honours
`period` and `days` dynamically (verified: 3mo→61 rows, 6mo→124, 1y→249,
3y→741). So the mapping lives HERE, in the consumer codebase, not in MCP.

Design notes (why not just "SHORT → 3mo"):
  - Technical derives ema200 (OHLCV fallback), 52-week high/low and a 3-month
    return from the OHLCV frame. A 3-month fetch can't produce any of those and
    would silently degrade SHORT to nulls. So the OHLCV *fetch* is floored at 1y
    and we instead vary the *analysis windows* (pivot/swing window, return
    lookback) by horizon. That makes raw_data genuinely differ per horizon
    without breaking long-lookback features.
  - Chart-pattern is computed purely from the dataframe (no 52w/ema200 fallback
    to protect), so its fetch can vary fully (6mo / 1y / 3y).
  - News/sentiment `days` is a clean swap; floored at 7 so thin-coverage stocks
    don't return an empty feed on SHORT.
"""

from __future__ import annotations

# Canonical horizons
_HORIZONS = ("SHORT", "MID", "LONG")


def normalize_horizon(horizon: str | None) -> str:
    """Coerce arbitrary input to one of SHORT / MID / LONG (default MID)."""
    h = (horizon or "").strip().upper()
    return h if h in _HORIZONS else "MID"


# ── Technical agent ─────────────────────────────────────────────────────────
# Floor the OHLCV fetch at 1y so high_52w / low_52w / ema200-fallback stay
# honest; vary the lookback windows so derived raw_data still moves per horizon.
_TECHNICAL = {
    "SHORT": {"ohlcv_period": "1y", "pivot_window": 20, "return_days": 30},
    "MID": {"ohlcv_period": "2y", "pivot_window": 60, "return_days": 90},
    "LONG": {"ohlcv_period": "3y", "pivot_window": 120, "return_days": 180},
}

# ── Chart-pattern agent ─────────────────────────────────────────────────────
# Safe to vary the fetch fully — everything is derived from the frame.
_CHART_PATTERN = {
    "SHORT": {"ohlcv_period": "6mo", "swing_window": 5},
    "MID": {"ohlcv_period": "1y", "swing_window": 10},
    "LONG": {"ohlcv_period": "3y", "swing_window": 20},
}

# ── News / sentiment agents ─────────────────────────────────────────────────
# `days` controls the RSS recency window on the MCP server. Floored at 7.
_NEWS_DAYS = {"SHORT": 7, "MID": 14, "LONG": 30}

# ── Fundamental agent ───────────────────────────────────────────────────────
# Fundamental RAW metrics (PE, ROE, D/E, …) are company facts — they do NOT
# change with a trading horizon, and the MCP server has no time-window param
# for them. So horizon variance comes from how the SAME metrics are WEIGHTED
# in the score, which mirrors real investing:
#   SHORT — fundamentals barely matter for a days/weeks trade; solvency still
#           counts a little, growth/quality are de-emphasised.
#   MID   — balanced (this is the original 3x/2x/1x weighting).
#   LONG  — quality, growth, moat and balance-sheet strength dominate.
# Each key is a per-metric multiplier consumed by compute_fundamental_score().
# Metrics absent from a profile fall back to 1.0.
_FUNDAMENTAL_WEIGHTS = {
    "SHORT": {
        "debt_to_equity": 2.0,
        "interest_coverage": 2.0,
        "roe": 1.0,
        "revenue_growth": 1.0,
        "pe_ratio": 1.5,
        "roce": 1.0,
        "net_margin": 1.0,
        "earnings_growth": 1.0,
        "promoter_holding": 1.0,
        "dividend_yield": 1.0,
    },
    "MID": {
        "debt_to_equity": 3.0,
        "interest_coverage": 3.0,
        "roe": 2.0,
        "revenue_growth": 2.0,
        "pe_ratio": 1.0,
        "roce": 1.0,
        "net_margin": 1.0,
        "earnings_growth": 1.0,
        "promoter_holding": 1.0,
        "dividend_yield": 1.0,
    },
    "LONG": {
        "debt_to_equity": 3.0,
        "interest_coverage": 3.0,
        "roe": 3.0,
        "revenue_growth": 3.0,
        "pe_ratio": 1.0,
        "roce": 2.5,
        "net_margin": 2.0,
        "earnings_growth": 2.5,
        "promoter_holding": 2.0,
        "dividend_yield": 1.5,
    },
}


def technical_params(horizon: str | None) -> dict:
    return _TECHNICAL[normalize_horizon(horizon)]


def chart_pattern_params(horizon: str | None) -> dict:
    return _CHART_PATTERN[normalize_horizon(horizon)]


def news_days(horizon: str | None) -> int:
    return _NEWS_DAYS[normalize_horizon(horizon)]


def fundamental_weights(horizon: str | None) -> dict:
    """Per-metric scoring multipliers for the given horizon. Metrics not
    listed default to 1.0 in compute_fundamental_score()."""
    return _FUNDAMENTAL_WEIGHTS[normalize_horizon(horizon)]
