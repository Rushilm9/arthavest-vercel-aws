"""
MCP Client — HTTP bridge to the deployed Quant AI MCP Server.

All agents call:
    mcp("tool.name", {"param": value})

The server exposes POST /call with body:
    {"tool": "tool.name", "arguments": {...}}

mcp_safe() returns `default` on any failure so callers can fall back
to local yfinance/feedparser/TradingView implementations gracefully.

Hardening (TEST_REPORT.md):
- Single shared requests.Session (TCP connection pooling)
- Bounded retry/backoff on connection errors and 5xx responses
- Lightweight in-process health cache so callers can skip MCP fast when down
- Optional health probe: ping() + is_healthy()
"""

import os
import time
import threading
import requests
from app.core.config import settings, logger

# ── Configuration ─────────────────────────────────────────────────────────────
MCP_BASE_URL: str = settings.MCP_SERVER_URL.rstrip("/")

MCP_TIMEOUT: int = settings.MCP_TIMEOUT
MCP_RETRIES: int = settings.MCP_RETRIES  # extra attempts after the first
MCP_HEALTH_TTL: int = settings.MCP_HEALTH_TTL  # cache health result for N seconds

_CALL_URL = f"{MCP_BASE_URL}/call"
_HEALTH_URL = f"{MCP_BASE_URL}/health"

_session = requests.Session()
_health_lock = threading.Lock()
_health_cache: dict = {"ok": None, "checked_at": 0.0, "detail": None}


class MCPError(RuntimeError):
    """Raised when a tool call to the MCP server fails."""


# ── Public API ────────────────────────────────────────────────────────────────


def mcp(tool: str, arguments: dict | None = None) -> dict | list:
    """
    Call a tool on the deployed MCP server and return the result.

    Args:
        tool:       Full tool name, e.g. "economic.get_full_snapshot"
        arguments:  Dict of arguments (can be empty or None).

    Returns:
        The tool result (dict or list).

    Raises:
        MCPError on failure (after retries).
    """
    body = {"tool": tool, "arguments": arguments or {}}
    last_err: Exception | None = None

    attempts = max(1, MCP_RETRIES + 1)
    for i in range(attempts):
        try:
            resp = _session.post(_CALL_URL, json=body, timeout=MCP_TIMEOUT)
        except requests.exceptions.ConnectionError as e:
            last_err = e
            _backoff(i)
            continue
        except requests.exceptions.Timeout as e:
            # Don't retry timeouts on slow tools — bubble immediately
            raise MCPError(f"MCP timeout ({MCP_TIMEOUT}s) calling {tool}") from e
        except Exception as e:
            raise MCPError(f"MCP request error for {tool}: {e}") from e

        # Retry on 5xx, fail fast on 4xx
        if resp.status_code >= 500:
            last_err = MCPError(
                f"MCP HTTP {resp.status_code} for {tool}: {resp.text[:200]}"
            )
            _backoff(i)
            continue

        if not resp.ok:
            raise MCPError(f"MCP HTTP {resp.status_code} for {tool}: {resp.text[:200]}")

        try:
            data = resp.json()
        except Exception as e:
            raise MCPError(f"MCP returned non-JSON for {tool}: {e}") from e

        # Tool-level errors (e.g. rate-limit on one tool) must not mark the server
        # as unhealthy — the MCP server itself is up, only this tool call failed.
        if isinstance(data, dict) and "error" in data:
            raise MCPError(f"MCP tool error for {tool}: {data['error']}")

        # Success — refresh health cache opportunistically
        _record_health(True, "live call ok")
        return data

    # Exhausted retries — only poison health cache on TRUE connection-level failures.
    # 5xx responses mean the server is reachable but individual tools are broken;
    # the server itself is still healthy for other tools.
    _is_connection_err = last_err is not None and isinstance(
        last_err, (requests.exceptions.ConnectionError, ConnectionError)
    )
    if _is_connection_err:
        _record_health(False, str(last_err) if last_err else "unknown failure")
    raise MCPError(f"MCP call failed after {attempts} attempts for {tool}: {last_err}")


def mcp_safe(tool: str, arguments: dict | None = None, default=None):
    """
    Like mcp() but returns `default` instead of raising on error.
    Use this when you have a working local fallback.

    Skips the network call entirely if a recent health check failed,
    so we don't block every agent on a known-down MCP server.
    """
    if settings.DISABLE_MCP_FALLBACK:
        # Bypasses fallback behavior and goes directly to the mcp call which can raise MCPError on failure
        return mcp(tool, arguments)

    if not _is_recently_healthy():
        # One probe per TTL window; otherwise return default immediately
        if not ping():
            logger.warning(
                f"[yellow]MCP marked unhealthy; skipping {tool} → default[/yellow]"
            )
            return default

    try:
        return mcp(tool, arguments)
    except MCPError as e:
        logger.warning(f"[yellow]MCP safe call failed for {tool}: {e}[/yellow]")
        return default


def ping(force: bool = False) -> bool:
    """
    Probe the MCP server's /health endpoint, caching the result for
    MCP_HEALTH_TTL seconds. Returns True on 200, False otherwise.
    """
    with _health_lock:
        now = time.time()
        if (
            not force
            and _health_cache["ok"] is not None
            and now - _health_cache["checked_at"] < MCP_HEALTH_TTL
        ):
            return bool(_health_cache["ok"])

    ok = False
    detail = ""
    try:
        resp = _session.get(_HEALTH_URL, timeout=min(10, MCP_TIMEOUT))
        ok = resp.ok
        detail = f"HTTP {resp.status_code}"
    except Exception as e:
        ok = False
        detail = f"{type(e).__name__}: {e}"

    _record_health(ok, detail)
    return ok


def is_healthy() -> dict:
    """Return the current MCP health snapshot for /mcp/health endpoint."""
    ok = ping()
    return {
        "ok": ok,
        "base_url": MCP_BASE_URL,
        "timeout_sec": MCP_TIMEOUT,
        "retries": MCP_RETRIES,
        "checked_at": _health_cache["checked_at"],
        "detail": _health_cache["detail"],
    }


# ── Internals ─────────────────────────────────────────────────────────────────


def _backoff(attempt: int) -> None:
    # 0.5s, 1.0s, 2.0s — capped
    delay = min(2.0, 0.5 * (2**attempt))
    time.sleep(delay)


def _record_health(ok: bool, detail: str) -> None:
    with _health_lock:
        _health_cache["ok"] = bool(ok)
        _health_cache["detail"] = detail
        _health_cache["checked_at"] = time.time()


def _is_recently_healthy() -> bool:
    with _health_lock:
        if _health_cache["ok"] is None:
            return False
        if time.time() - _health_cache["checked_at"] > MCP_HEALTH_TTL:
            return False
        return bool(_health_cache["ok"])


def log_mcp_config() -> None:
    """Called once on startup so operators can see which MCP server is in use."""
    logger.info(
        f"[bold cyan]MCP client → {MCP_BASE_URL} "
        f"(timeout={MCP_TIMEOUT}s, retries={MCP_RETRIES}, health_ttl={MCP_HEALTH_TTL}s)[/bold cyan]"
    )
