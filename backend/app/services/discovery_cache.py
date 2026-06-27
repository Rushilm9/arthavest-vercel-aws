"""
Discovery Job Manager

Fire-and-poll pattern for F1 discovery runs.

  submit_job() -> job_id   # returns immediately
  get_job(job_id)          # poll for status / result
  list_jobs(limit)         # recent jobs

The in-memory `_cache` dict was removed. Discovery results are persisted to DB
(discovery_results table) and read back via fetch_discovery_run_buckets().
"""

from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from app.core.config import logger


# ── State ──────────────────────────────────────────────────────────────────────

_jobs: dict[
    str, dict
] = {}  # job_id -> {status, started_at, finished_at, elapsed_sec, error, result}
_jobs_lock = threading.Lock()

# Bounded job pool. We're CPU-light + LLM-bound, so a small pool is plenty.
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="discovery-job")


# ── Public API: jobs ──────────────────────────────────────────────────────────


def submit_job(horizon_filter: list[str] | None = None) -> str:
    """
    Submit a fresh discovery run and return a job_id immediately.
    Returns the existing job_id if a queued or running job already exists.
    Caller polls get_job(job_id) for status and results.

    horizon_filter: optional ["SHORT"], ["MID"], ["LONG"], or None for ALL.
    """
    with _jobs_lock:
        # Dedup: return existing active job if one is already pending or running
        for existing_id, job in _jobs.items():
            if job.get("status") in ("queued", "running"):
                logger.info(
                    f"[cyan]DiscoveryJobs: reusing in-flight job {existing_id}[/cyan]"
                )
                return existing_id

        job_id = str(uuid.uuid4())
        _jobs[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "started_at": None,
            "finished_at": None,
            "elapsed_sec": None,
            "error": None,
            "result": None,
            "horizon_filter": horizon_filter,
        }
    _executor.submit(_run_job, job_id, horizon_filter)
    logger.info(
        f"[bold cyan]DiscoveryJobs: queued job {job_id} horizon={horizon_filter or 'ALL'}[/bold cyan]"
    )
    return job_id


def get_job(job_id: str) -> Optional[dict]:
    """Return job snapshot or None if unknown."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def list_jobs(limit: int = 20) -> list[dict]:
    with _jobs_lock:
        items = list(_jobs.values())
    items.sort(
        key=lambda j: (j.get("started_at") or 0, j.get("finished_at") or 0),
        reverse=True,
    )
    return items[:limit]


# ── Internals ─────────────────────────────────────────────────────────────────


def _run_job(job_id: str, horizon_filter: list[str] | None = None) -> None:
    from app.agents.graph import run_discovery_pipeline

    t0 = time.time()
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id]["status"] = "running"
            _jobs[job_id]["started_at"] = t0

    try:
        result = run_discovery_pipeline(horizon_filter=horizon_filter)
        elapsed = round(time.time() - t0, 2)
        logger.info(
            f"[bold green]DiscoveryJobs: pipeline finished in {elapsed}s, persisting...[/bold green]"
        )

        # Persist to DB (failures here must NOT block the job from completing)
        run_id = result.get("run_id", "")
        buckets = result.get("discovered_buckets") or {}
        try:
            from app.services.discovery_persist import (
                persist_discovery_run,
                persist_market_regime,
                SessionLocal,
                _ist_today,
            )

            persist_discovery_run(run_id, result, buckets)
            persist_market_regime(
                result.get("macro_regime", "SIDEWAYS"),
                result.get("macro_confidence", 0.0),
                result.get("macro_triggers") or {},
                result.get("market_pulse_score", 50),
            )

            # Update economic snapshot with market pulse data
            from app.db.models import EconomicSnapshots

            db = SessionLocal()
            try:
                snap = (
                    db.query(EconomicSnapshots)
                    .filter(EconomicSnapshots.snapshot_date == _ist_today())
                    .first()
                )
                if snap:
                    if result.get("india_vix") is not None:
                        snap.india_vix = result.get("india_vix")
                    if result.get("nifty_level") is not None:
                        snap.nifty_level = result.get("nifty_level")
                    if result.get("advance_decline_ratio") is not None:
                        snap.advance_decline_ratio = result.get("advance_decline_ratio")
                    db.commit()
            except Exception:
                db.rollback()
            finally:
                db.close()
        except Exception as persist_err:
            logger.error(f"[red]DiscoveryJobs: persist failed — {persist_err}[/red]")

        # Mark job as done ONLY after persistence is complete
        with _jobs_lock:
            if job_id in _jobs:
                _jobs[job_id].update(
                    {
                        "status": "done",
                        "finished_at": time.time(),
                        "elapsed_sec": elapsed,
                        "result": result,
                    }
                )
        logger.info(
            f"[bold green]DiscoveryJobs: job {job_id} completely done and persisted[/bold green]"
        )

        # NOTE: Auto-dispatch of F2 was REMOVED to prevent runaway LLM costs.
        # F2 analysis now runs ONLY via explicit POST /analysis/analyze for
        # individual stocks the user selects.  (See rushil.md §6.1)

    except Exception as e:
        elapsed = round(time.time() - t0, 2)
        logger.error(
            f"[bold red]DiscoveryJobs: job {job_id} FAILED in {elapsed}s — {e}[/bold red]"
        )
        with _jobs_lock:
            if job_id in _jobs:
                _jobs[job_id].update(
                    {
                        "status": "error",
                        "finished_at": time.time(),
                        "elapsed_sec": elapsed,
                        "error": str(e),
                    }
                )


def shutdown() -> None:
    _executor.shutdown(wait=False, cancel_futures=True)
