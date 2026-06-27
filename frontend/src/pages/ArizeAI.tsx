import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { config } from "../config";
import { Spinner } from "../components/shared/Spinner";
import {
  ShieldCheck, Activity, AlertTriangle, CheckCircle2,
  Zap, Cpu, Coins, RefreshCw, ChevronDown, BarChart3,
  Layers, Eye, Hash, X, FileText, Gavel, Network, ExternalLink
} from "lucide-react";
import { apiService } from "../services/api";
import { generateArizePdf } from "../utils/generateArizePdf";

// Inline API call (avoids touching api.ts types)
async function fetchEvalSummary(hours: number) {
  const res = await fetch(`${config.API_BASE_URL}/api/arize/eval-summary?hours=${hours}`);
  if (!res.ok) throw new Error("Failed to fetch eval summary");
  return res.json();
}

// ── LLM-as-Judge experiment evals, READ over MCP from Phoenix Cloud ──────────
// The judges execute server-side (phoenix.evals); the experiment writes scores to
// Phoenix Cloud; this endpoint reads them back over MCP. (Backend: GET
// /api/evals/experiment → PhoenixMCP.get_latest_experiment_evals.)
interface EvalVerdict { label: string | null; score: number | null; explanation: string }
interface EvalRow {
  ticker: string; action: string; expected_action: string;
  trace_id?: string; latency_ms?: number; evals: Record<string, EvalVerdict>;
}
interface ExperimentEvals {
  experiment_id?: string; dataset_name?: string; evaluators: string[];
  rows: EvalRow[]; phoenix_base_url?: string; error?: string;
}

// Which evaluator names are LLM-as-judge (vs deterministic CODE / exact-match).
const LLM_JUDGES = new Set(["rationale_groundedness", "decision_correctness", "wait_refusal_quality"]);
const EVAL_PRETTY: Record<string, string> = {
  wait_discipline: "Wait Discipline",
  rationale_groundedness: "Rationale Groundedness",
  decision_correctness: "Decision Correctness",
  wait_refusal_quality: "Wait-Refusal Quality",
};

async function fetchExperimentEvals(force = false): Promise<ExperimentEvals> {
  const qs = force ? "?force=true" : "";
  const res = await fetch(`${config.API_BASE_URL}/api/evals/experiment${qs}`);
  if (!res.ok) throw new Error("Failed to fetch experiment evals");
  return res.json();
}

// A verdict is a "pass" when score === 1; N/A (not-applicable) rows are excluded
// from the pass-rate denominator so a metric isn't penalised on rows it skips.
function verdictKind(v?: EvalVerdict): "pass" | "fail" | "na" {
  if (!v) return "na";
  const l = (v.label || "").toLowerCase();
  if (l.includes("n/a") || l.includes("not_") || l.includes("no_rationale") || l === "na") return "na";
  if (v.score === 1) return "pass";
  if (v.score === 0) return "fail";
  return "na";
}

type ReportTab = "evaluations" | "pipeline_runs" | "hallucinations" | "safety_triggers" | null;

export function ArizeAI() {
  const [hours, setHours] = useState(72);
  const [selectedSpan, setSelectedSpan] = useState<string | null>(null);
  const queryClient = useQueryClient();

  // Detailed Report Modal state
  const [activeReport, setActiveReport] = useState<ReportTab>(null);

  const { data, isLoading, refetch } = useQuery({
    queryKey: ["arizeEvalSummary", hours],
    queryFn: () => fetchEvalSummary(hours),
    refetchInterval: 30000,
  });

  const { data: spanDetail, isLoading: isSpanLoading } = useQuery({
    queryKey: ["agentDetail", selectedSpan],
    queryFn: () => apiService.getAgentLogDetail(selectedSpan!),
    enabled: !!selectedSpan,
  });

  // LLM-as-Judge experiment evals. NOTE: each call spawns an npx phoenix-mcp
  // subprocess server-side, so we fetch once + manual refresh — NOT on an interval.
  const {
    data: expEvals, isLoading: isEvalsLoading, isFetching: isEvalsFetching,
  } = useQuery<ExperimentEvals>({
    queryKey: ["experimentEvals"],
    queryFn: () => fetchExperimentEvals(false),  // cached → instant page load
    staleTime: 5 * 60 * 1000,
    refetchOnWindowFocus: false,
  });

  // Refresh button forces a fresh MCP read (bypasses the server cache).
  const [isForcing, setIsForcing] = useState(false);
  const forceRefreshEvals = async () => {
    setIsForcing(true);
    try {
      const fresh = await fetchExperimentEvals(true);
      queryClient.setQueryData(["experimentEvals"], fresh);
    } finally {
      setIsForcing(false);
    }
  };

  // Groundedness derived from the real rationale_groundedness LLM judge (so the
  // hero cards agree with the Verdicts table instead of showing a misleading "0%").
  // Returns null when there's no judged data yet → rendered as "N/A".
  const groundednessStat = (() => {
    const rows = expEvals?.rows || [];
    let grounded = 0, judged = 0;
    for (const r of rows) {
      const k = verdictKind(r.evals?.["rationale_groundedness"]);
      if (k === "na") continue;
      judged += 1;
      if (k === "pass") grounded += 1;
    }
    if (!judged) return { groundedPct: null as number | null, hallucPct: null as number | null, judged: 0 };
    const groundedPct = Math.round((grounded / judged) * 100);
    return { groundedPct, hallucPct: 100 - groundedPct, judged };
  })();

  // Real per-evaluator pass rates computed from the experiment rows (replaces the
  // previously hardcoded mock "pass rate" bars).
  const evalPassRates = (() => {
    const rows = expEvals?.rows || [];
    const names = expEvals?.evaluators || [];
    return names.map((name) => {
      let pass = 0, total = 0;
      for (const r of rows) {
        const k = verdictKind(r.evals?.[name]);
        if (k === "na") continue;
        total += 1;
        if (k === "pass") pass += 1;
      }
      return {
        name,
        label: EVAL_PRETTY[name] || name,
        isLLM: LLM_JUDGES.has(name),
        pct: total ? Math.round((pass / total) * 100) : 0,
        pass, total,
      };
    });
  })();

  const hero = data?.hero_metrics || {};
  const agents = data?.agent_breakdown || [];
  const tokens = data?.token_economics || {};
  const spans = data?.recent_spans || [];
  const calibration = data?.confidence_calibration || {};
  const reportData = data?.detailed_report || {};


  return (
    <div className="space-y-6 animate-in fade-in duration-200 pb-8 relative">

      {/* ── Header ──────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 bg-white border border-border rounded-xl p-4 shadow-sm">
        <div className="flex items-center gap-2">
          <div className="p-2 bg-violet-50 rounded-lg text-violet-600 border border-violet-100">
            <ShieldCheck size={20} />
          </div>
          <div>
            <h2 className="text-base md:text-lg font-black text-primary tracking-tight">Arize AI Evaluation Hub</h2>
            <p className="text-xs text-muted font-medium">Observability, LLM-as-judge evaluation, and agent telemetry — powered by Arize Phoenix.</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button 
            onClick={() => setActiveReport("evaluations")}
            className="hidden md:flex items-center gap-1.5 px-3 py-1.5 bg-blue-50 text-blue-600 hover:bg-blue-100 border border-blue-200 rounded-lg text-xs font-bold transition-colors"
          >
            <Eye size={14} /> View Details
          </button>
          <button 
            onClick={() => generateArizePdf(hero, groundednessStat, agents, expEvals)}
            className="hidden md:flex items-center gap-1.5 px-3 py-1.5 bg-violet-600 text-white hover:bg-violet-700 rounded-lg text-xs font-bold transition-colors shadow-sm"
          >
            <FileText size={14} /> Download Report
          </button>
          <select value={hours} onChange={(e) => setHours(Number(e.target.value))} className="text-xs border border-border rounded-lg px-3 py-1.5 font-bold text-primary bg-white">
            <option value={24}>Last 24h</option>
            <option value={72}>Last 72h</option>
            <option value={168}>Last 7d</option>
          </select>
          <button onClick={() => refetch()} className="p-2 text-muted hover:text-accent rounded-lg border hover:bg-neutral-50 transition-colors">
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="py-20 text-center"><Spinner size="lg" /><p className="text-xs text-muted mt-2">Loading evaluation metrics...</p></div>
      ) : (
        <>
          {/* ── Hero Metric Cards ───────────────────────────── */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { label: "Total Evaluations", value: hero.total_evaluations || 0, icon: Layers, color: "blue", sub: `${hero.total_runs || 0} pipeline runs`, reportId: "evaluations" as ReportTab },
              { label: "Hallucination Rate", value: groundednessStat.hallucPct != null ? `${groundednessStat.hallucPct}%` : "N/A", icon: AlertTriangle, color: "amber", sub: groundednessStat.judged ? `${groundednessStat.judged} rationales judged (LLM)` : "no judged evals yet", reportId: "hallucinations" as ReportTab },
              { label: "Groundedness Score", value: groundednessStat.groundedPct != null ? `${groundednessStat.groundedPct}%` : "N/A", icon: CheckCircle2, color: "emerald", sub: groundednessStat.judged ? `via rationale_groundedness judge` : "run experiment to populate", reportId: "pipeline_runs" as ReportTab },
              { label: "Safety Triggers", value: hero.safety_triggers_prevented || 0, icon: ShieldCheck, color: "violet", sub: `${hero.total_retries || 0} auto-retries`, reportId: "safety_triggers" as ReportTab },
            ].map((m) => {
              const Icon = m.icon;
              return (
                <div 
                  key={m.label} 
                  onClick={() => setActiveReport(m.reportId)}
                  className={`bg-white rounded-xl border border-border p-4 shadow-sm hover:shadow-md hover:border-${m.color}-300 transition-all group relative overflow-hidden cursor-pointer`}
                >
                  <div className={`absolute top-0 right-0 w-20 h-20 bg-${m.color}-500/10 rounded-full blur-2xl -mr-8 -mt-8 transition-transform group-hover:scale-150`} />
                  <div className="flex items-center justify-between mb-3">
                    <div className={`p-1.5 bg-${m.color}-50 text-${m.color}-600 rounded-lg`}><Icon size={16} /></div>
                    <FileText size={14} className="text-muted opacity-0 group-hover:opacity-100 transition-opacity" />
                  </div>
                  <h3 className="text-2xl font-black text-primary">{m.value}</h3>
                  <p className="text-[10px] font-bold text-muted uppercase tracking-wider mt-0.5 group-hover:text-primary transition-colors">{m.label}</p>
                  <p className="text-[10px] text-muted mt-1">{m.sub}</p>
                </div>
              );
            })}
          </div>

          {/* ── LLM-as-Judge Verdicts (read from Phoenix via MCP) ───────── */}
          <div className="bg-white rounded-xl border border-border shadow-sm overflow-hidden">
            <div className="p-4 border-b border-border bg-gradient-to-r from-violet-50/60 to-transparent flex flex-col sm:flex-row sm:items-center gap-3">
              <div className="flex items-center gap-2">
                <Gavel size={15} className="text-violet-600" />
                <h3 className="text-xs font-black text-primary uppercase tracking-wider">LLM-as-Judge Verdicts</h3>
                <span className="flex items-center gap-1 text-[9px] font-bold text-violet-600 bg-violet-50 border border-violet-200 px-1.5 py-0.5 rounded">
                  <Network size={10} /> read via MCP
                </span>
              </div>
              <div className="sm:ml-auto flex items-center gap-3">
                {expEvals?.experiment_id && (
                  <span className="text-[10px] font-mono text-muted hidden md:inline">exp · {expEvals.experiment_id.slice(0, 12)}…</span>
                )}
                {expEvals?.phoenix_base_url && (
                  <a
                    href={`${expEvals.phoenix_base_url}/datasets`}
                    target="_blank" rel="noreferrer"
                    className="flex items-center gap-1 text-[10px] font-bold text-violet-600 hover:underline"
                  >
                    Phoenix Cloud <ExternalLink size={10} />
                  </a>
                )}
                <button
                  onClick={forceRefreshEvals}
                  disabled={isForcing || isEvalsFetching}
                  title="Re-read the latest experiment from Phoenix over MCP (~6s)"
                  className="flex items-center gap-1 px-2 py-1 text-[10px] font-bold text-muted hover:text-violet-600 rounded border hover:bg-violet-50 transition-colors disabled:opacity-50"
                >
                  <RefreshCw size={11} className={(isForcing || isEvalsFetching) ? "animate-spin" : ""} /> {isForcing ? "Reading…" : "Refresh"}
                </button>
              </div>
            </div>

            <div className="px-4 py-2.5 bg-violet-50/30 border-b border-border text-[10.5px] text-muted leading-relaxed">
              <span className="font-bold text-violet-700">Why this matters:</span> the <span className="font-bold">Wait Discipline</span> column is a deterministic
              exact-match (action == expected). The <span className="font-bold text-violet-700">LLM Judge</span> columns (Gemini via Arize Phoenix Evals)
              read each agent's <em>rationale</em> against the <em>evidence it saw</em> — catching ungrounded reasoning that exact-match cannot.
            </div>

            {isEvalsLoading ? (
              <div className="py-12 text-center"><Spinner size="md" /><p className="text-[11px] text-muted mt-2">Reading evaluator results from Phoenix over MCP…</p></div>
            ) : expEvals?.error && (!expEvals.rows || expEvals.rows.length === 0) ? (
              <div className="py-10 px-4 text-center">
                <AlertTriangle size={20} className="text-amber-500 mx-auto mb-2" />
                <p className="text-xs font-bold text-primary">{expEvals.error}</p>
                <p className="text-[10px] text-muted mt-1">Run <code className="font-mono bg-neutral-100 px-1 rounded">eval/run_experiment.py</code>, then refresh.</p>
              </div>
            ) : !expEvals?.rows?.length ? (
              <div className="py-10 text-center text-muted text-xs font-medium">No experiment results yet.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="border-b border-border bg-neutral-50/40 text-[10px] uppercase tracking-wider text-muted font-black">
                      <th className="py-2.5 px-4">Stock</th>
                      <th className="py-2.5 px-3 text-center">Action</th>
                      <th className="py-2.5 px-3 text-center">Expected</th>
                      {[...(expEvals.evaluators || [])]
                        .sort((a, b) => (LLM_JUDGES.has(a) ? 1 : 0) - (LLM_JUDGES.has(b) ? 1 : 0))
                        .map((name) => (
                          <th key={name} className="py-2.5 px-3 min-w-[200px]">
                            <span className="flex items-center gap-1.5">
                              {EVAL_PRETTY[name] || name}
                              <span className={`text-[8px] font-black px-1 py-px rounded ${LLM_JUDGES.has(name) ? "bg-violet-100 text-violet-700" : "bg-sky-100 text-sky-700"}`}>
                                {LLM_JUDGES.has(name) ? "LLM" : "EXACT"}
                              </span>
                            </span>
                          </th>
                        ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-neutral-100">
                    {expEvals.rows.map((row) => {
                      const sorted = [...(expEvals.evaluators || [])].sort((a, b) => (LLM_JUDGES.has(a) ? 1 : 0) - (LLM_JUDGES.has(b) ? 1 : 0));
                      return (
                        <tr key={row.ticker} className="hover:bg-neutral-50/50 align-top transition-colors">
                          <td className="py-3 px-4 font-mono font-bold text-primary whitespace-nowrap">{row.ticker}</td>
                          <td className="py-3 px-3 text-center"><span className="px-1.5 py-0.5 rounded text-[10px] font-black bg-neutral-100 text-neutral-700 font-mono">{row.action}</span></td>
                          <td className="py-3 px-3 text-center"><span className="px-1.5 py-0.5 rounded text-[10px] font-black bg-neutral-100 text-neutral-500 font-mono">{row.expected_action}</span></td>
                          {sorted.map((name) => {
                            const v = row.evals?.[name];
                            const kind = verdictKind(v);
                            const chip = kind === "pass" ? "bg-emerald-50 text-emerald-700 border-emerald-100"
                              : kind === "fail" ? "bg-red-50 text-red-700 border-red-100"
                              : "bg-neutral-100 text-neutral-500 border-neutral-200";
                            return (
                              <td key={name} className="py-3 px-3">
                                <span className={`inline-block px-1.5 py-0.5 rounded border text-[10px] font-black font-mono ${chip}`}>
                                  {v?.label || "—"}{v?.score != null ? ` · ${v.score}` : ""}
                                </span>
                                {v?.explanation && (
                                  <p className="text-[10px] text-muted mt-1.5 leading-snug line-clamp-3">{v.explanation}</p>
                                )}
                              </td>
                            );
                          })}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* ── Eval Categories & Latency Row ─────────── */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            <div className="md:col-span-2 bg-white rounded-xl border border-border p-4 shadow-sm">
               <div className="flex items-center gap-2 mb-3">
                 <Activity size={14} className="text-accent" />
                 <span className="text-xs font-black text-primary uppercase tracking-wider">Evaluator Pass Rate</span>
                 <span className="ml-auto text-[9px] font-bold text-muted">live · Phoenix experiment</span>
               </div>
               <div className="space-y-3 mt-4">
                  {evalPassRates.length === 0 && (
                    <p className="text-[11px] text-muted py-4">
                      No experiment evals yet — run <code className="font-mono bg-neutral-100 px-1 rounded">eval/run_experiment.py</code> to populate.
                    </p>
                  )}
                  {evalPassRates.map((m) => (
                    <div key={m.name}>
                      <div className="flex justify-between items-center text-[10px] font-bold text-primary mb-1">
                        <span className="flex items-center gap-1.5">
                          {m.label}
                          <span className={`text-[8px] font-black px-1 py-px rounded ${m.isLLM ? "bg-violet-100 text-violet-700" : "bg-sky-100 text-sky-700"}`}>
                            {m.isLLM ? "LLM JUDGE" : "EXACT"}
                          </span>
                        </span>
                        <span>{m.pct}% <span className="text-muted font-medium">({m.pass}/{m.total})</span></span>
                      </div>
                      <div className="w-full bg-neutral-100 rounded-full h-1.5 overflow-hidden">
                        <div className={`h-full rounded-full ${m.isLLM ? "bg-violet-500" : "bg-sky-500"}`} style={{ width: `${m.pct}%` }} />
                      </div>
                    </div>
                  ))}
               </div>
            </div>

            <div className="bg-white rounded-xl border border-border p-4 shadow-sm">
              <div className="flex items-center gap-2 mb-3"><Hash size={14} className="text-accent" /><span className="text-xs font-black text-primary uppercase tracking-wider">Token Usage</span></div>
              <div className="flex items-baseline gap-2">
                <span className="text-2xl font-black text-primary">{(tokens.total || 0).toLocaleString()}</span>
                <span className="text-xs text-muted font-bold">tokens</span>
              </div>
              <div className="flex gap-3 mt-1 text-[10px] text-muted">
                <span>In: {(tokens.total_input || 0).toLocaleString()}</span>
                <span>Out: {(tokens.total_output || 0).toLocaleString()}</span>
              </div>
              {!tokens.total && (
                <p className="text-[9px] text-amber-600 mt-1.5 leading-snug">Token capture is now enabled — run a new analysis to populate (older runs predate it).</p>
              )}
            </div>

            <div className="bg-white rounded-xl border border-border p-4 shadow-sm">
              <div className="flex items-center gap-2 mb-3"><Coins size={14} className="text-accent" /><span className="text-xs font-black text-primary uppercase tracking-wider">Cost</span></div>
              <div className="flex items-baseline gap-2">
                <span className="text-2xl font-black text-primary">${tokens.cost_usd || "0.00"}</span>
                <span className="text-xs text-muted font-bold">USD</span>
              </div>
              <p className="text-[10px] text-muted mt-1">~{Math.round(tokens.avg_tokens_per_eval || 0)} tokens/eval</p>
            </div>
          </div>

          {/* ── Agent Performance Breakdown ──────────────────── */}
          <div className="bg-white rounded-xl border border-border shadow-sm overflow-hidden">
            <div className="p-4 border-b border-border bg-neutral-50/50 flex items-center justify-between">
              <div className="flex items-center gap-2"><Cpu size={14} className="text-accent" /><h3 className="text-xs font-black text-primary uppercase tracking-wider">Agent Performance Breakdown</h3></div>
              <span className="text-[10px] text-muted font-bold">{agents.length} agents tracked</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-border bg-neutral-50/30 text-[10px] uppercase tracking-wider text-muted font-black">
                    <th className="py-2.5 px-4">Agent</th>
                    <th className="py-2.5 px-3 text-center">Calls</th>
                    <th className="py-2.5 px-3 text-center">Tools</th>
                    <th className="py-2.5 px-3 text-center">Success</th>
                    <th className="py-2.5 px-3 text-center">Retries</th>
                    <th className="py-2.5 px-3 text-right">p50 / p95</th>
                    <th className="py-2.5 px-3 text-right">Tokens</th>
                    <th className="py-2.5 px-3 text-right">Confidence</th>
                    <th className="py-2.5 px-3">Model</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-neutral-100">
                  {agents.map((a: any) => (
                    <tr key={a.agent_name + a.model_used} className="hover:bg-neutral-50/60 transition-colors">
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-2">
                          <div className={`w-2 h-2 rounded-full ${a.failures > 0 ? "bg-amber-400" : "bg-emerald-500"}`} />
                          <span className="font-bold text-primary">{a.agent_name}</span>
                        </div>
                      </td>
                      <td className="py-3 px-3 text-center font-mono font-bold text-primary">{a.invocations}</td>
                      <td className="py-3 px-3 text-center font-mono font-bold text-blue-600 bg-blue-50/30 rounded">{a.tool_calls || 0}</td>
                      <td className="py-3 px-3 text-center">
                        <span className={`font-bold ${a.success_rate >= 95 ? "text-emerald-600" : a.success_rate >= 80 ? "text-amber-600" : "text-red-600"}`}>{a.success_rate}%</span>
                      </td>
                      <td className="py-3 px-3 text-center font-mono text-muted">{a.retries}</td>
                      <td className="py-3 px-3 text-right font-mono">
                        <span className="text-primary font-bold">{a.p50_latency_ms ? Math.round(a.p50_latency_ms) : "—"}</span>
                        <span className="text-muted"> / </span>
                        <span className="text-muted">{a.p95_latency_ms ? Math.round(a.p95_latency_ms) : "—"}ms</span>
                      </td>
                      <td className="py-3 px-3 text-right font-mono text-primary">{a.total_tokens.toLocaleString()}</td>
                      <td className="py-3 px-3 text-right">
                        {a.avg_confidence != null ? (
                          <div className="flex items-center justify-end gap-1.5">
                            <div className="w-16 h-1.5 bg-neutral-100 rounded-full overflow-hidden">
                              <div className="h-full bg-accent rounded-full" style={{ width: `${Math.round(a.avg_confidence * 100)}%` }} />
                            </div>
                            <span className="font-mono text-[10px] font-bold text-primary">{Math.round(a.avg_confidence * 100)}%</span>
                          </div>
                        ) : <span className="text-muted">—</span>}
                      </td>
                      <td className="py-3 px-3 text-[10px] font-mono text-muted">{a.model_used}</td>
                    </tr>
                  ))}
                  {agents.length === 0 && (
                    <tr><td colSpan={9} className="py-8 text-center text-muted font-medium">No agent data in this window.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* ── Span Trace Timeline ──────────────────────────── */}
          <div className="bg-white rounded-xl border border-border shadow-sm overflow-hidden">
            <div className="p-4 border-b border-border bg-neutral-50/50 flex items-center gap-2">
              <Eye size={14} className="text-accent" />
              <h3 className="text-xs font-black text-primary uppercase tracking-wider">Recent Execution Spans <span className="text-[10px] normal-case font-medium text-muted">(Click to inspect Trace)</span></h3>
              <span className="ml-auto text-[10px] text-muted font-bold">{spans.length} spans</span>
            </div>
            <div className="divide-y divide-neutral-100 max-h-72 overflow-y-auto">
              {spans.slice(0, 20).map((span: any) => (
                <div 
                  key={span.id} 
                  onClick={() => setSelectedSpan(span.id)}
                  className="flex items-center gap-3 px-4 py-2.5 hover:bg-neutral-50/60 transition-colors text-xs cursor-pointer group"
                >
                  {span.status === "SUCCESS" ? <CheckCircle2 size={13} className="text-emerald-500 shrink-0" /> : <AlertTriangle size={13} className="text-red-500 shrink-0" />}
                  <span className="font-bold text-primary w-28 truncate group-hover:text-blue-600 transition-colors">{span.agent_name}</span>
                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-black ${
                    span.signal === "BUY" ? "bg-emerald-50 text-emerald-700" :
                    span.signal === "SELL" ? "bg-red-50 text-red-700" :
                    "bg-neutral-100 text-neutral-600"
                  }`}>{span.signal || "—"}</span>
                  <span className="font-mono text-muted flex items-center gap-1"><Zap size={10} />{span.latency_ms ? `${Math.round(span.latency_ms)}ms` : "—"}</span>
                  <span className="font-mono text-muted text-[10px]">{(span.tokens_in + span.tokens_out).toLocaleString()} tok</span>
                  <span className="text-[10px] font-mono text-muted ml-auto">{span.created_at ? new Date(span.created_at.includes("Z") || span.created_at.includes("+") ? span.created_at : span.created_at + "Z").toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }) : ""}</span>
                  <ChevronDown size={12} className="text-muted opacity-0 group-hover:opacity-100 -rotate-90 transition-all" />
                </div>
              ))}
              {spans.length === 0 && <div className="py-8 text-center text-muted text-sm font-medium">No spans recorded yet.</div>}
            </div>
          </div>

          {/* ── Confidence Distribution (real, from recommendation confidences) ── */}
          {Object.values(calibration).some((v: any) => v > 0) && (
            <div className="bg-white rounded-xl border border-border p-4 shadow-sm">
              <div className="flex items-center gap-2 mb-4">
                <BarChart3 size={14} className="text-accent" />
                <h3 className="text-xs font-black text-primary uppercase tracking-wider">Confidence Distribution</h3>
                <span className="ml-auto text-[10px] text-muted font-medium">{Object.values(calibration).reduce((a: number, b: any) => a + Number(b), 0)} decisions</span>
              </div>
              <div className="flex items-end gap-3 h-28">
                {Object.entries(calibration).map(([bucket, count]: [string, any]) => {
                  const max = Math.max(...Object.values(calibration).map(Number), 1);
                  const h = (count / max) * 100;
                  return (
                    <div key={bucket} className="flex-1 flex flex-col items-center gap-1">
                      <span className="text-[10px] font-bold text-primary">{count}</span>
                      <div className="w-full bg-neutral-100 rounded-t-md overflow-hidden" style={{ height: "80px" }}>
                        <div className="w-full bg-accent/70 rounded-t-md transition-all duration-500" style={{ height: `${h}%`, marginTop: `${100 - h}%` }} />
                      </div>
                      <span className="text-[9px] font-bold text-muted">{bucket}%</span>
                    </div>
                  );
                })}
              </div>
              <p className="text-[10px] text-muted mt-2">Distribution of final decision confidence across all recommendations in the window.</p>
            </div>
          )}
        </>
      )}

      {/* ── Trace Modal Overlay ───────────────────────────── */}
      {selectedSpan && (
         <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-navy/20 backdrop-blur-sm animate-in fade-in duration-200" onClick={() => setSelectedSpan(null)}>
           <div className="bg-white w-full max-w-4xl rounded-xl shadow-2xl overflow-hidden border border-border flex flex-col max-h-[85vh]" onClick={e => e.stopPropagation()}>
             <div className="px-5 py-4 border-b border-border flex items-center justify-between bg-neutral-50/80">
               <div className="flex items-center gap-3">
                 <div className="p-1.5 bg-blue-100 text-blue-600 rounded"><Eye size={16} /></div>
                 <div>
                   <h3 className="text-sm font-black text-primary">Trace Inspection</h3>
                   <p className="text-[10px] font-mono text-muted">{selectedSpan}</p>
                 </div>
               </div>
               <button onClick={() => setSelectedSpan(null)} className="p-1.5 text-muted hover:bg-neutral-200 rounded transition-colors"><X size={16} /></button>
             </div>
             
             <div className="flex-1 overflow-y-auto p-5 space-y-6">
               {isSpanLoading ? (
                 <div className="py-20 text-center"><Spinner size="md" /><p className="text-xs mt-2 text-muted">Loading trace details...</p></div>
               ) : spanDetail ? (
                 <>
                   <div className="flex flex-wrap gap-4 text-xs font-bold text-primary">
                     <div className="bg-neutral-50 px-3 py-1.5 rounded-md border">Agent: <span className="text-blue-600 font-mono">{spanDetail.agent_name}</span></div>
                     <div className="bg-neutral-50 px-3 py-1.5 rounded-md border">Model: <span className="text-blue-600 font-mono">{spanDetail.model_used}</span></div>
                     <div className="bg-neutral-50 px-3 py-1.5 rounded-md border">Latency: <span className="text-blue-600 font-mono">{spanDetail.latency_ms}ms</span></div>
                   </div>
                   
                   <div className="grid grid-cols-2 gap-4">
                     <div>
                       <h4 className="text-xs font-black uppercase tracking-wider text-muted mb-2">Input Context</h4>
                       <pre className="bg-[#0d1117] text-emerald-400 p-3 rounded-lg text-[10px] font-mono overflow-auto border border-slate-800">
                         {JSON.stringify(spanDetail.input, null, 2)}
                       </pre>
                     </div>
                     <div>
                       <h4 className="text-xs font-black uppercase tracking-wider text-muted mb-2">Structured Output</h4>
                       <pre className="bg-[#0d1117] text-blue-300 p-3 rounded-lg text-[10px] font-mono overflow-auto border border-slate-800">
                         {JSON.stringify(spanDetail.output, null, 2)}
                       </pre>
                     </div>
                   </div>

                   <div className="space-y-4">
                     <div>
                       <h4 className="text-xs font-black uppercase tracking-wider text-muted mb-2">Prompt Template Used</h4>
                       <div className="bg-neutral-50 p-4 rounded-lg border border-neutral-200 text-xs font-mono text-neutral-600 whitespace-pre-wrap max-h-40 overflow-y-auto">
                         {spanDetail.prompt_template || "No prompt template recorded."}
                       </div>
                     </div>
                     <div>
                       <h4 className="text-xs font-black uppercase tracking-wider text-muted mb-2">Raw LLM Response</h4>
                       <div className="bg-[#0d1117] p-4 rounded-lg border border-slate-800 text-[11px] font-mono text-slate-300 whitespace-pre-wrap max-h-60 overflow-y-auto">
                         {spanDetail.raw_llm_response || "No raw response recorded."}
                       </div>
                     </div>
                   </div>
                 </>
               ) : (
                 <div className="py-20 text-center text-red-500 text-xs font-bold">Failed to load trace.</div>
               )}
             </div>
           </div>
         </div>
      )}

      {/* ── Detailed Report Modal Overlay ───────────────────── */}
      {activeReport && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-navy/20 backdrop-blur-sm animate-in fade-in duration-200" onClick={() => setActiveReport(null)}>
          <div className="bg-white w-full max-w-5xl rounded-xl shadow-2xl overflow-hidden border border-border flex flex-col max-h-[90vh]" onClick={e => e.stopPropagation()}>
            <div className="relative px-5 py-4 border-b border-border flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-neutral-50/80 pr-12">
              <div className="flex items-center gap-3">
                <div className="p-1.5 bg-indigo-100 text-indigo-600 rounded"><FileText size={18} /></div>
                <div>
                  <h3 className="text-sm font-black text-primary uppercase tracking-wider">Detailed Evaluation Report</h3>
                  <p className="text-[10px] font-medium text-muted">Raw data breakdown for top-level KPIs</p>
                </div>
              </div>
              <div className="flex gap-2 bg-white p-1 rounded-lg border border-border">
                {(["evaluations", "pipeline_runs", "hallucinations", "safety_triggers"] as ReportTab[]).map(tab => (
                  <button 
                    key={tab} 
                    onClick={() => setActiveReport(tab)}
                    className={`px-3 py-1.5 rounded-md text-[10px] font-bold uppercase tracking-wider transition-colors ${activeReport === tab ? 'bg-navy text-white shadow-sm' : 'text-muted hover:bg-neutral-100'}`}
                  >
                    {tab?.replace("_", " ")}
                  </button>
                ))}
              </div>
              <button onClick={() => setActiveReport(null)} className="absolute top-4 right-4 p-1.5 text-muted hover:bg-neutral-200 rounded transition-colors"><X size={16} /></button>
            </div>
            
            <div className="flex-1 overflow-y-auto p-5 bg-neutral-50/30">
              {activeReport === "evaluations" && (
                <div className="space-y-3">
                  <h4 className="text-xs font-black text-primary mb-4 flex items-center gap-2"><Layers size={14} className="text-blue-500"/> Agent Evaluations ({reportData.evaluations?.length || 0})</h4>
                  <div className="bg-white border border-border rounded-lg overflow-hidden">
                    <table className="w-full text-left text-xs border-collapse">
                      <thead className="bg-neutral-50/80 text-[10px] uppercase tracking-wider text-muted font-black border-b border-border">
                        <tr><th className="py-2 px-4">Trace ID</th><th className="py-2 px-4">Agent</th><th className="py-2 px-4">Signal</th><th className="py-2 px-4">Latency</th><th className="py-2 px-4">Timestamp</th></tr>
                      </thead>
                      <tbody className="divide-y divide-neutral-100">
                        {reportData.evaluations?.map((ev: any) => (
                          <tr key={ev.id} className="hover:bg-neutral-50 transition-colors">
                            <td className="py-2.5 px-4 font-mono text-[10px] text-muted">{ev.id}</td>
                            <td className="py-2.5 px-4 font-bold text-primary">{ev.agent_name}</td>
                            <td className="py-2.5 px-4 font-bold text-emerald-600">{ev.signal}</td>
                            <td className="py-2.5 px-4 font-mono text-muted">{ev.latency_ms}ms</td>
                            <td className="py-2.5 px-4 text-[10px] text-muted">{new Date(ev.created_at.includes("Z") || ev.created_at.includes("+") ? ev.created_at : ev.created_at + "Z").toLocaleString("en-IN")}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
              
              {activeReport === "pipeline_runs" && (
                <div className="space-y-3">
                  <h4 className="text-xs font-black text-primary mb-4 flex items-center gap-2"><Cpu size={14} className="text-emerald-500"/> Pipeline Runs ({reportData.pipeline_runs?.length || 0})</h4>
                  <div className="bg-white border border-border rounded-lg overflow-hidden">
                    <table className="w-full text-left text-xs border-collapse">
                      <thead className="bg-neutral-50/80 text-[10px] uppercase tracking-wider text-muted font-black border-b border-border">
                        <tr><th className="py-2 px-4">Run ID</th><th className="py-2 px-4">Workflow</th><th className="py-2 px-4">Status</th><th className="py-2 px-4">Started At</th></tr>
                      </thead>
                      <tbody className="divide-y divide-neutral-100">
                        {reportData.pipeline_runs?.map((run: any) => (
                          <tr key={run.id} className="hover:bg-neutral-50 transition-colors">
                            <td className="py-2.5 px-4 font-mono text-[10px] text-muted">{run.id}</td>
                            <td className="py-2.5 px-4 font-bold text-primary">{run.workflow_name}</td>
                            <td className="py-2.5 px-4 font-bold text-emerald-600">{run.status}</td>
                            <td className="py-2.5 px-4 text-[10px] text-muted">{new Date(run.started_at.includes("Z") || run.started_at.includes("+") ? run.started_at : run.started_at + "Z").toLocaleString("en-IN")}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {activeReport === "hallucinations" && (
                <div className="space-y-3">
                  <h4 className="text-xs font-black text-primary mb-4 flex items-center gap-2"><AlertTriangle size={14} className="text-amber-500"/> Hallucinations & Conflicts ({reportData.hallucinations?.length || 0})</h4>
                  <div className="grid gap-3">
                    {reportData.hallucinations?.map((h: any) => (
                      <div key={h.id} className="bg-white p-3 rounded-lg border border-amber-200 shadow-sm flex flex-col gap-2">
                         <div className="flex items-center justify-between">
                           <span className="font-mono font-bold text-primary text-xs">{h.symbol}</span>
                           <span className="text-[10px] font-black uppercase text-amber-600 bg-amber-50 px-2 py-0.5 rounded">Conflict</span>
                         </div>
                         <div className="text-[11px] text-muted"><span className="font-bold text-primary">Signal:</span> {h.final_signal}</div>
                         <div className="text-[11px] text-muted"><span className="font-bold text-primary">Bear Case Issue:</span> {h.debate_bear_case}</div>
                         {h.validator_issues?.length > 0 && (
                           <div className="text-[11px] text-red-600 font-medium bg-red-50 p-1.5 rounded mt-1">Validator: {h.validator_issues.join(", ")}</div>
                         )}
                      </div>
                    ))}
                    {reportData.hallucinations?.length === 0 && <p className="text-xs text-muted">No hallucinations detected.</p>}
                  </div>
                </div>
              )}

              {activeReport === "safety_triggers" && (
                <div className="space-y-3">
                  <h4 className="text-xs font-black text-primary mb-4 flex items-center gap-2"><ShieldCheck size={14} className="text-violet-500"/> Safety Triggers ({reportData.safety_triggers?.length || 0})</h4>
                  <div className="grid gap-3">
                    {reportData.safety_triggers?.map((s: any) => (
                      <div key={s.id} className="bg-white p-3 rounded-lg border border-violet-200 shadow-sm flex flex-col gap-2">
                         <div className="flex items-center justify-between">
                           <span className="font-mono font-bold text-primary text-xs">{s.symbol}</span>
                           <span className="text-[10px] font-black uppercase text-violet-600 bg-violet-50 px-2 py-0.5 rounded">Triggered</span>
                         </div>
                         <div className="text-[11px] text-muted"><span className="font-bold text-primary">Confidence:</span> {s.final_confidence}</div>
                         {s.validator_issues?.length > 0 && (
                           <div className="text-[11px] text-red-600 font-medium bg-red-50 p-1.5 rounded mt-1">Issues: {s.validator_issues.join(", ")}</div>
                         )}
                      </div>
                    ))}
                    {reportData.safety_triggers?.length === 0 && <p className="text-xs text-muted">No safety triggers activated.</p>}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
