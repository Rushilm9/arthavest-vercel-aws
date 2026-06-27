"""
Discovery Agent — Tools (F1 Stages 6-7)

Stage 6 — Hard Filters (pure rules):
  mcap ≥ ₹500 Cr, avg vol ≥ 5L, price ≥ ₹50

Stage 7 — Broad Scan (3-signature union in one TradingView query):
  S1 (SHORT, momentum):  rel_vol > 2 AND RSI 50-75 AND close > VWAP
  S2 (MID, earnings):    Perf.3M > 5 AND RSI 40-65 AND market_cap > 50bn
  S3 (LONG, compounder): ROE > 15 AND D/E < 1 AND market_cap > 100bn

Signatures are unioned via a single OR group; filters are applied AFTER the
hard filter floor.
"""

from typing import Optional
import pandas as pd

from tradingview_screener import Query, Column
from app.core.config import logger, settings
from app.services.screener_service import (
    FUNDAMENTAL_FIELDS,
    TECHNICAL_FIELDS,
    PERFORMANCE_FIELDS,
    VOLUME_FIELDS,
    META_FIELDS,
    get_discovery_scan,
)


# ── Hard Filter constants (Stage 6) — sourced from config for env-var override ──
HARD_MIN_MCAP = settings.DISCOVERY_HARD_MIN_MCAP  # ₹500 Cr default
HARD_MIN_AVG_VOL = settings.DISCOVERY_HARD_MIN_AVG_VOL  # 5 lakh shares avg vol default
HARD_MIN_PRICE = settings.DISCOVERY_HARD_MIN_PRICE  # ₹50 default


def broad_scan(limit: int = 60) -> Optional[pd.DataFrame]:
    """
    Stage 7 — TradingView broad scan with hard filters + 3-signature union.
    Falls back to the legacy momentum scan if the union scan fails.
    """
    select_fields = list(
        set(
            [
                "close",
                "change",
                "volume",
                "relative_volume_10d_calc",
                "average_volume_30d_calc",
                "RSI",
                "VWAP",
                "price_earnings_ttm",
                "price_book_fq",
                "return_on_equity",
                "debt_to_equity",
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
                "after_tax_margin",
                "dividend_yield_recent",
            ]
        )
    )

    try:
        # Hard filters
        hard = [
            Column("market_cap_basic") > HARD_MIN_MCAP,
            Column("average_volume_30d_calc") > HARD_MIN_AVG_VOL,
            Column("close") > HARD_MIN_PRICE,
        ]

        # Build query — TV-screener supports AND-of-conditions per where().
        # We approximate the union by running 3 lighter queries and concatenating,
        # because a clean OR DSL isn't reliably exposed across versions.
        signatures = []

        # ── S1: SHORT momentum ──
        # Threshold: rel_vol > 1.5 (down from 2.0) to capture momentum stocks
        # on lower-volume sessions while still filtering out flat-volume stocks.
        s1_empty = True
        try:
            q1 = (
                Query()
                .set_markets("india")
                .select(*select_fields)
                .where(
                    *hard,
                    Column("relative_volume_10d_calc") > 1.5,
                    Column("RSI") > 50,
                    Column("RSI") < 75,
                    Column("close") > Column("VWAP"),
                )
                .order_by("relative_volume_10d_calc", ascending=False)
                .limit(limit)
            )
            _, df1 = q1.get_scanner_data()
            if df1 is not None and not df1.empty:
                df1 = df1.copy()
                df1["_signature"] = "SHORT"
                signatures.append(df1)
                s1_empty = False
        except Exception as e:
            logger.warning(f"[yellow]Broad scan S1 (SHORT) failed: {e}[/yellow]")

        # ── S2: MID earnings/momentum ──
        try:
            q2 = (
                Query()
                .set_markets("india")
                .select(*select_fields)
                .where(
                    *hard,
                    Column("Perf.3M") > 5,
                    Column("RSI") > 40,
                    Column("RSI") < 65,
                    Column("market_cap_basic") > 50_000_000_000,
                )
                .order_by("Perf.3M", ascending=False)
                .limit(limit)
            )
            _, df2 = q2.get_scanner_data()
            if df2 is not None and not df2.empty:
                df2 = df2.copy()
                df2["_signature"] = "MID"
                signatures.append(df2)
        except Exception as e:
            logger.warning(f"[yellow]Broad scan S2 (MID) failed: {e}[/yellow]")

        # ── S3: LONG compounder ──
        try:
            q3 = (
                Query()
                .set_markets("india")
                .select(*select_fields)
                .where(
                    *hard,
                    Column("return_on_equity") > 15,
                    Column("debt_to_equity") < 1,
                    Column("market_cap_basic") > 100_000_000_000,
                )
                .order_by("return_on_equity", ascending=False)
                .limit(limit)
            )
            _, df3 = q3.get_scanner_data()
            if df3 is not None and not df3.empty:
                df3 = df3.copy()
                df3["_signature"] = "LONG"
                signatures.append(df3)
        except Exception as e:
            logger.warning(f"[yellow]Broad scan S3 (LONG) failed: {e}[/yellow]")

        if not signatures:
            logger.warning(
                "[yellow]Broad scan: all 3 signatures returned empty — falling back[/yellow]"
            )
            return None

        union = pd.concat(signatures, ignore_index=True)

        # De-dup by ticker, keep first signature seen
        if "ticker" in union.columns:
            union = union.drop_duplicates(subset=["ticker"], keep="first")

        # Fallback: if S1 returned nothing (low-volume session), promote the
        # top-5 highest-relVol stocks from the union to SHORT so the LLM
        # always has momentum candidates to evaluate.
        if s1_empty and "relative_volume_10d_calc" in union.columns:
            top_rv = (
                union[union["RSI"].between(48, 78)]
                .nlargest(5, "relative_volume_10d_calc")
                .index
            )
            union.loc[top_rv, "_signature"] = "SHORT"
            logger.info(
                f"[yellow]S1 fallback: promoted {len(top_rv)} stocks to SHORT by relVol[/yellow]"
            )

        logger.info(
            f"[green]Broad scan union: {len(union)} unique stocks "
            f"(S1={sum(union['_signature'] == 'SHORT')}, "
            f"S2={sum(union['_signature'] == 'MID')}, "
            f"S3={sum(union['_signature'] == 'LONG')})[/green]"
        )
        return union

    except Exception as e:
        logger.error(f"[red]Broad scan failed: {e}[/red]")
        return None


def scan_market(filters: Optional[dict] = None) -> tuple[list[str], list[dict]]:
    """
    Top-level scan used by both the legacy /discover path and the new
    broad-scan path. If `filters` is provided we honor the legacy momentum
    scan; otherwise we run the new 3-signature union.
    """
    if filters:
        # Legacy path — preserved for backward compatibility
        scan_params = {
            "min_market_cap": HARD_MIN_MCAP,
            "min_relative_volume": 1.5,
            "rsi_min": 40,
            "rsi_max": 65,
            "limit": 30,
            **filters,
        }
        df = get_discovery_scan(**scan_params)
    else:
        df = broad_scan(limit=60)
        if df is None or df.empty:
            # Final fallback to legacy scan so we always return *something*
            df = get_discovery_scan()

    if df is None or df.empty:
        logger.warning("[yellow]Discovery scan returned 0 results[/yellow]")
        return [], []

    symbols: list[str] = []
    stock_data: list[dict] = []
    for _, row in df.iterrows():
        raw_ticker = row.get("ticker", "")
        clean_symbol = (
            raw_ticker.split(":")[-1] if ":" in str(raw_ticker) else str(raw_ticker)
        )
        symbols.append(clean_symbol)
        row_dict = row.to_dict()
        row_dict["clean_symbol"] = clean_symbol
        stock_data.append(row_dict)

    logger.info(
        f"[green]Discovery found {len(symbols)} stocks: {symbols[:5]}...[/green]"
    )
    return symbols, stock_data
