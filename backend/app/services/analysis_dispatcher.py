"""
Analysis Dispatcher — Phase 4
After discovery, fan-out F2 analysis on all discovered stocks.
Max 5 concurrent (threading.Semaphore). Progress tracked per (run_id, symbol).

Usage:
    from app.services.analysis_dispatcher import dispatch_analysis, get_status

Endpoints:
    POST /analysis/dispatch/{run_id}
    GET  /analysis/status/{run_id}
"""

import asyncio
import datetime
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Literal, Optional

import pytz

from app.core.config import logger
from app.core.verdict import final_verdict

_IST = pytz.timezone("Asia/Kolkata")


def _ist_today() -> datetime.date:
    return datetime.datetime.now(_IST).date()


# ── In-memory status store ──────────────────────────────────────────────────
# {run_id: {symbol: {status, started_at, finished_at, recommendation, cost_inr, error}}}
_status_store: dict[str, dict[str, dict]] = {}
_status_lock = threading.Lock()

_cancelled_dispatches: set[str] = set()
_cancelled_lock = threading.Lock()


SymbolStatus = Literal["queued", "running", "done", "error"]

MAX_CONCURRENT = (
    3  # Per spec: each analysis fires ~6 LLM calls; 3×6 = 18 parallel requests max
)
_STATUS_STORE_MAX = 100  # Evict oldest run when store exceeds this size
STAGGER_DELAY = 1.5  # seconds between thread starts to avoid burst rate-limit hits


def _set_status(run_id: str, symbol: str, **kwargs):
    with _status_lock:
        if run_id not in _status_store:
            # Evict oldest run when store is at capacity
            if len(_status_store) >= _STATUS_STORE_MAX:
                oldest = next(iter(_status_store))
                del _status_store[oldest]
            _status_store[run_id] = {}
        if symbol not in _status_store[run_id]:
            _status_store[run_id][symbol] = {}
        _status_store[run_id][symbol].update(kwargs)


def get_status(run_id: str) -> dict:
    """Returns per-symbol status dict for a run_id."""
    with _status_lock:
        run_data = dict(_status_store.get(run_id, {}))
    total = len(run_data)
    done = sum(1 for v in run_data.values() if v.get("status") == "done")
    running = sum(1 for v in run_data.values() if v.get("status") == "running")
    errors = sum(1 for v in run_data.values() if v.get("status") == "error")
    return {
        "run_id": run_id,
        "total": total,
        "done": done,
        "running": running,
        "queued": total - done - running - errors,
        "errors": errors,
        "complete": done + errors == total and total > 0,
        "stocks": run_data,
    }


def cancel_dispatch(run_id: str):
    """Mark a run_id as cancelled so no more queued stocks are processed."""
    with _cancelled_lock:
        _cancelled_dispatches.add(run_id)
    with _status_lock:
        if run_id in _status_store:
            for sym, item in _status_store[run_id].items():
                if item.get("status") in ("queued", "running"):
                    item.update(
                        {
                            "status": "error",
                            "error": "Cancelled by user",
                            "finished_at": time.time(),
                        }
                    )


def get_latest_recommendation_today(symbol: str, horizon: str) -> Optional[dict]:
    """
    Return today's (IST) recommendation for symbol+horizon from DB, or None.
    Used to skip re-analysis when dedup policy is 'same calendar day'.
    """
    from app.core.config import SessionLocal

    if not SessionLocal:
        return None
    from app.db.models import Recommendations, Stocks
    from sqlalchemy import func

    today = _ist_today()
    db = SessionLocal()
    try:
        row = (
            db.query(Recommendations)
            .join(Stocks, Recommendations.stock_id == Stocks.id)
            .filter(
                Stocks.symbol == symbol.upper(),
                Recommendations.horizon == horizon,
                func.date(Recommendations.created_at) == today,
            )
            .order_by(Recommendations.created_at.desc())
            .first()
        )
        if not row:
            return None

        def _s(v):
            if v is None:
                return None
            try:
                import math

                f = float(v)
                return None if math.isnan(f) or math.isinf(f) else round(f, 4)
            except (TypeError, ValueError):
                return None

        return {
            "recommendation_id": str(row.id),
            "recommendation": row.recommendation,
            "confidence": _s(row.confidence),
            "entry_price": _s(row.entry_price),
            "target_price": _s(row.target_price),
            "stop_loss": _s(row.stop_loss),
            "risk_reward": _s(row.risk_reward),
            "horizon": row.horizon,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
    except Exception as e:
        logger.warning(
            f"[yellow]Dispatcher dedup check failed for {symbol}: {e}[/yellow]"
        )
        return None
    finally:
        db.close()


def dispatch_analysis(
    run_id: str,
    buckets: dict,
    usd_inr: float = 84.0,
    force_refresh: bool = False,
    on_complete: callable = None,
) -> str:
    """
    Start background F2 analysis on all stocks in buckets.
    Stocks are processed in order: SHORT first (rank 1..n), then MID, then LONG.
    Max MAX_CONCURRENT in-flight at once, with stagger delay between thread starts.

    force_refresh=True  skips today's dedup check (used on explicit button click).
    force_refresh=False reuses today's DB result if one exists (used for auto-dispatch).

    Returns a dispatch_id (same as run_id for tracking).
    """
    # Carry full stock dicts so F1 catalyst/reasoning can be threaded into F2
    all_stocks = []
    skipped = 0
    for horizon in ("SHORT", "MID", "LONG"):
        for stock in sorted(buckets.get(horizon, []), key=lambda x: x.get("rank", 999)):
            sym = stock.get("symbol")
            if not sym:
                continue
            if not force_refresh:
                existing = get_latest_recommendation_today(sym, horizon)
                if existing:
                    # Reuse — register as done immediately without running F2
                    _set_status(
                        run_id,
                        sym,
                        status="done",
                        started_at=None,
                        finished_at=None,
                        recommendation=final_verdict(existing.get("recommendation")),
                        confidence=existing.get("confidence"),
                        entry_price=existing.get("entry_price"),
                        target_price=existing.get("target_price"),
                        stop_loss=existing.get("stop_loss"),
                        risk_reward=existing.get("risk_reward"),
                        horizon=existing.get("horizon") or horizon,
                        cost_inr=0.0,
                        recommendation_id=existing.get("recommendation_id"),
                        full_response=None,
                        reused=True,
                    )
                    skipped += 1
                    continue
            all_stocks.append((sym, horizon, stock))

    if skipped:
        logger.info(
            f"[cyan]Dispatcher: {skipped} stocks reused from today's DB for run {run_id}[/cyan]"
        )

    if not all_stocks:
        logger.info(
            f"[green]Dispatcher: all stocks already analysed today for run {run_id}[/green]"
        )
        return run_id

    # Pre-register remaining as queued
    for symbol, _, _ in all_stocks:
        if symbol:
            _set_status(
                run_id,
                symbol,
                status="queued",
                started_at=None,
                finished_at=None,
                recommendation=None,
                confidence=None,
                cost_inr=None,
                error=None,
            )

    # Launch background thread that manages the semaphore
    t = threading.Thread(
        target=_run_with_semaphore,
        args=(run_id, all_stocks, usd_inr),
        kwargs={"on_complete": on_complete},
        daemon=True,
    )
    t.start()
    logger.info(
        f"[bold cyan]Dispatcher: launched {len(all_stocks)} stocks for run {run_id}[/bold cyan]"
    )
    return run_id


def _build_full_response(
    result: dict, symbol: str, horizon: str, cost_inr: float, f1_stock: dict = None
) -> dict:
    """Build a JSON-serializable AnalyzeResponse-shaped dict from a raw pipeline result.
    Stored in _status_store so the frontend can populate _analyzeCache without re-running."""
    rec = result.get("final_recommendation") or {}
    tech = result.get("technical_output") or {}
    fund = result.get("fundamental_output") or {}
    sent = result.get("sentiment_output") or {}
    chart = result.get("chart_pattern_output") or {}
    debate = result.get("debate_output") or {}
    f1 = f1_stock or {}

    def _safe(v):
        if v is None:
            return None
        try:
            import math

            f = float(v)
            return None if math.isnan(f) or math.isinf(f) else f
        except (TypeError, ValueError):
            return None

    _horizon_days_map = {"SHORT": 15, "MID": 60, "LONG": 365}
    final_horizon = rec.get("horizon") or horizon
    # Final verdict label space is BUY/SELL/WAIT — legacy HOLD maps to WAIT
    _rec_label = final_verdict(rec.get("recommendation"))
    return {
        "symbol": symbol,
        "run_id": rec.get("recommendation_id"),
        "recommendation": _rec_label,
        "confidence": _safe(rec.get("confidence", 0.0)),
        "entry_price": _safe(rec.get("entry_price")),
        "target_price": _safe(rec.get("target_price")),
        "stop_loss": _safe(rec.get("stop_loss")),
        "risk_reward": _safe(rec.get("risk_reward")),
        "upside_pct": _safe(rec.get("upside_pct")),
        "risk_pct": _safe(rec.get("risk_pct")),
        "position_size_pct": _safe(rec.get("position_size_pct")),
        "horizon": final_horizon,
        "horizon_days": _horizon_days_map.get((final_horizon or "MID").upper(), 60),
        "timeframe": rec.get("timeframe"),
        "narrative": rec.get("narrative", ""),
        "key_risks": rec.get("key_risks") or [],
        "key_catalysts": rec.get("key_catalysts") or [],
        "validator_status": result.get("validator_status", "accepted"),
        "validator_issues": result.get("validator_issues") or [],
        "macro_regime": result.get("macro_regime", "SIDEWAYS"),
        "market_pulse_score": result.get("market_pulse_score", 50),
        "economic_score": result.get("economic_score"),
        "economic_regime": result.get("economic_regime"),
        "recommendation_id": rec.get("recommendation_id"),
        "cost_per_analysis_inr": cost_inr,
        "errors": result.get("errors") or [],
        "f1_catalyst": f1.get("catalyst") or result.get("f1_catalyst"),
        "f1_reasoning": f1.get("reasoning") or result.get("f1_reasoning"),
        "f1_discovery_score": f1.get("discovery_score")
        or result.get("f1_discovery_score"),
        "agent_signals": rec.get("agent_signals") or {},
        "technical_summary": {
            "signal": tech.get("signal", "HOLD"),
            "confidence": _safe(tech.get("confidence", 0.0)),
            "narrative": tech.get("narrative", ""),
            "key_levels": tech.get("key_levels"),
            "raw_data": tech.get("raw_data"),
            "sub_scores": tech.get("sub_scores"),
        },
        "fundamental_summary": {
            "signal": fund.get("signal", "HOLD"),
            "confidence": _safe(fund.get("confidence", 0.0)),
            "weighted_score": _safe(fund.get("weighted_score", 0.0)),
            "narrative": fund.get("narrative", ""),
            "strengths": fund.get("strengths") or [],
            "weaknesses": fund.get("weaknesses") or [],
            "sub_scores": fund.get("sub_scores"),
        },
        "sentiment_summary": {
            "signal": sent.get("signal", "HOLD"),
            "confidence": _safe(sent.get("confidence", 0.0)),
            "aggregate_score": _safe(sent.get("aggregate_score", 0.0)),
            "narrative": sent.get("narrative", ""),
            "key_themes": sent.get("key_themes") or [],
            "anomaly_count": sent.get("anomaly_count", 0),
            "headline_count": sent.get("headline_count", 0),
            "fallback_used": bool(sent.get("fallback_used", False)),
            "headlines": [
                {
                    "text": h.get("headline", ""),
                    "score": round(float(h.get("score", 0)), 2),
                }
                for h in (sent.get("scores") or [])[:20]
            ],
            "sub_scores": sent.get("sub_scores"),
        },
        "chart_pattern_summary": {
            "signal": chart.get("signal", "HOLD"),
            "confidence": _safe(chart.get("confidence", 0.0)),
            "narrative": chart.get("narrative", ""),
            "patterns_detected": chart.get("patterns_detected") or [],
            "sub_scores": chart.get("sub_scores"),
        },
        "debate_summary": {
            "triggered": True,
            "bull_case": debate.get("bull_case"),
            "bear_case": debate.get("bear_case"),
            "missed_risks": debate.get("missed_risks") or [],
            "independent_signal": debate.get("independent_signal"),
            "independent_confidence": _safe(debate.get("independent_confidence")),
            "agrees_with_consensus": debate.get("agrees_with_consensus"),
            "synthesis": debate.get("synthesis"),
            "evidence_citations": debate.get("evidence_citations") or [],
        },
        "horizon_confirmation": {
            "suggested_horizon": result.get("suggested_horizon"),
            "final_horizon": result.get("final_horizon"),
            "override_reason": result.get("horizon_override_reason"),
        },
    }


def _run_with_semaphore(
    run_id: str, all_stocks: list, usd_inr: float, on_complete: callable = None
):
    """Worker thread: uses a threading.Semaphore(MAX_CONCURRENT) to cap concurrency."""
    from app.agents.graph import run_analysis_pipeline
    from app.core.model_router import (
        compute_cost,
        cost_usd_to_inr,
        get_model_id,
        ModelTier,
    )

    sem = threading.Semaphore(MAX_CONCURRENT)

    def run_one(symbol: str, horizon: str, f1_stock: dict):
        if not symbol:
            return

        with _cancelled_lock:
            if run_id in _cancelled_dispatches:
                return

        sem.acquire()
        try:
            with _cancelled_lock:
                if run_id in _cancelled_dispatches:
                    return

            _set_status(run_id, symbol, status="running", started_at=time.time())
            result = run_analysis_pipeline(
                symbol,
                suggested_horizon=horizon,
                f1_catalyst=f1_stock.get("catalyst"),
                f1_reasoning=f1_stock.get("reasoning"),
                f1_discovery_score=f1_stock.get("discovery_score"),
            )
            rec = result.get("final_recommendation") or {}

            # Prefer real cost computed by decision_node; fall back to flat approximation
            cost_inr_real = rec.get("cost_per_analysis_inr")
            if cost_inr_real:
                cost_inr = float(cost_inr_real)
            else:
                cost_usd_approx = (
                    4 * compute_cost(get_model_id(ModelTier.FLASH), 3000, 500)
                    + compute_cost(get_model_id(ModelTier.PRO_THINK), 6000, 1500)
                    + compute_cost(get_model_id(ModelTier.PRO), 5000, 1200)
                )
                cost_inr = cost_usd_to_inr(cost_usd_approx, usd_inr)

            try:
                full_response = _build_full_response(
                    result, symbol, horizon, round(cost_inr, 2), f1_stock
                )
            except Exception as build_err:
                logger.error(
                    f"[red]Dispatcher: _build_full_response failed for {symbol} — {build_err}[/red]"
                )
                full_response = None

            with _cancelled_lock:
                if run_id in _cancelled_dispatches:
                    return

            _set_status(
                run_id,
                symbol,
                status="done",
                finished_at=time.time(),
                recommendation=final_verdict(rec.get("recommendation")),
                confidence=rec.get("confidence"),
                entry_price=rec.get("entry_price"),
                target_price=rec.get("target_price"),
                stop_loss=rec.get("stop_loss"),
                risk_reward=rec.get("risk_reward"),
                horizon=rec.get("horizon") or horizon,
                cost_inr=round(cost_inr, 2),
                recommendation_id=rec.get("recommendation_id"),
                full_response=full_response,
            )
            logger.info(
                f"[green]Dispatcher: {symbol} done — "
                f"{rec.get('recommendation', 'N/A')} @ {rec.get('confidence', 0)}%[/green]"
            )
        except Exception as e:
            with _cancelled_lock:
                if run_id in _cancelled_dispatches:
                    return
            _set_status(
                run_id, symbol, status="error", finished_at=time.time(), error=str(e)
            )
            logger.error(f"[red]Dispatcher: {symbol} failed — {e}[/red]")
        finally:
            sem.release()

    threads = []
    for i, (symbol, horizon, f1_stock) in enumerate(all_stocks):
        if not symbol:
            continue
        with _cancelled_lock:
            if run_id in _cancelled_dispatches:
                break
        t = threading.Thread(
            target=run_one, args=(symbol, horizon, f1_stock), daemon=True
        )
        threads.append(t)
        t.start()
        # Stagger thread starts to avoid burst LLM/MCP rate-limit hits
        if STAGGER_DELAY > 0 and i < len(all_stocks) - 1:
            sleep_step = 0.1
            elapsed_sleep = 0.0
            while elapsed_sleep < STAGGER_DELAY:
                with _cancelled_lock:
                    if run_id in _cancelled_dispatches:
                        break
                time.sleep(sleep_step)
                elapsed_sleep += sleep_step

    for t in threads:
        t.join()

    with _cancelled_lock:
        _cancelled_dispatches.discard(run_id)

    if on_complete:
        try:
            on_complete()
        except Exception as e:
            logger.warning(
                f"[yellow]Dispatcher on_complete callback failed: {e}[/yellow]"
            )

    logger.info(
        f"[bold green]Dispatcher: all stocks done for run {run_id}[/bold green]"
    )
