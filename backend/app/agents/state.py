"""
AnalysisState — The shared state schema for the LangGraph pipeline.
Every agent reads from and writes to this TypedDict.

Updated for F1/F2 final strategy:
- Per-horizon classification (SHORT / MID / LONG)
- Economic + News context as first-class state
- Chart Pattern as 4th specialist
- Validator output (issues + status)
- Debate confidence cap propagation
"""

from typing import TypedDict, Optional, Annotated
import operator


class AnalysisState(TypedDict):
    # ── Task Metadata ──────────────────────────────────────────
    task: str  # "discover" | "analyze"
    stock_symbol: Optional[str]  # None in discovery mode, "RELIANCE" in direct
    run_id: str  # UUID string for this execution

    # ── Horizon (F1/F2) ────────────────────────────────────────
    suggested_horizon: Optional[str]  # SHORT/MID/LONG from F1
    final_horizon: Optional[str]  # confirmed or overridden after F2 stage 2
    horizon_override_reason: Optional[str]

    # ── Economic Context (F1 Stage 1) ──────────────────────────
    economic_score: int  # 0-100
    economic_regime: str  # EXPANSION/STABLE/SLOWING/CONTRACTION
    overweight_sectors: list
    underweight_sectors: list
    economic_positives: list
    economic_risks: list

    # ── Phase 1: Market Pulse (F1 Stage 2) ─────────────────────
    macro_regime: str  # BULL/SIDEWAYS/BEAR/CRISIS (was BULL/BEAR/VOLATILE/CRISIS)
    macro_confidence: float
    macro_triggers: dict
    market_pulse_score: int
    india_vix: float
    nifty_level: float
    advance_decline_ratio: float
    sector_strength: list  # [{sector, rank}]
    breadth_signal: str  # HEALTHY/DETERIORATING/COLLAPSED
    market_health: str  # STRONG/MODERATE/WEAK/FRAGILE

    # ── News Context (F1 Stage 3) ──────────────────────────────
    market_sentiment: float  # -1.0 to +1.0
    hot_sectors: list
    avoid_sectors: list
    anomaly_alerts: list

    # ── Planner Output (F1 Stage 5) ────────────────────────────
    planner_plan: (
        dict  # per-horizon strategies + active_horizons + flat fallback weights
    )

    # ── Discovery Output (F1 Stages 6-8) ───────────────────────
    discovered_symbols: Optional[list]  # legacy flat list
    discovered_buckets: dict  # {"SHORT": [...], "MID": [...], "LONG": [...]}

    # ── Worker Agent Outputs (F2 Stage 1) ──────────────────────
    technical_output: dict
    fundamental_output: dict
    sentiment_output: dict
    chart_pattern_output: dict  # NEW 4th specialist

    # ── Post-Merge ─────────────────────────────────────────────
    merged_signals: dict
    debate_triggered: bool
    debate_output: Optional[dict]

    # ── Confidence cap from Debate (F2 Stage 3) ────────────────
    max_decision_confidence: float  # 1.0 default; 0.70 if debate disagrees
    debate_disagreement: bool

    # ── Final Output (F2 Stage 4 + 4b) ─────────────────────────
    final_recommendation: dict
    validator_issues: list  # [{layer, field, action, before, after}]
    validator_status: str  # accepted | rejected_forced_wait
    decision_span_id: Optional[
        str
    ]  # OpenTelemetry span ID for eval annotation (Phase 3b)
    errors: Annotated[list[str], operator.add]

    # ── Internal / pass-through fields ──────────────────────────
    _economic_indicators: Optional[
        dict
    ]  # raw fetch_economic_indicators() output (F1 only)
    _f1_horizon: Optional[str]  # F1 horizon suggestion threaded into F2
    _f1_catalyst: Optional[str]  # F1 catalyst text threaded into F2
    _f1_reasoning: Optional[str]  # F1 reasoning text threaded into F2
    _f1_discovery_score: Optional[
        int
    ]  # F1 discovery_score threaded into F2 for persist
    _horizon_filter: Optional[
        list
    ]  # Discovery only: user-requested horizon subset (e.g. ["SHORT"])

    # ── Debug / Testing ─────────────────────────────────────────
    _debug_mode: Optional[bool]  # Used by test-agent endpoint to enable tracing
    _mock_data: Optional[dict]  # Used by test-agent endpoint to bypass tools
    _custom_api_key: Optional[str]  # Custom model API key for side-by-side comparison
    _custom_model: Optional[str]  # Custom model ID for side-by-side comparison
