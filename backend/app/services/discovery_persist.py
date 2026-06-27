"""
F1 Persistence — writes discovery, economic, and market regime results to DB.
Called from the discovery route after run_discovery_pipeline() returns.
"""

import uuid
import datetime
import pytz
from typing import Optional

_IST = pytz.timezone("Asia/Kolkata")


def _ist_today() -> datetime.date:
    return datetime.datetime.now(_IST).date()


from app.core.config import logger, SessionLocal
from app.core.verdict import final_verdict
from app.db.models import (
    DiscoveryResults,
    EconomicSnapshots,
    MarketRegimes,
    Runs,
    Stocks,
)


def persist_discovery_run(run_id: str, result: dict, buckets: dict) -> int:
    """
    Persist all discovered stocks from F1 to the discovery_results table.
    Idempotent — unique constraint on (run_id, horizon, symbol) prevents duplicates.
    Returns the number of rows inserted.
    """
    if not SessionLocal:
        logger.warning("[yellow]Discovery persist: DB not available[/yellow]")
        return 0

    macro_regime = result.get("macro_regime", "SIDEWAYS")
    economic_score = result.get("economic_score")
    economic_regime = result.get("economic_regime")
    market_pulse_score = result.get("market_pulse_score", 50)
    today = _ist_today()

    # Try to parse run_id as UUID
    try:
        run_uuid = uuid.UUID(run_id)
    except (ValueError, AttributeError):
        run_uuid = uuid.uuid4()
        logger.warning(
            f"[yellow]Discovery persist: invalid run_id '{run_id}', generated {run_uuid}[/yellow]"
        )

    db = SessionLocal()
    inserted = 0
    try:
        # Create or update the single Runs row for this discovery cycle.
        # graph.py::run_discovery_pipeline writes a STARTED row at pipeline start;
        # if present, mark it COMPLETED + enrich workflow_config with regime details.
        run = db.query(Runs).filter(Runs.id == run_uuid).first()
        if not run:
            run = Runs(
                id=run_uuid,
                stock_id=None,
                workflow_name="discovery_pipeline",
                workflow_config={
                    "task": "discover",
                    "macro_regime": macro_regime,
                    "economic_regime": economic_regime,
                    "economic_score": economic_score,
                    "market_pulse_score": market_pulse_score,
                },
                status="COMPLETED",
                started_at=datetime.datetime.utcnow(),
                completed_at=datetime.datetime.utcnow(),
            )
            db.add(run)
            db.flush()
        else:
            cfg = dict(run.workflow_config or {})
            cfg.update(
                {
                    "macro_regime": macro_regime,
                    "economic_regime": economic_regime,
                    "economic_score": economic_score,
                    "market_pulse_score": market_pulse_score,
                }
            )
            run.workflow_config = cfg
            run.status = "COMPLETED"
            run.completed_at = datetime.datetime.utcnow()
            db.flush()

        # Insert one DiscoveryResults row per stock per horizon.
        # Dedupe within each (horizon, symbol): the LLM occasionally lists the
        # same symbol twice in a bucket, which would violate the UNIQUE
        # (run_id, horizon, symbol) constraint and roll back the ENTIRE persist —
        # silently dropping every classified stock and returning 0 to the API.
        seen_keys: set[tuple[str, str]] = set()
        for horizon in ("SHORT", "MID", "LONG"):
            for stock in buckets.get(horizon, []) or []:
                sym = (stock.get("symbol") or "").strip().upper()
                if not sym:
                    continue

                key = (horizon, sym)
                if key in seen_keys:
                    logger.warning(
                        f"[yellow]Discovery persist: skipping duplicate {sym} in {horizon}[/yellow]"
                    )
                    continue
                seen_keys.add(key)

                rank = int(stock.get("rank") or 0)
                disc_score = int(stock.get("discovery_score") or 0)

                # Price targets embedded in stock by the discovery LLM
                # NOTE: entry_price, stop_loss, risk_reward_ratio are NOT produced by the
                # discovery LLM — they are computed later by F2.  Write None explicitly.
                entry_price = None  # discovery LLM does not produce entry_price
                indicative_target = _safe_float(
                    stock.get("indicative_target") or stock.get("target_price")
                )
                stop_loss = None  # discovery LLM does not produce stop_loss
                rr = None  # discovery LLM does not produce risk_reward_ratio
                probability = _safe_int(stock.get("probability"))
                suggested_hold_days = _safe_int(stock.get("suggested_hold_days"))

                risk_flags = stock.get("risk_flags")
                if isinstance(risk_flags, list):
                    pass  # already JSON-serialisable
                elif risk_flags is None:
                    risk_flags = []

                dr = DiscoveryResults(
                    id=uuid.uuid4(),
                    run_id=run_uuid,
                    cycle_date=today,
                    horizon=horizon,
                    symbol=sym,
                    rank=rank,
                    discovery_score=disc_score,
                    regime=macro_regime,
                    sector=stock.get("sector")
                    or (stock.get("_raw_screener") or {}).get("sector"),
                    reasoning=stock.get("reasoning"),
                    suggested_hold_days=suggested_hold_days,
                    risk_flags=risk_flags,
                    catalyst=stock.get("catalyst"),
                    raw_screener=_sanitize_screener_row(stock.get("_raw_screener")),
                    entry_price=entry_price,
                    indicative_target=indicative_target,
                    stop_loss=stop_loss,
                    probability=probability,
                    risk_reward_ratio=rr,
                    cost_per_cycle=None,
                )
                db.add(dr)
                inserted += 1

        db.commit()
        logger.info(
            f"[bold green]Discovery persist: {inserted} stocks written for run {run_id}[/bold green]"
        )
        save_last_discovery_context(result)

    except Exception as e:
        db.rollback()
        logger.error(f"[bold red]Discovery persist: DB write failed — {e}[/bold red]")
        inserted = 0
    finally:
        db.close()

    return inserted


def persist_economic_snapshot(economic_data: dict, score: int, regime: str) -> bool:
    """
    Upsert today's economic snapshot. economic_data is the dict returned by
    fetch_economic_indicators() — keys map directly to EconomicSnapshots columns.
    Uses ON CONFLICT DO NOTHING semantics via try/except on the unique date key.
    """
    if not SessionLocal:
        return False

    today = _ist_today()
    db = SessionLocal()
    try:
        existing = (
            db.query(EconomicSnapshots)
            .filter(EconomicSnapshots.snapshot_date == today)
            .first()
        )

        if existing:
            # Update existing snapshot
            existing.economic_score = score
            existing.economic_regime = regime
            _update_econ_fields(existing, economic_data)
        else:
            snap = EconomicSnapshots(
                snapshot_date=today,
                economic_score=score,
                economic_regime=regime,
            )
            _update_econ_fields(snap, economic_data)
            db.add(snap)

        db.commit()
        logger.info(
            f"[green]Economic persist: snapshot for {today} saved (regime={regime}, score={score})[/green]"
        )
        return True

    except Exception as e:
        db.rollback()
        logger.error(f"[bold red]Economic persist: failed — {e}[/bold red]")
        return False
    finally:
        db.close()


def persist_market_regime(
    macro_regime: str, confidence: float, triggers: dict, pulse_score: int
) -> bool:
    """Insert a new market_regimes row for the current cycle."""
    if not SessionLocal:
        return False

    valid = {"BULL", "SIDEWAYS", "BEAR", "CRISIS", "VOLATILE"}
    regime = macro_regime.upper() if macro_regime else "SIDEWAYS"
    if regime not in valid:
        regime = "SIDEWAYS"

    db = SessionLocal()
    try:
        mr = MarketRegimes(
            id=uuid.uuid4(),
            regime=regime,
            confidence=confidence,
            triggers=triggers or {},
            market_pulse_score=pulse_score,
        )
        db.add(mr)
        db.commit()
        logger.info(
            f"[green]Market regime persist: {regime} (confidence={confidence}) saved[/green]"
        )
        return True

    except Exception as e:
        db.rollback()
        logger.error(f"[bold red]Market regime persist: failed — {e}[/bold red]")
        return False
    finally:
        db.close()


# ── Fetching ─────────────────────────────────────────────────────────────────


def fetch_discovery_run_buckets(run_id: str) -> dict:
    """Fetch discovered buckets from DB for a given run_id as fallback if cache is empty."""
    if not SessionLocal:
        return {}

    try:
        run_uuid = uuid.UUID(run_id)
    except (ValueError, AttributeError):
        return {}

    from app.db.models import Recommendations, Stocks

    db = SessionLocal()
    try:
        results = (
            db.query(DiscoveryResults).filter(DiscoveryResults.run_id == run_uuid).all()
        )
        buckets = {"SHORT": [], "MID": [], "LONG": []}
        if not results:
            return buckets

        symbols = [r.symbol for r in results]
        recs = (
            db.query(Recommendations, Stocks.symbol)
            .join(Stocks, Recommendations.stock_id == Stocks.id)
            .filter(Stocks.symbol.in_(symbols))
            .order_by(Recommendations.created_at.asc())
            .all()
        )

        # Map (symbol, horizon) -> latest recommendation
        rec_map = {}
        for rec, sym in recs:
            horizon_key = (rec.horizon or "MID").upper()
            rec_map[(sym, horizon_key)] = rec

        for r in results:
            h = r.horizon.upper()
            if h not in buckets:
                continue

            # Start with raw screener fields so DB-authoritative columns can override
            stock_dict: dict = {}
            if isinstance(r.raw_screener, dict):
                stock_dict.update(r.raw_screener)

            # DB-authoritative columns always win
            stock_dict.update(
                {
                    "symbol": r.symbol,
                    "clean_symbol": r.symbol,
                    "rank": r.rank,
                    "discovery_score": r.discovery_score,
                    "sector": r.sector or stock_dict.get("sector"),
                    "reasoning": r.reasoning,
                    "suggested_hold_days": r.suggested_hold_days,
                    "risk_flags": r.risk_flags,
                    "catalyst": r.catalyst,
                    "entry_price": r.entry_price,
                    "indicative_target": float(r.indicative_target)
                    if r.indicative_target is not None
                    else None,
                    "target_price": float(r.indicative_target)
                    if r.indicative_target is not None
                    else None,
                    "stop_loss": r.stop_loss,
                    "probability": r.probability,
                    "risk_reward": r.risk_reward_ratio,
                    "risk_reward_ratio": r.risk_reward_ratio,
                }
            )

            # Overlay F2 data if present
            horizon_key = r.horizon.upper()
            if (r.symbol, horizon_key) in rec_map:
                rec = rec_map[(r.symbol, horizon_key)]
                stock_dict["recommendation_id"] = str(rec.id)
                # The stored snapshot is authoritative for the user-facing verdict
                # (it was normalized at write time). Prefer it over the raw column so
                # the list badge and the detail panel can never disagree.
                fr = dict(rec.full_response) if rec.full_response else None
                verdict_src = (
                    (fr or {}).get("recommendation") if fr else rec.recommendation
                )
                if fr is not None:
                    fr["recommendation"] = final_verdict(verdict_src)
                    stock_dict["full_response"] = fr
                stock_dict["recommendation"] = final_verdict(verdict_src)

            buckets[h].append(stock_dict)

        return buckets
    except Exception as e:
        logger.error(f"[bold red]Discovery fetch: DB read failed — {e}[/bold red]")
        return {}
    finally:
        db.close()


# ── Helpers ──────────────────────────────────────────────────────────────────


def _safe_float(v) -> Optional[float]:
    try:
        import math

        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else round(f, 4)
    except (TypeError, ValueError):
        return None


def _safe_int(v) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# Fields used by _build_stock_from_scan (analysis.py) — store only these to keep JSONB tight
_SCREENER_WHITELIST = {
    "close",
    "change",
    "volume",
    "relative_volume_10d_calc",
    "RSI",
    "VWAP",
    "market_cap_basic",
    "price_earnings_ttm",
    "return_on_equity",
    "sector",
    "industry",
    "ATR",
    "EMA20",
    "EMA50",
    "EMA200",
    "Perf.W",
    "Perf.1M",
    "Perf.3M",
    "debt_to_equity",
    "after_tax_margin",
    "price_book_fq",
    "dividend_yield_recent",
}


_SCREENER_IMPORTANT = {"close", "RSI", "EMA20", "EMA50", "volume"}


def _sanitize_screener_row(row) -> Optional[dict]:
    """Coerce numpy types → Python natives, drop NaN/inf, whitelist keys."""
    if not row or not isinstance(row, dict):
        return None
    import math
    from app.core.config import logger as _log

    result = {}
    for k, v in row.items():
        if k not in _SCREENER_WHITELIST:
            continue
        if v is None:
            continue
        # Coerce numpy scalars to Python natives
        try:
            f = float(v)
            if math.isnan(f) or math.isinf(f):
                continue
            # Preserve integers as int to keep JSON clean
            result[k] = (
                int(f)
                if isinstance(v, (int,)) or (f == int(f) and abs(f) < 1e15)
                else round(f, 6)
            )
        except (TypeError, ValueError):
            # Non-numeric (str) — keep as-is
            if isinstance(v, str):
                result[k] = v
    for f in _SCREENER_IMPORTANT:
        if f not in result:
            _log.warning(
                f"[yellow]discovery_persist: key '{f}' missing from screener row[/yellow]"
            )
    return result or None


_ECON_KEY_MAP = {
    "rbi_repo_rate": "repo_rate",
    "india_cpi_yoy": "cpi",
    "india_gdp_yoy": "gdp_growth",
    "fii_flows_inr_cr": "fii_net_flow",
    "dii_flows_inr_cr": "dii_net_flow",
    "usd_inr": "usd_inr",
    "crude_oil_brent": "crude_oil",
    "gold_inr_proxy": "gold_price",
    "india_vix": "india_vix",
    "us_10y_yield": "us_fed_rate",
    "nifty_level": "nifty_level",
    "nifty_1m_change_pct": "nifty_change_pct",
}


def _update_econ_fields(obj: EconomicSnapshots, data: dict):
    for src_key, col_name in _ECON_KEY_MAP.items():
        val = _safe_float(data.get(src_key))
        if val is not None:
            setattr(obj, col_name, val)


def save_last_discovery_context(result: dict):
    """
    Save the full macroeconomic context dictionary to a local JSON file.
    Runs inline and handles all exceptions silently.
    """
    try:
        import os
        import json

        base_dir = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(base_dir, "last_discovery_context.json")
        with open(path, "w") as f:
            json.dump(result, f, indent=2, default=str)
        logger.info(
            f"[green]Successfully saved last discovery context to {path}[/green]"
        )
    except Exception as e:
        logger.error(f"[red]Failed to save last discovery context JSON: {e}[/red]")


def load_last_discovery_context() -> dict:
    """
    Load the saved macroeconomic context dictionary from the local JSON file.
    Returns empty dict if file is missing or failed to load.
    """
    import os
    import json

    base_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_dir, "last_discovery_context.json")
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"[red]Failed to load last discovery context JSON: {e}[/red]")
    return {}
