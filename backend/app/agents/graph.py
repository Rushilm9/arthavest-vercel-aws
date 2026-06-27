"""
LangGraph — Graph Builder (F1/F2 final)

Discovery:
  START → economic → market_pulse → news → macro_context → planner → discovery → END

Analysis:
  START → economic → market_pulse → news → macro_context → planner
        → technical → fundamental → sentiment → chart_pattern
        → merge_signals → horizon_confirm → debate → decision → END
"""

import uuid
from langgraph.graph import StateGraph, END, START
from app.agents.state import AnalysisState

from app.agents.economic.node import economic_node
from app.agents.news.node import news_node
from app.agents.market_pulse.node import market_pulse_node
from app.agents.macro_context.node import macro_context_node
from app.agents.planner.node import planner_node
from app.agents.discovery.node import discovery_node

from app.agents.technical.node import technical_node
from app.agents.fundamental.node import fundamental_node
from app.agents.sentiment.node import sentiment_node
from app.agents.chart_pattern.node import chart_pattern_node
from app.agents.horizon_confirm.node import horizon_confirm_node
from app.agents.debate.node import debate_node
from app.agents.decision.node import decision_node
from app.agents.debate.tools import merge_worker_signals

from app.core.config import logger
from app.services.run_log import start_run, finish_run, track_agent
from app.services.failure_log import log_failure


from langgraph.types import RetryPolicy

# Retry policy for all LangGraph nodes (3 attempts max)
node_retry = RetryPolicy(max_attempts=3)


# ── AgentLogs telemetry ────────────────────────────────────────────────────
# Wrap every node with `track_agent` so each invocation writes one row into the
# agent_logs DB table (run_id, agent_name, status, latency_ms, signal, error).
# This populates the Debug page's "Agent Logs (DB)" section that was previously
# always empty. SUCCESS rows carry the node's emitted signal+confidence; FAILED
# rows carry the exception type+message. Decorator re-raises, so RetryPolicy
# still drives LangGraph retries.
_economic = track_agent("economic", "F1_CONTEXT")(economic_node)
_market_pulse = track_agent("market_pulse", "F1_CONTEXT")(market_pulse_node)
_news = track_agent("news", "F1_CONTEXT")(news_node)
_macro_context = track_agent("macro_context", "F1_CONTEXT")(macro_context_node)
_planner = track_agent("planner", "F1_PLANNER")(planner_node)
_discovery = track_agent("discovery", "F1_DISCOVERY")(discovery_node)
_technical = track_agent("technical", "F2_SPECIALIST")(technical_node)
_fundamental = track_agent("fundamental", "F2_SPECIALIST")(fundamental_node)
_sentiment = track_agent("sentiment", "F2_SPECIALIST")(sentiment_node)
_chart_pattern = track_agent("chart_pattern", "F2_SPECIALIST")(chart_pattern_node)
_horizon_confirm = track_agent("horizon_confirm", "F2_HORIZON")(horizon_confirm_node)
_debate = track_agent("debate", "F2_DEBATE")(debate_node)
_decision = track_agent("decision", "F2_DECISION")(decision_node)

# ═══════════════════════════════════════════════════════════════
# DISCOVERY GRAPH
# ═══════════════════════════════════════════════════════════════


def build_discovery_graph() -> StateGraph:
    graph = StateGraph(AnalysisState)

    graph.add_node("economic", _economic, retry=node_retry)
    graph.add_node("market_pulse", _market_pulse, retry=node_retry)
    graph.add_node("news", _news, retry=node_retry)
    graph.add_node("macro_context", _macro_context, retry=node_retry)
    graph.add_node("planner", _planner, retry=node_retry)
    graph.add_node("discovery", _discovery, retry=node_retry)

    graph.add_edge(START, "economic")
    graph.add_edge("economic", "market_pulse")
    graph.add_edge("market_pulse", "news")
    graph.add_edge("news", "macro_context")
    graph.add_edge("macro_context", "planner")
    graph.add_edge("planner", "discovery")
    graph.add_edge("discovery", END)

    compiled = graph.compile()
    logger.info("[green]LangGraph Discovery (F1) pipeline compiled.[/green]")
    return compiled


def run_discovery_pipeline(horizon_filter: list[str] | None = None) -> dict:
    """Run F1 discovery. When horizon_filter is set (e.g. ["SHORT"]), Stage 8 will
    only classify into those buckets — the others come back empty. Used by the
    per-horizon ▶ Run Discovery dropdown so users don't burn quota on horizons
    they won't analyse today."""
    graph = build_discovery_graph()
    initial_state: AnalysisState = _get_default_state("discover")
    if horizon_filter:
        valid = [h for h in horizon_filter if h in ("SHORT", "MID", "LONG")]
        if valid:
            initial_state["_horizon_filter"] = valid
    run_id = initial_state["run_id"]
    logger.info(
        f"[bold cyan]Starting Discovery Pipeline (run_id: {run_id}, "
        f"horizon_filter: {initial_state.get('_horizon_filter') or 'ALL'})[/bold cyan]"
    )
    # Persist a STARTED Runs row so failed runs appear on the Debug page.
    start_run(
        run_id=run_id,
        workflow_name="discovery_pipeline",
        workflow_config={
            "task": "discover",
            "horizon_filter": initial_state.get("_horizon_filter"),
        },
    )
    try:
        result = graph.invoke(initial_state)
    except Exception as e:
        finish_run(run_id=run_id, status="FAILED", error=str(e))
        log_failure("pipeline.discovery", "graph_invoke", e, run_id=run_id)
        raise
    buckets = result.get("discovered_buckets") or {"SHORT": [], "MID": [], "LONG": []}
    n = sum(len(buckets.get(h, [])) for h in ("SHORT", "MID", "LONG"))
    logger.info(
        f"[bold green]Discovery Pipeline complete. {n} stocks across 3 horizons.[/bold green]"
    )
    return result


# ═══════════════════════════════════════════════════════════════
# ANALYSIS GRAPH
# ═══════════════════════════════════════════════════════════════


def merge_signals_node(state: AnalysisState) -> dict:
    """Merge the 3 legacy worker outputs into merged_signals (chart kept separately)."""
    merged = merge_worker_signals(
        state.get("technical_output", {}) or {},
        state.get("fundamental_output", {}) or {},
        state.get("sentiment_output", {}) or {},
    )
    return {"merged_signals": merged}


def build_analysis_graph() -> StateGraph:
    graph = StateGraph(AnalysisState)

    # Pre-amble (same upstream as Discovery)
    graph.add_node("economic", _economic, retry=node_retry)
    graph.add_node("market_pulse", _market_pulse, retry=node_retry)
    graph.add_node("news", _news, retry=node_retry)
    graph.add_node("macro_context", _macro_context, retry=node_retry)
    graph.add_node("planner", _planner, retry=node_retry)

    # 4 specialists
    graph.add_node("technical", _technical, retry=node_retry)
    graph.add_node("fundamental", _fundamental, retry=node_retry)
    graph.add_node("sentiment", _sentiment, retry=node_retry)
    graph.add_node("chart_pattern", _chart_pattern, retry=node_retry)

    # Merge → horizon confirm → debate → decision
    graph.add_node("merge_signals", merge_signals_node, retry=node_retry)
    graph.add_node("horizon_confirm", _horizon_confirm, retry=node_retry)
    graph.add_node("debate", _debate, retry=node_retry)
    graph.add_node("decision", _decision, retry=node_retry)

    # Wiring
    graph.add_edge(START, "economic")
    graph.add_edge("economic", "market_pulse")
    graph.add_edge("market_pulse", "news")
    graph.add_edge("news", "macro_context")
    graph.add_edge("macro_context", "planner")

    # Parallel fan-out: all 4 specialists run concurrently after planner
    graph.add_edge("planner", "technical")
    graph.add_edge("planner", "fundamental")
    graph.add_edge("planner", "sentiment")
    graph.add_edge("planner", "chart_pattern")

    # Fan-in at merge_signals
    graph.add_edge("technical", "merge_signals")
    graph.add_edge("fundamental", "merge_signals")
    graph.add_edge("sentiment", "merge_signals")
    graph.add_edge("chart_pattern", "merge_signals")
    graph.add_edge("merge_signals", "horizon_confirm")
    graph.add_edge("horizon_confirm", "debate")  # ← always run
    graph.add_edge("debate", "decision")
    graph.add_edge("decision", END)

    compiled = graph.compile()
    logger.info("[green]LangGraph Analysis (F2) pipeline compiled.[/green]")
    return compiled


def run_analysis_pipeline(
    symbol: str,
    suggested_horizon: str | None = None,
    f1_catalyst: str | None = None,
    f1_reasoning: str | None = None,
    f1_discovery_score: int | None = None,
) -> dict:
    graph = build_analysis_graph()
    initial_state: AnalysisState = _get_default_state(
        "analyze", symbol, suggested_horizon
    )
    # Embed F1 passthrough so decision node can persist them on the recommendations row
    if f1_catalyst or f1_reasoning or f1_discovery_score is not None:
        initial_state["_f1_catalyst"] = f1_catalyst
        initial_state["_f1_reasoning"] = f1_reasoning
        initial_state["_f1_horizon"] = suggested_horizon
        initial_state["_f1_discovery_score"] = f1_discovery_score
    run_id = initial_state["run_id"]
    logger.info(
        f"[bold cyan]Starting Analysis Pipeline for {symbol} "
        f"(run_id: {run_id}, suggested_horizon: {suggested_horizon})[/bold cyan]"
    )
    # Persist a STARTED Runs row so failed runs are visible on the Debug page.
    # Note: decision_node.persist_recommendation later inserts its OWN Runs row
    # via the legacy path. finish_run() updates whichever row reached the DB first.
    start_run(
        run_id=run_id,
        workflow_name="analysis_pipeline",
        workflow_config={
            "task": "analyze",
            "symbol": symbol,
            "suggested_horizon": suggested_horizon,
        },
        symbol=symbol,
    )
    try:
        result = graph.invoke(initial_state)
    except Exception as e:
        finish_run(run_id=run_id, status="FAILED", error=str(e))
        log_failure(
            "pipeline.analysis", "graph_invoke", e, run_id=run_id, symbol=symbol or ""
        )
        raise
    finish_run(run_id=run_id, status="COMPLETED")
    rec = result.get("final_recommendation", {}) or {}
    logger.info(
        f"[bold green]Analysis Pipeline done — {symbol}: "
        f"{rec.get('recommendation', 'N/A')} @ {rec.get('confidence', 0)}%[/bold green]"
    )

    # ── Eval annotation on the decision span (Phase 3b) ────────
    # Deterministic eval: PASS = (validator accepted AND confidence >= threshold)
    # OR the decision is WAIT (refusing correctly = good behaviour).
    try:
        from app.core.eval_annotate import annotate_decision

        span_id = result.get("decision_span_id")
        if span_id:
            action = rec.get("recommendation", "")
            validator_ok = result.get("validator_status", "") == "accepted"
            confidence = rec.get("confidence", 0)
            # WAIT with low confidence is a PASS — the agent correctly refused.
            if action == "WAIT":
                passed = True
                explanation = (
                    f"WAIT decision (confidence={confidence}%). "
                    f"Agent correctly refused a low-conviction trade."
                )
            else:
                passed = validator_ok and confidence >= 60
                explanation = (
                    f"{action} decision: validator={'accepted' if validator_ok else 'rejected'}, "
                    f"confidence={confidence}%"
                )
            annotate_decision(span_id=span_id, passed=passed, explanation=explanation)
    except Exception as e:
        logger.warning(
            f"[yellow]Eval annotation wiring error (non-fatal): {e}[/yellow]"
        )

    return result


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════


def _get_default_state(
    task: str, symbol: str = None, suggested_horizon: str | None = None
) -> AnalysisState:
    """Initialize every TypedDict field — LangGraph requires this."""
    return {
        "task": task,
        "stock_symbol": symbol,
        "run_id": str(uuid.uuid4()),
        # Horizon
        "suggested_horizon": suggested_horizon,
        "final_horizon": None,
        "horizon_override_reason": None,
        # Economic
        "economic_score": 50,
        "economic_regime": "STABLE",
        "overweight_sectors": [],
        "underweight_sectors": [],
        "economic_positives": [],
        "economic_risks": [],
        # Market pulse
        "macro_regime": "SIDEWAYS",
        "macro_confidence": 0.0,
        "macro_triggers": {},
        "market_pulse_score": 50,
        "india_vix": 0.0,
        "nifty_level": 0.0,
        "advance_decline_ratio": 0.0,
        "sector_strength": [],
        "breadth_signal": "HEALTHY",
        "market_health": "MODERATE",
        # News
        "market_sentiment": 0.0,
        "hot_sectors": [],
        "avoid_sectors": [],
        "anomaly_alerts": [],
        # Planner
        "planner_plan": {},
        # Discovery
        "discovered_symbols": None,
        "discovered_buckets": {"SHORT": [], "MID": [], "LONG": []},
        # Specialists
        "technical_output": {},
        "fundamental_output": {},
        "sentiment_output": {},
        "chart_pattern_output": {},
        # Merge & Debate
        "merged_signals": {},
        "debate_triggered": False,
        "debate_output": None,
        "max_decision_confidence": 1.0,
        "debate_disagreement": False,
        # Final
        "final_recommendation": {},
        "validator_issues": [],
        "validator_status": "accepted",
        "decision_span_id": None,
        "errors": [],
        # Internal pass-throughs
        "_economic_indicators": None,
        "_f1_horizon": None,
        "_f1_catalyst": None,
        "_f1_reasoning": None,
        "_f1_discovery_score": None,
        "_horizon_filter": None,
    }
