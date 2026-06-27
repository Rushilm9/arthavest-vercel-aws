"""
Pipeline run lifecycle helpers.

Every pipeline run (Discovery F1 or Analysis F2) gets a Runs row:
  • status="STARTED"   — written immediately when the pipeline begins, so the
                          Debug page can see in-flight runs and runs that
                          crashed before reaching the persistence step.
  • status="COMPLETED" — written on successful pipeline return.
  • status="FAILED"    — written when the LangGraph invoke() raises.

Each agent inside the run can also log a per-agent row to the `agent_logs`
table via `log_agent_run()` (status / latency / tokens / cost / error).

Both helpers are best-effort: a DB hiccup logs a warning and does not raise.
"""

from __future__ import annotations

import datetime as _dt
import functools
import time
import uuid
from typing import Optional

from app.core.config import logger


def _session():
    """Lazy import so a missing DB at boot doesn't kill the module."""
    from app.core.config import SessionLocal  # type: ignore

    return SessionLocal


def start_run(
    run_id: str,
    workflow_name: str,
    workflow_config: Optional[dict] = None,
    symbol: Optional[str] = None,
) -> None:
    """Insert a Runs row with status='STARTED'. Best-effort — never raises."""
    SessionLocal = _session()
    if SessionLocal is None:
        return
    try:
        from app.db.models import Runs, Stocks

        db = SessionLocal()
        try:
            stock_id = None
            if symbol:
                stock = db.query(Stocks).filter(Stocks.symbol == symbol.upper()).first()
                if stock:
                    stock_id = stock.id
            run = Runs(
                id=uuid.UUID(run_id) if isinstance(run_id, str) else run_id,
                stock_id=stock_id,
                workflow_name=workflow_name,
                workflow_config=workflow_config or {},
                status="STARTED",
                started_at=_dt.datetime.utcnow(),
            )
            db.add(run)
            db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.warning(
            f"[yellow]run_log.start_run: could not write Runs row: {e}[/yellow]"
        )


def finish_run(run_id: str, status: str, error: Optional[str] = None) -> None:
    """Update an existing Runs row's status + completed_at. Best-effort."""
    if status not in ("COMPLETED", "FAILED"):
        return
    SessionLocal = _session()
    if SessionLocal is None:
        return
    try:
        from app.db.models import Runs

        db = SessionLocal()
        try:
            rid = uuid.UUID(run_id) if isinstance(run_id, str) else run_id
            run = db.query(Runs).filter(Runs.id == rid).first()
            if run is None:
                # decision_node.persist_recommendation may have already inserted
                # its own Runs row (legacy path) — nothing to update here.
                return
            run.status = status
            run.completed_at = _dt.datetime.utcnow()
            if error and run.workflow_config is not None:
                cfg = dict(run.workflow_config)
                cfg["error"] = (error or "")[:500]
                run.workflow_config = cfg
            db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.warning(
            f"[yellow]run_log.finish_run: could not update Runs row: {e}[/yellow]"
        )


_MAX_TEXT_LEN = 5000  # truncate raw prompt/response so the DB doesn't bloat
_MAX_JSON_LEN = 8000  # truncate serialized JSON dicts (input/output/reasoning)


def _trunc_text(s, limit: int = _MAX_TEXT_LEN):
    """Truncate a string field for DB storage. Returns None for None/empty."""
    if s is None:
        return None
    try:
        s = str(s)
    except Exception:
        return None
    if not s:
        return None
    if len(s) <= limit:
        return s
    return s[:limit] + f"...[truncated {len(s) - limit} chars]"


def _safe_json_dict(obj, limit: int = _MAX_JSON_LEN):
    """Coerce an object to a JSON-serializable dict, truncating if it would exceed `limit` chars.
    Returns a dict (so JSONB column accepts it) or None."""
    if obj is None:
        return None
    if not isinstance(obj, dict):
        # Wrap non-dict values so JSONB stores them under a sentinel key
        obj = {"value": obj}
    import json

    try:
        serialized = json.dumps(obj, default=str, ensure_ascii=False)
    except Exception:
        try:
            serialized = json.dumps(
                _coerce_for_json(obj), default=str, ensure_ascii=False
            )
        except Exception:
            return None
    if len(serialized) <= limit:
        try:
            return json.loads(serialized)
        except Exception:
            return None
    # Truncate by serializing a summary
    return {
        "_truncated": True,
        "_original_size_chars": len(serialized),
        "_preview": serialized[:limit] + "...[truncated]",
    }


def _coerce_for_json(obj):
    """Best-effort coercion of non-serializable types."""
    if isinstance(obj, dict):
        return {str(k): _coerce_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_coerce_for_json(v) for v in obj]
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    return str(obj)


def log_agent_run(
    run_id: str,
    agent_name: str,
    agent_type: str,
    status: str,
    *,
    latency_ms: Optional[float] = None,
    error: Optional[str] = None,
    model_used: Optional[str] = None,
    signal: Optional[str] = None,
    confidence: Optional[float] = None,
    tokens_input: Optional[int] = None,
    tokens_output: Optional[int] = None,
    cost_usd: Optional[float] = None,
    retry_count: Optional[int] = None,
    # New: rich-capture fields (all optional; truncated automatically)
    input: Optional[dict] = None,  # whitelisted state snapshot at agent entry
    output: Optional[dict] = None,  # agent's return dict (or parsed LLM output)
    reasoning: Optional[dict] = None,  # PRO_THINK thinking trace / chain-of-reasoning
    prompt_template: Optional[str] = None,  # rendered prompt sent to the LLM
    raw_llm_response: Optional[str] = None,  # untouched LLM response text (pre-parsing)
) -> None:
    """Insert one row into agent_logs. Best-effort — never raises.

    Rich-capture fields (input/output/reasoning/prompt_template/raw_llm_response) are
    truncated automatically to keep DB rows bounded:
      - JSONB dicts: up to ~8KB serialized (summary stub if over)
      - text fields: up to 5KB (suffix indicates truncation)
    """
    if status not in ("SUCCESS", "FAILED"):
        status = "SUCCESS" if not error else "FAILED"
    SessionLocal = _session()
    if SessionLocal is None:
        return
    try:
        from app.db.models import AgentLogs

        db = SessionLocal()
        try:
            try:
                rid = uuid.UUID(run_id) if isinstance(run_id, str) else run_id
            except (ValueError, TypeError):
                rid = None
            row = AgentLogs(
                id=uuid.uuid4(),
                run_id=rid,
                agent_name=agent_name,
                agent_type=agent_type,
                status=status,
                error=_trunc_text(error, 2000),
                latency_ms=float(latency_ms) if latency_ms is not None else None,
                model_used=model_used,
                signal=signal,
                confidence=round(float(confidence), 2)
                if confidence is not None
                else None,
                tokens_input=int(tokens_input) if tokens_input is not None else None,
                tokens_output=int(tokens_output) if tokens_output is not None else None,
                cost_usd=round(float(cost_usd), 6) if cost_usd is not None else None,
                retry_count=int(retry_count) if retry_count is not None else 0,
                input=_safe_json_dict(input),
                output=_safe_json_dict(output),
                reasoning=_safe_json_dict(reasoning),
                prompt_template=_trunc_text(prompt_template),
                raw_llm_response=_trunc_text(raw_llm_response),
                created_at=_dt.datetime.utcnow(),
            )
            db.add(row)
            db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.warning(
            f"[yellow]run_log.log_agent_run: could not write AgentLogs row for {agent_name}: {e}[/yellow]"
        )


# Keys we whitelist from AnalysisState into the agent_logs.input snapshot.
# Avoid raw_screener / news_headlines / fundamentals_raw which can be 50-200KB each.
_INPUT_STATE_WHITELIST = {
    "stock_symbol",
    "run_id",
    "task",
    "final_horizon",
    "suggested_horizon",
    "macro_regime",
    "market_pulse_score",
    "economic_regime",
    "economic_score",
    "f1_catalyst",
    "f1_reasoning",
    "f1_discovery_score",
    "debate_disagreement",
    "max_decision_confidence",
}


def _snapshot_state(state) -> Optional[dict]:
    """Capture the whitelisted subset of AnalysisState as the agent's input snapshot."""
    if not isinstance(state, dict):
        return None
    snap = {}
    for k in _INPUT_STATE_WHITELIST:
        if k in state and state[k] is not None:
            snap[k] = state[k]
    return snap or None


def _snapshot_output(result) -> tuple[Optional[dict], Optional[str], Optional[float]]:
    """Extract a compact output snapshot + signal/confidence from a node's return dict."""
    if not isinstance(result, dict):
        return None, None, None
    signal = None
    confidence = None
    summary: dict = {}
    for k, v in result.items():
        # Specialist outputs: {"<name>_output": {...}}
        if isinstance(v, dict) and "signal" in v:
            if signal is None:
                signal = v.get("signal")
                confidence = v.get("confidence")
            # Capture the *_output dicts in the summary (these are the meaty payloads)
            summary[k] = {
                "signal": v.get("signal"),
                "confidence": v.get("confidence"),
                "narrative": (v.get("narrative") or "")[:600],
                "sub_scores": v.get("sub_scores"),
            }
        elif k in (
            "errors",
            "debate_disagreement",
            "max_decision_confidence",
            "final_horizon",
            "validator_status",
            "horizon_override_reason",
        ):
            summary[k] = v
    return (summary or None), signal, confidence


def track_agent(agent_name: str, agent_type: str = "F2_SPECIALIST"):
    """
    Decorator for LangGraph node functions. Writes one AgentLogs row per
    invocation capturing latency, status, error, input snapshot, and output
    summary. Re-raises exceptions so LangGraph's RetryPolicy still drives retries.

    The decorator's row writes `input` (whitelisted state) and `output` (summarized
    return dict) automatically. Nodes that also call log_agent_run() directly
    inside their handler (with full prompt/raw_llm_response/reasoning) will create
    a SECOND row — by design: the decorator's row is coarse telemetry that survives
    any internal failure; the inner row carries rich detail when the LLM call
    succeeded enough to capture it.
    """

    def _wrap(fn):
        @functools.wraps(fn)
        def _inner(state, *args, **kwargs):
            run_id = (state.get("run_id") if isinstance(state, dict) else "") or ""
            t0 = time.time()
            input_snap = _snapshot_state(state)
            # Reset the per-node token accumulator; the model callback fills it as
            # the node's LLM calls run, and we read it back after fn() returns.
            try:
                from app.core.model_router import reset_token_accumulator

                reset_token_accumulator()
            except Exception:
                pass
            try:
                result = fn(state, *args, **kwargs)
                elapsed_ms = (time.time() - t0) * 1000.0
                output_snap, signal, confidence = _snapshot_output(result)
                tok_in = tok_out = 0
                model_used = None
                cost = None
                try:
                    from app.core.model_router import (
                        read_token_accumulator,
                        compute_cost,
                    )

                    acc = read_token_accumulator()
                    tok_in, tok_out = acc["input"], acc["output"]
                    if tok_in or tok_out:
                        # Cost is an estimate; the exact per-tier model isn't known here.
                        cost = compute_cost("gemini-2.5-flash", tok_in, tok_out)
                except Exception:
                    pass
                log_agent_run(
                    run_id=run_id,
                    agent_name=agent_name,
                    agent_type=agent_type,
                    status="SUCCESS",
                    latency_ms=elapsed_ms,
                    signal=signal,
                    confidence=confidence,
                    tokens_input=tok_in or None,
                    tokens_output=tok_out or None,
                    cost_usd=cost,
                    model_used=model_used,
                    input=input_snap,
                    output=output_snap,
                )
                return result
            except Exception as e:
                elapsed_ms = (time.time() - t0) * 1000.0
                log_agent_run(
                    run_id=run_id,
                    agent_name=agent_name,
                    agent_type=agent_type,
                    status="FAILED",
                    latency_ms=elapsed_ms,
                    error=f"{type(e).__name__}: {e}"[:2000],
                    input=input_snap,
                )
                raise

        return _inner

    return _wrap
