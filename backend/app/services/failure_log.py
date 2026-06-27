"""
Structured failure logger for the Quant AI pipeline.

Any agent node or service that catches an error can call:
    from app.services.failure_log import log_failure
    log_failure(feature="economic_node", stage="llm_invoke", error=e)

Entries are appended to qa_logs/failed_log.jsonl (shared with the QA runner)
AND written to graphify-out/pipeline_failures.jsonl for easy browsing.

Format (one JSON object per line):
    {
      "ts":         "2026-05-10T13:44:26Z",
      "run_id":     "<uuid>",
      "feature":    "agent.economic_node",
      "stage":      "llm_invoke",
      "error_type": "PermissionDenied",
      "error":      "403 Your project has been denied...",
      "symbol":     "TATACHEM.NS",    # optional
      "elapsed_sec": 2.3              # optional
    }
"""

import json
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path
from app.core.config import logger

# ── Paths (relative to the app root so they work on Render/Docker) ──────────
# _REPO_ROOT points at the `app/` directory. All log dirs default INSIDE the
# app so read-only deploys and container builds don't try to write a sibling
# directory that isn't part of the deployable. Both paths are env-overridable.
_REPO_ROOT = Path(__file__).parent.parent.resolve()

# Primary: app/qa_logs/failed_log.jsonl
_QA_LOG_DIR = Path(os.getenv("QA_LOG_DIR", str(_REPO_ROOT / "qa_logs")))
_QA_FAIL_LOG = _QA_LOG_DIR / "failed_log.jsonl"

# Secondary: app/qa_logs/pipeline_failures.jsonl (was ../graphify-out which sat
# outside the app and broke on Docker/Render deploys).
_GRAPHIFY_DIR = Path(os.getenv("GRAPHIFY_OUT_DIR", str(_QA_LOG_DIR)))
_GRAPHIFY_FAIL_LOG = _GRAPHIFY_DIR / "pipeline_failures.jsonl"


def _ensure_dirs():
    _QA_LOG_DIR.mkdir(parents=True, exist_ok=True)
    _GRAPHIFY_DIR.mkdir(parents=True, exist_ok=True)


def log_failure(
    feature: str,
    stage: str,
    error: Exception | str,
    run_id: str = "",
    symbol: str = "",
    elapsed_sec: float | None = None,
) -> None:
    """
    Append one structured failure entry to both failure logs.
    Safe to call from any thread — each write is a single atomic line append.

    Args:
        feature:     Dotted name, e.g. "agent.economic_node", "mcp.economic.get_full_snapshot"
        stage:       Sub-step where the failure occurred, e.g. "llm_invoke", "tool_call", "db_persist"
        error:       Exception object or plain string description
        run_id:      Pipeline run_id (from AnalysisState)
        symbol:      Stock symbol being processed, if any
        elapsed_sec: How long the step took before it failed
    """
    error_str = str(error)
    error_type = type(error).__name__ if isinstance(error, Exception) else "Error"
    tb = traceback.format_exc() if isinstance(error, Exception) else ""

    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "feature": feature,
        "stage": stage,
        "error_type": error_type,
        "error": error_str,
        "symbol": symbol,
        "elapsed_sec": elapsed_sec,
        "traceback": tb,
    }

    line = json.dumps(entry) + "\n"

    try:
        _ensure_dirs()
        with _QA_FAIL_LOG.open("a", encoding="utf-8") as f:
            f.write(line)
        _trim_log(_QA_FAIL_LOG)
    except Exception as write_err:
        logger.warning(
            f"[yellow]failure_log: could not write to {_QA_FAIL_LOG}: {write_err}[/yellow]"
        )

    try:
        with _GRAPHIFY_FAIL_LOG.open("a", encoding="utf-8") as f:
            f.write(line)
        _trim_log(_GRAPHIFY_FAIL_LOG)
    except Exception as write_err:
        logger.warning(
            f"[yellow]failure_log: could not write to {_GRAPHIFY_FAIL_LOG}: {write_err}[/yellow]"
        )

    logger.warning(
        f"[bold yellow]FAILURE LOGGED[/bold yellow] | "
        f"feature={feature} | stage={stage} | "
        f"symbol={symbol or 'N/A'} | {error_type}: {error_str[:120]}"
    )


_LOG_MAX_LINES = int(os.getenv("FAILURE_LOG_MAX_LINES", "1000"))


def _trim_log(path: Path) -> None:
    """Keep only the last _LOG_MAX_LINES lines to prevent unbounded growth."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        if len(lines) > _LOG_MAX_LINES:
            path.write_text("".join(lines[-_LOG_MAX_LINES:]), encoding="utf-8")
    except Exception:
        pass


def get_recent_failures(limit: int = 50) -> list[dict]:
    """Return the most recent `limit` failure entries from the primary log."""
    if not _QA_FAIL_LOG.exists():
        return []
    entries = []
    try:
        with _QA_FAIL_LOG.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except Exception:
        return []
    return entries[-limit:]


def clear_all_logs() -> dict:
    """Truncate all failure log files and return summary of what was cleared."""
    cleared = {"files_cleared": [], "entries_removed": 0}

    for path in (_QA_FAIL_LOG, _GRAPHIFY_FAIL_LOG):
        if path.exists():
            try:
                # Count entries before clearing
                with path.open(encoding="utf-8") as f:
                    count = sum(1 for line in f if line.strip())
                cleared["entries_removed"] += count
                # Truncate the file
                path.write_text("", encoding="utf-8")
                cleared["files_cleared"].append(str(path))
            except Exception as e:
                logger.warning(
                    f"[yellow]clear_all_logs: could not clear {path}: {e}[/yellow]"
                )

    return cleared
