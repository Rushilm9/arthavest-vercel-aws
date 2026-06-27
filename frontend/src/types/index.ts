// ── Shared ────────────────────────────────────────────────────
export type Signal = "BUY" | "SELL" | "HOLD" | "WAIT";
export type Horizon = "SHORT" | "MID" | "LONG";
export type EconomicRegime = "EXPANSION" | "STABLE" | "SLOWING" | "CONTRACTION";
export type MacroRegime = "BULL" | "SIDEWAYS" | "BEAR" | "CRISIS";

// ── Auth ──────────────────────────────────────────────────────
export interface AuthUser {
  id: string;
  email: string;
  created_at: string;
}

export interface AuthResponse {
  message: string;
  user: AuthUser;
}

export interface PriceTargets {
  buy_price?: number | null;
  target_price?: number | null;
  stop_loss?: number | null;
  risk_reward?: number | null;
  suggested_duration?: string | null;
}

// ── Discovery ─────────────────────────────────────────────────
export interface DiscoveredStock {
  symbol: string;
  close?: number | null;
  change_pct?: number | null;
  volume?: number | null;
  relative_volume?: number | null;
  rsi?: number | null;
  market_cap?: number | null;
  pe_ratio?: number | null;
  roe?: number | null;
  sector?: string | null;
  industry?: string | null;

  // F1 horizon classification
  horizon?: Horizon | null;
  discovery_score?: number | null;     // 0-100
  confidence?: number | null;
  rank?: number | null;
  catalyst?: string | null;             // ⭐ reasoning
  risk_flags: string[];
  indicative_target?: number | null;    // rough, NOT for trading
  suggested_hold_days?: number | null;

  // Enrichments
  news_headlines: string[];
  price_targets?: PriceTargets | null;
  ai_reasoning?: string | null;         // ⭐ reasoning
  pick_type?: "Technical" | "Fundamental" | "Both" | null;
  holding_period?: string | null;
  expected_return_pct?: number | null;

  // Technical snapshot
  atr?: number | null;
  ema20?: number | null;
  ema50?: number | null;
  ema200?: number | null;
  perf_week?: number | null;
  perf_1m?: number | null;
  perf_3m?: number | null;
  debt_to_equity?: number | null;
  net_margin?: number | null;
  price_book?: number | null;
  dividend_yield?: number | null;
}

export interface DiscoveryResponse {
  run_id: string;
  task: "discover";
  stocks_found: number;
  stocks: DiscoveredStock[];                // flat list (legacy)
  buckets: {
    SHORT: DiscoveredStock[];
    MID: DiscoveredStock[];
    LONG: DiscoveredStock[];
  };
  macro_regime: MacroRegime;
  market_pulse_score: number;
  economic_score?: number | null;
  economic_regime?: EconomicRegime | null;
  market_sentiment?: number | null;
  hot_sectors: string[];
  avoid_sectors: string[];
  active_horizons: Horizon[];
  ai_summary?: string | null;
  errors: string[];
  timestamp: string;
}

// ── Analyze (full F2 output) ──────────────────────────────────
export interface AgentSignals {
  technical: Signal;
  fundamental: Signal;
  sentiment: Signal;
  chart_pattern: Signal;
}

export interface TechnicalSummary {
  signal: Signal;
  confidence: number;          // 0..1
  narrative: string;           // ⭐ reasoning
  key_levels?: Record<string, unknown> | null;
  current_price?: number | null;
  atr?: number | null;
  rsi?: number | null;
  raw_data?: Record<string, unknown> | null;
  sub_scores?: Record<string, number> | null;
}

export interface FundamentalSummary {
  signal: Signal;
  confidence: number;          // 0..1
  weighted_score: number;
  narrative: string;           // ⭐ reasoning
  strengths: string[];          // ⭐ reasoning
  weaknesses: string[];         // ⭐ reasoning
  sub_scores?: Record<string, number> | null;
}

export interface SentimentSummary {
  signal: Signal;
  confidence: number;          // 0..1
  aggregate_score: number;      // -1..+1
  narrative: string;           // ⭐ reasoning
  key_themes: string[];         // ⭐ reasoning
  anomaly_count: number;
  headline_count: number;
  fallback_used: boolean;
  headlines: { text: string; source?: string; score: number }[];   // ⭐ reasoning support
  sub_scores?: Record<string, number> | null;
}

export interface ChartPatternSummary {
  signal: Signal;
  confidence: number;          // 0..1
  narrative: string;           // ⭐ reasoning
  patterns_detected: string[];  // ⭐ reasoning
  sub_scores?: Record<string, number> | null;
}

export interface DebateSummary {
  triggered: true;
  bull_case?: string | null;        // ⭐ ⭐ reasoning (highest signal)
  bear_case?: string | null;        // ⭐ ⭐ reasoning
  missed_risks: string[];           // ⭐ ⭐ reasoning
  independent_signal?: Signal | null;
  independent_confidence?: number | null;
  agrees_with_consensus?: boolean | null;
  synthesis?: string | null;        // ⭐ ⭐ reasoning
  evidence_citations: string[];     // ⭐ reasoning support
}

export interface ValidatorIssue {
  layer: 1 | 2 | 3;
  field: string;
  // Backend emits: rebuild_from_atr / rebuild_from_atr_v2 (L1), clamp_atr /
  // repair_from_atr / force_wait (L2), dampen / cap (L3). Kept open-ended so
  // new validator actions don't break the UI.
  action: string;
  before?: number | string | null;
  after?: number | string | null;
  rec_before?: string | null;
  note?: string | null;
}

export interface HorizonConfirmation {
  suggested_horizon?: Horizon | null;
  final_horizon?: Horizon | null;
  override_reason?: string | null;     // ⭐ reasoning
  horizon_scores: Record<string, number>;
}

export interface AnalyzeResponse {
  id?: string | null;                   // database PK (returned by history endpoints)
  run_id: string;
  symbol: string;
  company_name?: string | null;
  recommendation: Signal;
  confidence: number;                  // 0..100
  entry_price?: number | null;
  target_price?: number | null;
  stop_loss?: number | null;
  risk_reward?: number | null;
  upside_pct?: number | null;
  risk_pct?: number | null;
  profit_pct?: number | null;
  timeframe?: string | null;
  horizon_days?: number | null;
  position_size_pct?: number | null;
  narrative: string;                   // ⭐ ⭐ ⭐ decision narrative
  key_risks: string[];                 // ⭐ ⭐ ⭐
  key_catalysts: string[];             // ⭐ ⭐ ⭐
  agent_signals: AgentSignals;
  technical_summary?: TechnicalSummary | null;
  fundamental_summary?: FundamentalSummary | null;
  sentiment_summary?: SentimentSummary | null;
  chart_pattern_summary?: ChartPatternSummary | null;
  debate_summary?: DebateSummary | null;
  horizon_confirmation?: HorizonConfirmation | null;
  validator_issues: ValidatorIssue[];  // ⭐ reasoning (why values were clamped)
  validator_status: "accepted" | "rejected_forced_wait";
  macro_regime: MacroRegime;
  market_pulse_score: number;
  economic_score?: number | null;
  economic_regime?: EconomicRegime | null;
  horizon?: Horizon | null;
  recommendation_id?: string | null;
  cost_per_analysis?: number | null;       // ignore for POC
  cost_per_analysis_inr?: number | null;   // ignore for POC
  errors: string[];
  created_at?: string;
  timestamp?: string;
}

// ── Dispatch status ───────────────────────────────────────────
export interface DispatchSymbolStatus {
  status: "queued" | "running" | "done" | "error";
  started_at?: number | null;
  finished_at?: number | null;
  recommendation?: Signal | null;
  confidence?: number | null;
  entry_price?: number | null;
  target_price?: number | null;
  stop_loss?: number | null;
  risk_reward?: number | null;
  horizon?: Horizon | null;
  cost_inr?: number | null;
  recommendation_id?: string | null;
  full_response?: AnalyzeResponse | null;    // pre-built so you can render without a second fetch
  error?: string | null;
  reused?: boolean;
}

export interface DispatchStatusResponse {
  run_id: string;
  total: number;
  done: number;
  running: number;
  queued: number;
  errors: number;
  complete: boolean;
  stocks: Record<string, DispatchSymbolStatus>;   // keyed by symbol
}

// ── NEW endpoints the backend must add ────────────────────────
export interface MarketIndex {
  name: string;
  symbol: string;
  price: number;
  change: number;
  change_pct: number;
  error?: string;
}

export interface MarketNews {
  category: string;
  title: string;
  source: string;
  link: string;
  published: string;
}

export interface MarketDashboardResponse {
  indices: MarketIndex[];
  news: MarketNews[];
  fetched_at: number;
}

export interface PaginatedNewsResponse {
  count: number;
  page: number;
  total_pages: number;
  items: MarketNews[];
}

export interface MarketContextResponse {
  date: string;                      // IST date YYYY-MM-DD
  economic: {
    score: number;                   // 0-100
    regime: EconomicRegime;
    positives: string[];             // ⭐ reasoning
    risks: string[];                 // ⭐ reasoning
    overweight_sectors: string[];
    underweight_sectors: string[];
    reasoning: string;               // ⭐ ⭐ ⭐ narrative
    model_used: string;
    built_at: string;
  };
  market_pulse: {
    score: number;
    regime: MacroRegime;
    india_vix: number;
    nifty_level: number;
    advance_decline_ratio: number;
    sector_strength: { sector: string; rank: number }[];
    breadth_signal: "HEALTHY" | "DETERIORATING" | "COLLAPSED";
    market_health: "STRONG" | "MODERATE" | "WEAK" | "FRAGILE";
    reasoning: string;               // ⭐ deterministic
  };
  news: {
    market_sentiment: number | null;        // -1..+1
    hot_sectors: string[];
    avoid_sectors: string[];
    anomaly_alerts: string[];
    reasoning: string;               // ⭐ ⭐ narrative
    model_used: string;
  };
  macro_context: {
    regime: MacroRegime;
    confidence: number;
    triggers: Record<string, string>;
    reasoning: string;               // ⭐ ⭐ ⭐ THE most important pre-amble reasoning
    model_used: string;
  };
  planner: {
    active_horizons: Horizon[];
    overall_caution: "NORMAL" | "CAUTIOUS" | "ELEVATED" | "CRISIS";
    horizon_plans: Record<Horizon, {
      agent_weights: { technical: number; fundamental: number; sentiment: number; chart_pattern: number };
      min_conviction: number;
      strategy: string;              // ⭐ reasoning
    }>;
    reasoning: string;               // ⭐ ⭐ why these weights
  };
}

export interface QuotaTodayResponse {
  date: string;                      // IST date
  resets_at: string;                 // ISO timestamp when quota resets
  tiers: {
    pro: { used: number; ceiling: number; pct: number };       // gemini-2.5-pro
    flash: { used: number; ceiling: number; pct: number };     // gemini-3-flash-preview
    flash_lite: { used: number; ceiling: number; pct: number };// gemini-3.1-flash-lite
    gemini_flash: { used: number; ceiling: number; pct: number };      // gemini-1.5-flash
  };
}

export interface ApiKeyHealthItem {
  name: string;
  status: "ok" | "error" | "missing" | "configured";
  detail: string;
}

export interface ConnectionsHealthResponse {
  ok: boolean;
  checks: {
    gemini: ApiKeyHealthItem[];
    gemini_flash: ApiKeyHealthItem[];
    database: { status: "ok" | "error"; detail: string };
    data_providers: { name: string; status: "configured" | "missing"; detail: string }[];
  };
}

// Additional log types for §3.1 /logs endpoints
export interface DebugSummaryResponse {
  failures: {
    ts: string;
    run_id?: string;
    feature: string;
    stage: string;
    error_type: string;
    error: string;
    symbol?: string;
    elapsed_sec?: number | null;
    traceback?: string;
  }[];
  mcp_status: Record<string, "ok" | "down">;
  recent_runs: {
    id: string;
    workflow_name: string;
    status: string;
    started_at: string;
    completed_at?: string | null;
    elapsed_sec?: number | null;
  }[];
  discovery_jobs: {
    job_id: string;
    status: string;
    started_at: string;
    completed_at?: string | null;
  }[];
}

export interface AgentLogRun {
  id: string;
  workflow_name: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  elapsed_sec: number | null;
  stock_id: string | null;
  symbol: string | null;
  workflow_config: {
    task?: string;
    error?: string;
    symbol?: string;
    suggested_horizon?: string;
    horizon?: string;
  } | null;
  error: string | null;
  agent_count?: number;
  failed_count?: number;
  total_latency_ms?: number;
  total_cost_usd?: number;
  total_tokens_in?: number;
  total_tokens_out?: number;
  horizon?: string;
  timestamp?: string;
}

export interface AgentLogRunListResponse {
  runs: AgentLogRun[];
  total: number;
  page: number;
  total_pages: number;
  limit: number;
}

export interface AgentLogDetail {
  id: string;
  run_id: string | null;
  agent_name: string;
  agent_type?: string;
  status: string;
  error: string | null;
  latency_ms: number | null;
  model_used: string;
  signal?: string | null;
  confidence?: number | null;
  tokens_input?: number | null;
  tokens_output?: number | null;
  cost_usd?: number | null;
  retry_count?: number;
  created_at: string;
  has_prompt?: boolean;
  has_raw_response?: boolean;
  has_input?: boolean;
  has_output?: boolean;
  has_reasoning?: boolean;

  // Full drill-down payload attributes
  input?: Record<string, any> | null;
  output?: Record<string, any> | null;
  reasoning?: any | null;
  prompt_template?: string | null;
  raw_llm_response?: string | null;
}

export interface AgentLogRunDetailResponse {
  run: AgentLogRun;
  symbol: string | null;
  agents: AgentLogDetail[];
  recommendation?: any | null;
  discovery_count?: number | null;
}


export interface AgentStatItem {
  agent_name: string;
  agent_type: string;
  count: number;
  failures: number;
  failure_rate: number;
  avg_latency_ms: number;
  p50_latency_ms: number;
  p95_latency_ms: number;
  avg_cost_usd: number | null;
  total_tokens_in: number;
  total_tokens_out: number;
}

export interface AgentStatsResponse {
  window_hours: number;
  since: string;
  agents: AgentStatItem[];
}

// ── Arize AI Improve ──────────────────────────────────────────
export interface ImproveProposeResponse {
  status: string;
  message?: string;
  analysis?: string;
  candidate_prompt?: string;
  proposed_prompt?: string;
  rule?: string;
  failures_analyzed?: number;
}

export interface ImproveActionResponse {
  status: string;
  message?: string;
}
