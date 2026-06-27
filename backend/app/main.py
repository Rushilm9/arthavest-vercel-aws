from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import auth
from app.api.routes import analysis
from app.api.routes import alerts
from app.api.routes import smc
from app.api.routes import market
from app.api.routes import agentlogs
from app.core.scheduler import start_scheduler, stop_scheduler
from app.core.config import logger, get_llm_info
from app.services.mcp_client import (
    log_mcp_config,
    is_healthy as mcp_is_healthy,
    ping as mcp_ping,
)
import logging
import time


# ── Suppress noisy access-log entries ──────────────────────────────────────
# The test console polls /health every 15 s and static assets are fetched
# on every page load. Neither is useful in the terminal. This filter drops
# those lines from uvicorn's access logger without affecting anything else.
_SILENT_PATHS = {"/health", "/mcp/health", "/docs", "/openapi.json", "/favicon.ico"}


class _SilentPathFilter(logging.Filter):
    """Drop uvicorn access-log records for health/static/docs paths."""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        # uvicorn access records look like:
        #   127.0.0.1:12345 - "GET /health HTTP/1.1" 200 OK
        for path in _SILENT_PATHS:
            if f'"GET {path} ' in msg or f'"HEAD {path} ' in msg:
                return False
        # Also suppress requests for static assets (js, css, fonts, icons)
        for ext in (".js", ".css", ".woff", ".woff2", ".png", ".ico", ".svg", ".map"):
            if f'"{ext}' in msg or ext + " HTTP" in msg:
                return False
        return True


_access_filter = _SilentPathFilter()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("[bold green]🚀 Starting ArthaVest Backend...[/bold green]")
    get_llm_info()

    # Auto-create tables for SQLite (idempotent — no-ops if tables exist)
    try:
        from app.core.config import engine
        from app.db.models import Base

        if engine:
            Base.metadata.create_all(bind=engine)
            logger.info("[bold green]✓ Database tables verified/created.[/bold green]")
    except Exception as _e:
        logger.warning(f"[yellow]Table creation skipped: {_e}[/yellow]")

    start_scheduler()

    # ── Startup Tasks (Deferred to run asynchronously after startup) ──
    async def run_startup_tasks():
        import asyncio

        # Wait a tiny bit for the web server to bind to the port
        await asyncio.sleep(0.1)

        # 1. Arize Phoenix Cloud tracing (Phase 3)
        try:
            from app.core.observability import init_observability

            await asyncio.to_thread(init_observability)
        except Exception as _e:
            logger.warning(f"[yellow]Deferred Arize init failed: {_e}[/yellow]")

        try:
            log_mcp_config()
        except Exception as _e:
            logger.warning(f"[yellow]Deferred log_mcp_config failed: {_e}[/yellow]")

        # 2. Best-effort initial probe so /mcp/health is meaningful right away.
        try:
            # Run in thread pool to avoid blocking the event loop
            ok = await asyncio.to_thread(mcp_ping, True)
            logger.info(
                f"[bold {'green' if ok else 'yellow'}]MCP initial probe: {'UP' if ok else 'DOWN'}[/bold {'green' if ok else 'yellow'}]"
            )
        except Exception as _e:
            logger.warning(f"[yellow]MCP initial probe error: {_e}[/yellow]")

    import asyncio

    asyncio.create_task(run_startup_tasks())

    # Attach the access-log filter so health polls don't clog the terminal
    uvicorn_access = logging.getLogger("uvicorn.access")
    uvicorn_access.addFilter(_access_filter)
    logger.info("[bold green]✓ ArthaVest Backend is ready![/bold green]")
    yield

    # Shutdown
    uvicorn_access.removeFilter(_access_filter)
    logger.info("[bold red]Stopping ArthaVest Backend...[/bold red]")
    stop_scheduler()


# Initialize FastAPI app
app = FastAPI(
    title="ArthaVest",
    description="AI-powered Indian stock research — Aurora-backed decision ledger",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow all origins for development
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request Logging Middleware — only log meaningful API calls
# Adds (TEST_REPORT.md issue #4) a completion line with elapsed time + a clear
# CLIENT-DISCONNECT marker for long handlers so operators can correlate slow
# /discover runs even when the client socket dropped.
@app.middleware("http")
async def log_requests(request: Request, call_next):
    path = request.url.path
    skip = (
        path in _SILENT_PATHS
        or path.startswith("/static")
        or any(
            path.endswith(ext)
            for ext in (
                ".js",
                ".css",
                ".woff",
                ".woff2",
                ".png",
                ".ico",
                ".svg",
                ".map",
            )
        )
    )
    if not skip:
        logger.info(f" [dim]← {request.method} {path}[/dim]")

    t0 = time.time()
    try:
        response = await call_next(request)
    except Exception as exc:
        elapsed = round(time.time() - t0, 2)
        # Starlette raises ClientDisconnect on dropped sockets; log it cleanly
        name = type(exc).__name__
        if name == "ClientDisconnect":
            if not skip:
                logger.warning(
                    f" [yellow]→ CLIENT-DISCONNECT {request.method} {path} after {elapsed}s "
                    f"(handler may still be running)[/yellow]"
                )
        else:
            logger.error(
                f" [red]→ ERROR {request.method} {path} after {elapsed}s: {name}: {exc}[/red]"
            )
        raise

    elapsed = round(time.time() - t0, 2)
    if not skip and elapsed >= 1.0:
        # Only log slow successes; fast handlers are uvicorn-access-log territory.
        logger.info(
            f" [dim]→ {response.status_code} {request.method} {path} ({elapsed}s)[/dim]"
        )
    return response


# Register routes
app.include_router(auth.router)
app.include_router(analysis.router)
app.include_router(alerts.router)
app.include_router(smc.router)
app.include_router(market.router)
app.include_router(agentlogs.router)


# ── /failures endpoint ────────────────────────────────────────────────────
from app.services.failure_log import get_recent_failures, clear_all_logs


@app.get("/failures", tags=["QA"], summary="Recent pipeline failure log entries")
def get_failures(limit: int = 50):
    """Returns the most recent structured failure log entries from qa_logs/failed_log.jsonl."""
    return {"failures": get_recent_failures(limit=limit), "count": min(limit, 9999)}


@app.delete("/logs", tags=["QA"], summary="Clear all pipeline logs")
def delete_logs(clear_db: bool = True):
    """
    Clears all failure log files (JSONL) and optionally the AgentLogs DB table.

    Query params:
        clear_db: If true (default), also truncates the AgentLogs table in the database.
    """
    result = clear_all_logs()

    # Optionally clear AgentLogs from DB
    db_cleared = 0
    if clear_db:
        try:
            from app.core.config import SessionLocal
            from app.db.models import AgentLogs

            if SessionLocal:
                db = SessionLocal()
                try:
                    db_cleared = db.query(AgentLogs).delete()
                    db.commit()
                except Exception as e:
                    db.rollback()
                    result["db_error"] = str(e)
                finally:
                    db.close()
        except Exception as e:
            result["db_error"] = str(e)

    result["db_agent_logs_cleared"] = db_cleared
    logger.info(
        f"[bold yellow]🧹 Logs cleared: {result['entries_removed']} file entries, {db_cleared} DB rows[/bold yellow]"
    )
    return result


from fastapi.staticfiles import StaticFiles


@app.get("/health")
def health():
    return {"status": "healthy", "version": "1.0.0"}


import httpx
import os


@app.get("/api_keys/health", tags=["QA"], summary="Test configured LLM API keys")
async def api_keys_health():
    """Test the 3 explicitly configured Gemini API keys."""
    keys = {}
    from app.core.config import settings

    if settings.LLM_API_KEY_1:
        keys["GOOGLE_API_KEY_1"] = settings.LLM_API_KEY_1
    if settings.LLM_API_KEY_2:
        keys["GOOGLE_API_KEY_2"] = settings.LLM_API_KEY_2
    if settings.LLM_API_KEY_3:
        keys["GOOGLE_API_KEY_3"] = settings.LLM_API_KEY_3

    results = []
    async with httpx.AsyncClient() as client:
        for name, key in keys.items():
            try:
                url = (
                    f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
                )
                resp = await client.get(url, timeout=5.0)
                if resp.status_code == 200:
                    results.append(
                        {"name": name, "status": "ok", "detail": "Valid key"}
                    )
                else:
                    try:
                        err = (
                            resp.json()
                            .get("error", {})
                            .get("message", f"HTTP {resp.status_code}")
                        )
                    except:
                        err = f"HTTP {resp.status_code}"
                    results.append({"name": name, "status": "error", "detail": err})
            except Exception as e:
                results.append({"name": name, "status": "error", "detail": str(e)})

    return {"keys": results, "total": len(results)}


@app.get(
    "/connections/vertex_check", tags=["QA"], summary="Test Vertex AI specifically"
)
async def vertex_check():
    """Confirms that ChatVertexAI is active and successfully connects to Google Cloud."""
    from app.core.config import settings

    if not settings.USE_VERTEX:
        return {"ok": False, "status": "Vertex AI is NOT enabled (USE_VERTEX=false)"}

    from app.core.model_router import get_model, ModelTier

    try:
        # Request a model to force instantiation and trigger auth
        llm = get_model(ModelTier.FLASH)
        # Type check to ensure it's Vertex
        if type(llm).__name__ != "ChatVertexAI":
            return {
                "ok": False,
                "status": "Model retrieved was not ChatVertexAI",
                "type": type(llm).__name__,
            }

        # Test generation
        from langchain_core.messages import HumanMessage

        response = llm.invoke(
            [
                HumanMessage(
                    content="Hello! Please reply with exactly the word 'VERTEX_OK'."
                )
            ]
        )
        content = response.content.strip()

        return {
            "ok": True,
            "status": "Vertex AI is active and responding",
            "response": content,
            "project": settings.GOOGLE_CLOUD_PROJECT,
            "location": settings.GOOGLE_CLOUD_LOCATION,
        }
    except Exception as e:
        return {"ok": False, "status": "Vertex AI call failed", "error": str(e)}


@app.get(
    "/connections/health", tags=["QA"], summary="Test all API keys + the DB connection"
)
async def connections_health():
    """
    One-shot connectivity check for every external credential the app uses.

    Probes:
      - Gemini keys  → live GET https://generativelanguage.googleapis.com/v1beta/models
      - Database     → SELECT 1 via the configured SQLAlchemy engine
      - FRED / Finnhub / Alpha Vantage → configured?
    """
    from app.core.config import settings

    checks: dict[str, dict] = {}

    # ── Gemini / Vertex AI keys (live) ──────────────────────────────────────
    gemini = []

    if settings.USE_VERTEX or settings.GOOGLE_CLOUD_PROJECT:
        # Vertex AI is configured, mock "ok" status for Vertex AI
        gemini.append(
            {
                "name": "VERTEX_AI",
                "status": "ok",
                "detail": f"Configured via Vertex AI (Project: {settings.GOOGLE_CLOUD_PROJECT})",
            }
        )
    else:
        gkeys = {
            "GOOGLE_API_KEY_1": settings.LLM_API_KEY_1,
            "GOOGLE_API_KEY_2": settings.LLM_API_KEY_2,
            "GOOGLE_API_KEY_3": settings.LLM_API_KEY_3,
        }
        async with httpx.AsyncClient() as client:
            for name, key in gkeys.items():
                if not key:
                    gemini.append(
                        {"name": name, "status": "missing", "detail": "not set"}
                    )
                    continue
                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
                    resp = await client.get(url, timeout=5.0)
                    if resp.status_code == 200:
                        gemini.append(
                            {"name": name, "status": "ok", "detail": "Valid key"}
                        )
                    else:
                        try:
                            err = (
                                resp.json()
                                .get("error", {})
                                .get("message", f"HTTP {resp.status_code}")
                            )
                        except Exception:
                            err = f"HTTP {resp.status_code}"
                        gemini.append({"name": name, "status": "error", "detail": err})
                except Exception as e:
                    gemini.append({"name": name, "status": "error", "detail": str(e)})

    checks["gemini"] = gemini

    # ── Database (live SELECT 1) ────────────────────────────────────────────
    db_check = {"status": "error", "detail": "unknown"}
    try:
        from app.core.config import SessionLocal
        from sqlalchemy import text as _text

        if not SessionLocal:
            db_check = {
                "status": "error",
                "detail": "SessionLocal not initialized (DB connect failed at startup)",
            }
        else:
            db = SessionLocal()
            try:
                db.execute(_text("SELECT 1"))
                url = settings.DATABASE_URL or ""
                safe = (
                    url.split("@")[-1]
                    if "@" in url
                    else ("sqlite" if "sqlite" in url else "unknown")
                )
                db_check = {"status": "ok", "detail": f"SELECT 1 ok ({safe})"}
            finally:
                db.close()
    except Exception as e:
        db_check = {"status": "error", "detail": f"{type(e).__name__}: {e}"}
    checks["database"] = db_check

    # ── Data-provider keys ──────────────────────────────────────────────────
    providers = []
    for env_name in ("FRED_API_KEY", "FINNHUB_API_KEY", "ALPHA_VANTAGE_API_KEY"):
        val = os.getenv(env_name, "")
        providers.append(
            {
                "name": env_name,
                "status": "configured" if val else "missing",
                "detail": "env var set"
                if val
                else "not set (provider falls back / skips)",
            }
        )
    checks["data_providers"] = providers

    # ── Vertex MCP Server ───────────────────────────────────────────────────
    if settings.USE_VERTEX or settings.GOOGLE_CLOUD_PROJECT:
        checks["vertex_mcp"] = {"status": "ok", "detail": "Vertex MCP Enabled"}
    else:
        checks["vertex_mcp"] = {"status": "missing", "detail": "Vertex MCP Not Enabled"}

    # ── Arize MCP Server ────────────────────────────────────────────────────
    if settings.ARIZE_MCP_ENABLED:
        checks["arize_mcp"] = {"status": "ok", "detail": "Arize MCP Enabled"}
    else:
        checks["arize_mcp"] = {"status": "missing", "detail": "MCP Not Enabled"}

    # ── Vertex AI check ─────────────────────────────────────────────────────
    vertex_ok = False
    if settings.USE_VERTEX:
        checks["vertex_ai"] = {
            "status": "active",
            "detail": f"project={settings.GOOGLE_CLOUD_PROJECT}, location={settings.GOOGLE_CLOUD_LOCATION}",
        }
        vertex_ok = True

    # ── Top-level ok ────────────────────────────────────────────────────────
    # When Vertex AI is active, Gemini API keys are NOT required.
    gemini_ok = all(k["status"] in ("ok", "missing") for k in gemini) and any(
        k["status"] == "ok" for k in gemini
    )
    live_ok = (gemini_ok or vertex_ok) and db_check["status"] == "ok"

    return {"ok": live_ok, "checks": checks}


@app.get("/debug/summary", tags=["QA"], summary="Consolidated debug snapshot")
def debug_summary(failures_limit: int = 100, agent_logs_limit: int = 50):
    """
    Returns a consolidated debug snapshot:
    - Recent structured pipeline failures (from JSONL)
    - MCP server health
    - Recent AgentLogs from DB (agent name, status, error, latency, run_id)
    - Recent Runs from DB (id, status, workflow_name, started_at, completed_at)
    - Discovery job queue state
    - Analysis dispatcher state (per run_id summary)
    """
    import datetime

    # 1. Pipeline failures from JSONL
    from app.services.failure_log import get_recent_failures

    failures = get_recent_failures(limit=failures_limit)

    # 2. MCP health
    from app.services.mcp_client import is_healthy as mcp_is_healthy

    mcp_health = mcp_is_healthy()

    # 3. AgentLogs from DB (most recent N rows, FAILED ones first then rest)
    agent_logs = []
    try:
        from app.core.config import SessionLocal
        from app.db.models import AgentLogs

        if SessionLocal:
            db = SessionLocal()
            try:
                rows = (
                    db.query(AgentLogs)
                    .order_by(AgentLogs.created_at.desc())
                    .limit(agent_logs_limit)
                    .all()
                )
                for r in rows:
                    agent_logs.append(
                        {
                            "id": str(r.id),
                            "run_id": str(r.run_id) if r.run_id else None,
                            "agent_name": r.agent_name,
                            "agent_type": r.agent_type,
                            "status": r.status,
                            "error": r.error,
                            "latency_ms": float(r.latency_ms)
                            if r.latency_ms is not None
                            else None,
                            "model_used": r.model_used,
                            "signal": r.signal,
                            "confidence": float(r.confidence)
                            if r.confidence is not None
                            else None,
                            "tokens_input": r.tokens_input,
                            "tokens_output": r.tokens_output,
                            "cost_usd": float(r.cost_usd)
                            if r.cost_usd is not None
                            else None,
                            "retry_count": r.retry_count,
                            "created_at": r.created_at.isoformat()
                            if r.created_at
                            else None,
                        }
                    )
            finally:
                db.close()
    except Exception as e:
        agent_logs = [{"error": f"DB read failed: {e}"}]

    # 4. Recent Runs from DB
    recent_runs = []
    try:
        from app.core.config import SessionLocal
        from app.db.models import Runs

        if SessionLocal:
            db = SessionLocal()
            try:
                rows = db.query(Runs).order_by(Runs.started_at.desc()).limit(20).all()
                for r in rows:
                    recent_runs.append(
                        {
                            "id": str(r.id),
                            "workflow_name": r.workflow_name,
                            "status": r.status,
                            "started_at": r.started_at.isoformat()
                            if r.started_at
                            else None,
                            "completed_at": r.completed_at.isoformat()
                            if r.completed_at
                            else None,
                            "elapsed_sec": round(
                                (r.completed_at - r.started_at).total_seconds(), 1
                            )
                            if r.completed_at and r.started_at
                            else None,
                        }
                    )
            finally:
                db.close()
    except Exception as e:
        recent_runs = [{"error": f"DB read failed: {e}"}]

    # 5. Discovery job queue state
    discovery_jobs = []
    try:
        from app.services.discovery_cache import list_jobs

        discovery_jobs = list_jobs(limit=10)
    except Exception as e:
        discovery_jobs = [{"error": str(e)}]

    # 6. Analysis dispatcher state
    dispatch_state = {}
    try:
        from app.services.analysis_dispatcher import (
            get_status,
            _status_store,
            _status_lock,
        )
        import threading

        with _status_lock:
            run_ids = list(_status_store.keys())
        for rid in run_ids[-5:]:  # last 5 run_ids
            dispatch_state[rid] = get_status(rid)
    except Exception as e:
        dispatch_state = {"error": str(e)}

    # Discovery job results embed raw screener stock data (RSI/close/…) that can
    # contain NaN/inf floats. FastAPI's JSON encoder rejects those with HTTP 500
    # ("Out of range float values are not JSON compliant"). Scrub them to null so
    # the Debug Console stays alive once a discovery job has run.
    return _json_safe(
        {
            "generated_at": datetime.datetime.utcnow().isoformat(),
            "failures": failures,
            "failures_count": len(failures),
            "mcp": mcp_health,
            "agent_logs": agent_logs,
            "recent_runs": recent_runs,
            "discovery_jobs": discovery_jobs,
            "dispatch_state": dispatch_state,
        }
    )


def _json_safe(obj):
    """Recursively replace NaN/inf floats with None so the result is JSON-compliant.
    FastAPI's default encoder raises on non-finite floats (which leak in via raw
    screener data inside discovery job results)."""
    import math

    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


# ── /logs HTML page ──────────────────────────────────────────────────────
# Standalone debug UI at /logs. Reads the existing /debug/summary JSON every
# 30s and renders failures + agent logs + runs + jobs in a single page.
# Route is registered BEFORE the static mount below so it wins over the
# StaticFiles catch-all.
from fastapi.responses import FileResponse
from pathlib import Path as _Path

_LOGS_HTML = _Path(__file__).parent.parent / "frontend" / "logs.html"
_AGENTLOGS_HTML = _Path(__file__).parent.parent / "frontend" / "agentlogs.html"
_EVALS_HTML = _Path(__file__).parent.parent / "frontend" / "evals.html"


@app.get("/logs", include_in_schema=False)
def logs_page():
    """Standalone debug UI: pipeline failures, agent logs, recent runs, MCP status."""
    return FileResponse(str(_LOGS_HTML), media_type="text/html")


@app.get("/agentlogs", include_in_schema=False)
def agentlogs_page():
    """Detailed per-agent drill-down UI: run list → agent timeline → per-agent payloads."""
    return FileResponse(str(_AGENTLOGS_HTML), media_type="text/html")


@app.get("/")
def health_check():
    return {"status": "ok", "message": "ArthaVest API is running"}
