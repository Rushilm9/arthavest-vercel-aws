"""
Agent Logs API — detailed drill-down on pipeline runs.

Endpoints (mounted under /api/agentlogs):
  GET  /runs                 — paginated list of recent runs with aggregate stats
  GET  /runs/{run_id}        — single run detail: Runs row + all AgentLogs ordered by created_at
  GET  /agents/{agent_log_id}— single AgentLogs row detail (input/output/prompt/raw_response/reasoning)
  GET  /stats                — aggregate stats: per-agent failure rate, p50/p95 latency, avg cost
"""

from __future__ import annotations

import datetime
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import desc, func, and_, case

from app.core.config import SessionLocal, logger
from app.db.models import Runs, AgentLogs, Recommendations, DiscoveryResults, Stocks


router = APIRouter(prefix="/api/agentlogs", tags=["AgentLogs"])


def _safe_dt(d: Optional[datetime.datetime]) -> Optional[str]:
    return d.isoformat() if d else None


def _safe_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _serialize_run_row(run: Runs, stats: Optional[dict] = None) -> dict:
    cfg = run.workflow_config or {}
    payload = {
        "id": str(run.id),
        "workflow_name": run.workflow_name,
        "status": run.status,
        "started_at": _safe_dt(run.started_at),
        "completed_at": _safe_dt(run.completed_at),
        "elapsed_sec": (
            round((run.completed_at - run.started_at).total_seconds(), 2)
            if run.completed_at and run.started_at
            else None
        ),
        "stock_id": str(run.stock_id) if run.stock_id else None,
        "workflow_config": cfg,
        "error": cfg.get("error") if isinstance(cfg, dict) else None,
    }
    if stats:
        payload.update(stats)
    return payload


def _serialize_agent_log_summary(row: AgentLogs) -> dict:
    return {
        "id": str(row.id),
        "run_id": str(row.run_id) if row.run_id else None,
        "agent_name": row.agent_name,
        "agent_type": row.agent_type,
        "status": row.status,
        "error": (row.error or None),
        "latency_ms": _safe_float(row.latency_ms),
        "model_used": row.model_used,
        "signal": row.signal,
        "confidence": _safe_float(row.confidence),
        "tokens_input": row.tokens_input,
        "tokens_output": row.tokens_output,
        "cost_usd": _safe_float(row.cost_usd),
        "retry_count": row.retry_count or 0,
        "created_at": _safe_dt(row.created_at),
        "has_prompt": bool(row.prompt_template),
        "has_raw_response": bool(row.raw_llm_response),
        "has_input": bool(row.input),
        "has_output": bool(row.output),
        "has_reasoning": bool(row.reasoning),
    }


def _serialize_agent_log_full(row: AgentLogs) -> dict:
    base = _serialize_agent_log_summary(row)
    base.update(
        {
            "input": row.input,
            "output": row.output,
            "reasoning": row.reasoning,
            "prompt_template": row.prompt_template,
            "raw_llm_response": row.raw_llm_response,
        }
    )
    return base


# ══════════════════════════════════════════════════════════════
# GET /api/agentlogs/runs
# ══════════════════════════════════════════════════════════════


@router.get("/runs", summary="Recent runs with aggregate agent stats")
def list_runs(
    limit: int = Query(20, ge=1, le=200),
    page: int = Query(1, ge=1),
    workflow: Optional[str] = Query(
        None, description="Filter by workflow_name (e.g. analysis_pipeline)"
    ),
    status: Optional[str] = Query(
        None, description="Filter by status: STARTED / COMPLETED / FAILED"
    ),
    symbol: Optional[str] = Query(None, description="Filter by stock symbol"),
):
    """
    Returns paginated list of recent runs. Each row includes aggregate stats
    pulled from agent_logs (agent count, failure count, total cost, total latency).
    """
    if not SessionLocal:
        raise HTTPException(503, "Database not available")
    db = SessionLocal()
    try:
        q = db.query(Runs)
        if workflow:
            q = q.filter(Runs.workflow_name == workflow)
        if status:
            q = q.filter(Runs.status == status.upper())
        if symbol:
            stock = db.query(Stocks).filter(Stocks.symbol == symbol.upper()).first()
            if stock:
                q = q.filter(Runs.stock_id == stock.id)
            else:
                return {
                    "runs": [],
                    "total": 0,
                    "page": 1,
                    "total_pages": 1,
                    "limit": limit,
                }

        total = q.count()
        total_pages = max(1, -(-total // limit))  # ceil division
        offset = (page - 1) * limit
        runs = q.order_by(desc(Runs.started_at)).offset(offset).limit(limit).all()
        run_ids = [r.id for r in runs]

        # Aggregate agent stats per run (single query)
        stats_by_run: dict[uuid.UUID, dict] = {}
        if run_ids:
            agg_rows = (
                db.query(
                    AgentLogs.run_id,
                    func.count(AgentLogs.id).label("agent_count"),
                    func.sum(case((AgentLogs.status == "FAILED", 1), else_=0)).label(
                        "failed_count"
                    ),
                    func.coalesce(func.sum(AgentLogs.latency_ms), 0).label(
                        "total_latency_ms"
                    ),
                    func.coalesce(func.sum(AgentLogs.cost_usd), 0).label(
                        "total_cost_usd"
                    ),
                    func.coalesce(func.sum(AgentLogs.tokens_input), 0).label(
                        "total_tokens_in"
                    ),
                    func.coalesce(func.sum(AgentLogs.tokens_output), 0).label(
                        "total_tokens_out"
                    ),
                )
                .filter(AgentLogs.run_id.in_(run_ids))
                .group_by(AgentLogs.run_id)
                .all()
            )
            for row in agg_rows:
                stats_by_run[row.run_id] = {
                    "agent_count": int(row.agent_count or 0),
                    "failed_count": int(row.failed_count or 0),
                    "total_latency_ms": _safe_float(row.total_latency_ms),
                    "total_cost_usd": _safe_float(row.total_cost_usd),
                    "total_tokens_in": int(row.total_tokens_in or 0),
                    "total_tokens_out": int(row.total_tokens_out or 0),
                }

        # Stock symbol for each run (single join)
        stock_id_to_sym: dict[uuid.UUID, str] = {}
        stock_ids = [r.stock_id for r in runs if r.stock_id]
        if stock_ids:
            for sid, sym in (
                db.query(Stocks.id, Stocks.symbol)
                .filter(Stocks.id.in_(stock_ids))
                .all()
            ):
                stock_id_to_sym[sid] = sym

        out = []
        for r in runs:
            payload = _serialize_run_row(r, stats=stats_by_run.get(r.id))
            payload["symbol"] = stock_id_to_sym.get(r.stock_id) if r.stock_id else None
            out.append(payload)

        return {
            "runs": out,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "limit": limit,
        }
    except Exception as e:
        logger.error(f"[red]agentlogs.list_runs failed: {e}[/red]")
        raise HTTPException(500, f"List runs failed: {e}")
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════
# GET /api/agentlogs/runs/{run_id}
# ══════════════════════════════════════════════════════════════


@router.get("/runs/{run_id}", summary="Single run detail: all agents timeline")
def get_run_detail(run_id: str):
    """
    Returns the run row + all AgentLogs rows ordered by created_at,
    plus linked recommendation/discovery_results if any.
    AgentLogs are returned as SUMMARIES (no input/output/prompt/raw_response payloads)
    to keep the response light. Use /agents/{id} for full per-agent detail.
    """
    if not SessionLocal:
        raise HTTPException(503, "Database not available")
    try:
        rid = uuid.UUID(run_id)
    except (ValueError, TypeError):
        raise HTTPException(400, f"Invalid run_id: {run_id}")

    db = SessionLocal()
    try:
        run = db.query(Runs).filter(Runs.id == rid).first()
        if not run:
            raise HTTPException(404, f"Run not found: {run_id}")

        agents = (
            db.query(AgentLogs)
            .filter(AgentLogs.run_id == rid)
            .order_by(AgentLogs.created_at.asc())
            .all()
        )
        agent_summaries = [_serialize_agent_log_summary(a) for a in agents]

        # Aggregate
        agg = {
            "agent_count": len(agents),
            "failed_count": sum(1 for a in agents if a.status == "FAILED"),
            "total_latency_ms": sum(_safe_float(a.latency_ms) or 0 for a in agents),
            "total_cost_usd": sum(_safe_float(a.cost_usd) or 0 for a in agents),
            "total_tokens_in": sum((a.tokens_input or 0) for a in agents),
            "total_tokens_out": sum((a.tokens_output or 0) for a in agents),
        }

        # Stock symbol if any
        symbol = None
        if run.stock_id:
            s = db.query(Stocks).filter(Stocks.id == run.stock_id).first()
            symbol = s.symbol if s else None

        # Linked recommendation (F2) or discovery_results count (F1)
        recommendation = None
        if (run.workflow_name or "").startswith("analysis"):
            rec = (
                db.query(Recommendations).filter(Recommendations.run_id == rid).first()
            )
            if rec:
                recommendation = {
                    "id": str(rec.id),
                    "recommendation": rec.recommendation,
                    "confidence": _safe_float(rec.confidence),
                    "horizon": rec.horizon,
                    "entry_price": _safe_float(rec.entry_price),
                    "target_price": _safe_float(rec.target_price),
                    "stop_loss": _safe_float(rec.stop_loss),
                    "validator_status": rec.validator_status,
                }

        discovery_count = None
        if (run.workflow_name or "").startswith("discovery"):
            discovery_count = (
                db.query(func.count(DiscoveryResults.id))
                .filter(DiscoveryResults.run_id == rid)
                .scalar()
            )

        return {
            "run": _serialize_run_row(run, stats=agg),
            "symbol": symbol,
            "agents": agent_summaries,
            "recommendation": recommendation,
            "discovery_count": discovery_count,
        }
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════
# GET /api/agentlogs/agents/{agent_log_id}
# ══════════════════════════════════════════════════════════════


@router.get("/agents/{agent_log_id}", summary="Full per-agent detail")
def get_agent_detail(agent_log_id: str):
    """
    Returns a single AgentLogs row with all payloads:
    input snapshot, output summary, reasoning, prompt template, raw LLM response.
    """
    if not SessionLocal:
        raise HTTPException(503, "Database not available")
    try:
        aid = uuid.UUID(agent_log_id)
    except (ValueError, TypeError):
        raise HTTPException(400, f"Invalid agent_log_id: {agent_log_id}")
    db = SessionLocal()
    try:
        row = db.query(AgentLogs).filter(AgentLogs.id == aid).first()
        if not row:
            raise HTTPException(404, f"Agent log not found: {agent_log_id}")
        return _serialize_agent_log_full(row)
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════
# GET /api/agentlogs/stats
# ══════════════════════════════════════════════════════════════


@router.get("/stats", summary="Per-agent failure rate, latency, cost")
def get_stats(hours: int = Query(24, ge=1, le=720)):
    """
    Aggregate stats grouped by agent_name across the last `hours` window.
    Returns: count, failure_count, failure_rate, p50/p95 latency, avg cost, total tokens.
    """
    if not SessionLocal:
        raise HTTPException(503, "Database not available")
    since = datetime.datetime.utcnow() - datetime.timedelta(hours=hours)
    db = SessionLocal()
    try:
        # Group counts + failure counts in SQL
        rows = (
            db.query(
                AgentLogs.agent_name,
                AgentLogs.agent_type,
                func.count(AgentLogs.id).label("count"),
                func.sum(case((AgentLogs.status == "FAILED", 1), else_=0)).label(
                    "failures"
                ),
                func.avg(AgentLogs.latency_ms).label("avg_latency_ms"),
                func.avg(AgentLogs.cost_usd).label("avg_cost_usd"),
                func.sum(AgentLogs.tokens_input).label("total_tokens_in"),
                func.sum(AgentLogs.tokens_output).label("total_tokens_out"),
            )
            .filter(AgentLogs.created_at >= since)
            .group_by(AgentLogs.agent_name, AgentLogs.agent_type)
            .all()
        )

        # Compute p50/p95 in Python (Postgres percentile_cont needs WITHIN GROUP — keep it simple)
        latencies_by_agent: dict[str, list[float]] = {}
        for r in (
            db.query(AgentLogs.agent_name, AgentLogs.latency_ms)
            .filter(AgentLogs.created_at >= since, AgentLogs.latency_ms.isnot(None))
            .all()
        ):
            latencies_by_agent.setdefault(r.agent_name, []).append(float(r.latency_ms))

        def _percentile(arr: list[float], p: float) -> Optional[float]:
            if not arr:
                return None
            s = sorted(arr)
            k = (len(s) - 1) * p
            f = int(k)
            c = min(f + 1, len(s) - 1)
            return round(s[f] + (s[c] - s[f]) * (k - f), 1)

        agents = []
        for r in rows:
            lats = latencies_by_agent.get(r.agent_name, [])
            count = int(r.count or 0)
            fails = int(r.failures or 0)
            agents.append(
                {
                    "agent_name": r.agent_name,
                    "agent_type": r.agent_type,
                    "count": count,
                    "failures": fails,
                    "failure_rate": round(fails / count, 4) if count else 0.0,
                    "avg_latency_ms": _safe_float(r.avg_latency_ms),
                    "p50_latency_ms": _percentile(lats, 0.50),
                    "p95_latency_ms": _percentile(lats, 0.95),
                    "avg_cost_usd": _safe_float(r.avg_cost_usd),
                    "total_tokens_in": int(r.total_tokens_in or 0),
                    "total_tokens_out": int(r.total_tokens_out or 0),
                }
            )

        # Sort highest-volume first
        agents.sort(key=lambda a: a["count"], reverse=True)
        return {
            "window_hours": hours,
            "since": since.isoformat(),
            "agents": agents,
        }
    finally:
        db.close()
