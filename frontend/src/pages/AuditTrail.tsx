import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { apiService } from "../services/api";
import type { AnalyzeResponse } from "../types";
import {
  Database, PlayCircle, Cpu, MessageSquare, ShieldCheck, ShieldX,
  CheckCircle2, XCircle, AlertTriangle, ArrowLeft, GitBranch, ChevronRight,
} from "lucide-react";
import { Spinner } from "../components/shared/Spinner";
import { SignalBadge } from "../components/shared/SignalBadge";

function inr(n: number) {
  return "₹" + n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatTime(iso: string) {
  const s = iso.includes("Z") || iso.includes("+") ? iso : `${iso}Z`;
  return new Date(s).toLocaleString("en-IN", {
    day: "2-digit", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit", hour12: true,
  });
}

function signalColor(signal: string) {
  switch (signal?.toUpperCase()) {
    case "BUY":  return "#16A34A";
    case "SELL": return "#DC2626";
    case "WAIT": return "#B85A10";
    default:     return "#5A6E85";
  }
}

function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-neutral-100 last:border-0">
      <span className="text-xs text-muted font-medium">{label}</span>
      <span className="text-xs font-mono font-bold text-primary">{value}</span>
    </div>
  );
}

function AuroraBadge() {
  return (
    <div className="inline-flex items-center gap-2 rounded-full border border-border bg-white px-3 py-1.5 shadow-sm">
      <Database size={13} className="text-muted" />
      <span className="text-xs font-semibold text-primary">Amazon Aurora PostgreSQL</span>
      <span className="relative flex h-2 w-2">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-signal-buy opacity-75" />
        <span className="relative inline-flex h-2 w-2 rounded-full bg-signal-buy" />
      </span>
    </div>
  );
}

function TimelineStep({
  icon, title, subLabel, accentColor, children, isLast = false,
}: {
  icon: React.ReactNode;
  title: string;
  subLabel?: string;
  accentColor: string;
  children: React.ReactNode;
  isLast?: boolean;
}) {
  return (
    <div className="relative pl-12">
      {!isLast && (
        <span className="absolute left-[19px] top-10 bottom-[-24px] w-px bg-border" />
      )}
      <span className="absolute left-0 top-0 flex h-10 w-10 items-center justify-center rounded-full bg-white border border-border shadow-sm">
        {icon}
      </span>
      <div
        className="rounded-xl border border-border bg-white p-4"
        style={{ borderLeft: `3px solid ${accentColor}` }}
      >
        <h3 className="text-sm font-black text-primary">{title}</h3>
        {subLabel && <p className="mt-0.5 text-xs text-muted">{subLabel}</p>}
        <div className="mt-3">{children}</div>
      </div>
    </div>
  );
}

function AgentCard({ name, signal, confidence }: { name: string; signal: string; confidence?: number | null }) {
  const color = signalColor(signal);
  const conf = confidence != null ? (confidence <= 1 ? Math.round(confidence * 100) : Math.round(confidence)) : null;
  return (
    <div className="rounded-lg border border-border bg-white p-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-black text-primary tracking-wide">{name}</span>
        <span
          className="rounded-full px-2 py-0.5 text-[10px] font-black"
          style={{ backgroundColor: `${color}1A`, color }}
        >
          {signal?.toUpperCase()}
        </span>
      </div>
      {conf != null && (
        <div className="mt-2">
          <div className="flex items-center justify-between mb-1">
            <span className="font-mono text-sm font-black text-primary">{conf}%</span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-neutral-100">
            <div className="h-full rounded-full" style={{ width: `${conf}%`, backgroundColor: color }} />
          </div>
        </div>
      )}
    </div>
  );
}

export function AuditTrail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<AnalyzeResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  // Index mode state (when no id is provided)
  const [recentRecs, setRecentRecs] = useState<AnalyzeResponse[]>([]);
  const [indexLoading, setIndexLoading] = useState(false);

  useEffect(() => {
    if (!id) {
      // No ID — load recent recommendations for the index view
      setIndexLoading(true);
      setLoading(false);
      apiService.getHistory({ limit: 25, page: 1 })
        .then((res) => setRecentRecs(res.recommendations || []))
        .catch(() => setRecentRecs([]))
        .finally(() => setIndexLoading(false));
      return;
    }
    setLoading(true);
    apiService.getHistoryDetail(id)
      .then(setData)
      .catch(() => setNotFound(true))
      .finally(() => setLoading(false));
  }, [id]);

  // ── INDEX MODE (no ID) ──────────────────────────────────────
  if (!id) {
    return (
      <div className="space-y-5 animate-in fade-in duration-200">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 bg-white border border-border rounded-xl p-4 shadow-sm">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-neutral-100 rounded-lg border border-border">
              <GitBranch size={20} className="text-accent" />
            </div>
            <div>
              <h1 className="text-lg font-black text-primary tracking-tight">Decision Audit Trails</h1>
              <p className="text-xs text-muted font-medium">Select a recommendation to reconstruct its full decision audit trail from Amazon Aurora PostgreSQL</p>
            </div>
          </div>
          <AuroraBadge />
        </div>

        {/* Index table */}
        <div className="bg-white border border-border rounded-xl shadow-sm overflow-hidden">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-border bg-neutral-50 font-bold text-primary">
                <th className="p-3">Asset</th>
                <th className="p-3">Verdict</th>
                <th className="p-3 text-center">Horizon</th>
                <th className="p-3 text-right">Target</th>
                <th className="p-3 text-right">Date</th>
                <th className="p-3 text-center">Trail</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-100">
              {indexLoading ? (
                <tr>
                  <td colSpan={6} className="p-12 text-center">
                    <Spinner size="md" className="mb-3 mx-auto" />
                    <p className="text-[10px] font-bold text-primary animate-pulse tracking-wider uppercase">
                      Loading recommendations from Aurora PostgreSQL…
                    </p>
                  </td>
                </tr>
              ) : recentRecs.length === 0 ? (
                <tr>
                  <td colSpan={6} className="p-12 text-center">
                    <div className="flex flex-col items-center gap-3">
                      <div className="p-4 bg-accent-soft rounded-full">
                        <Database size={28} className="text-accent" />
                      </div>
                      <p className="text-sm font-bold text-primary">No recommendations yet</p>
                      <p className="text-xs text-muted font-medium max-w-xs text-center">
                        Run an analysis from the Dashboard to generate recommendations, then return here to view their decision audit trails.
                      </p>
                    </div>
                  </td>
                </tr>
              ) : (
                recentRecs.map((rec, idx) => {
                  const rowId = rec.recommendation_id || rec.id || `row-${idx}`;
                  const dateStr = rec.created_at || rec.timestamp;
                  const formattedDate = dateStr
                    ? new Date(dateStr.includes("Z") || dateStr.includes("+") ? dateStr : `${dateStr}Z`).toLocaleDateString("en-IN", {
                        day: "2-digit", month: "short", year: "numeric",
                      })
                    : "—";

                  return (
                    <tr
                      key={rowId}
                      onClick={() => navigate(`/audit/${rowId}`)}
                      className="hover:bg-accent-soft/20 cursor-pointer transition-colors group"
                    >
                      <td className="p-3">
                        <span className="font-bold text-primary font-mono block">{rec.symbol}</span>
                        <span className="text-[10px] text-muted truncate max-w-[120px] block">
                          {rec.company_name || rec.symbol}
                        </span>
                      </td>
                      <td className="p-3">
                        <SignalBadge signal={rec.recommendation} confidence={rec.confidence} className="scale-90 origin-left" />
                      </td>
                      <td className="p-3 text-center font-bold text-accent-dark">{rec.horizon || "MID"}</td>
                      <td className="p-3 text-right font-mono font-bold text-emerald-800">
                        {rec.target_price ? `₹${rec.target_price.toLocaleString("en-IN")}` : "—"}
                      </td>
                      <td className="p-3 text-right text-muted font-mono">{formattedDate}</td>
                      <td className="p-3 text-center">
                        <ChevronRight size={14} className="mx-auto text-muted group-hover:text-accent transition-colors" />
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  // ── DETAIL MODE (with ID) ──────────────────────────────────
  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-24 space-y-3">
        <Spinner size="lg" />
        <p className="text-xs font-bold text-muted animate-pulse uppercase tracking-wider">
          Reconstructing from Amazon Aurora PostgreSQL…
        </p>
      </div>
    );
  }

  if (notFound || !data) {
    return (
      <div className="flex flex-col items-center justify-center py-24 space-y-4">
        <div className="p-4 bg-accent-soft rounded-full">
          <Database size={28} className="text-accent" />
        </div>
        <h2 className="text-lg font-black text-primary">Recommendation not found</h2>
        <p className="text-xs text-muted font-medium text-center max-w-xs">
          Could not locate this decision in Amazon Aurora PostgreSQL. The ID may be incorrect or the record archived.
        </p>
        <button
          onClick={() => navigate("/audit")}
          className="inline-flex items-center gap-2 px-4 py-2 bg-navy text-white rounded-lg text-sm font-bold hover:opacity-90 transition"
        >
          <ArrowLeft size={14} />
          Back to Audit Trails
        </button>
      </div>
    );
  }

  const rec = data;
  const finalColor = signalColor(rec.recommendation);

  const agentEntries = [
    { name: "TECHNICAL",      signal: rec.agent_signals.technical,     confidence: rec.technical_summary?.confidence },
    { name: "FUNDAMENTAL",   signal: rec.agent_signals.fundamental,    confidence: rec.fundamental_summary?.confidence },
    { name: "SENTIMENT",     signal: rec.agent_signals.sentiment,      confidence: rec.sentiment_summary?.confidence },
    { name: "CHART PATTERN", signal: rec.agent_signals.chart_pattern,  confidence: rec.chart_pattern_summary?.confidence },
  ];

  const dissenters = agentEntries.filter(
    (a) => a.signal?.toUpperCase() !== rec.recommendation?.toUpperCase()
  );

  const debateText = rec.debate_summary?.synthesis || rec.debate_summary?.bull_case || null;

  return (
    <div className="space-y-5 animate-in fade-in duration-200">

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 bg-white border border-border rounded-xl p-4 shadow-sm">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate("/history")}
            className="p-2 rounded-lg border border-border hover:bg-neutral-50 transition text-muted hover:text-primary"
          >
            <ArrowLeft size={16} />
          </button>
          <div>
            <h1 className="text-lg font-black text-primary tracking-tight">Decision Audit Trail</h1>
            <p className="text-xs text-muted font-medium">Reconstructed from Amazon Aurora PostgreSQL</p>
          </div>
        </div>
        <AuroraBadge />
      </div>

      {/* Summary card */}
      <div className="bg-white border border-border rounded-xl p-4 shadow-sm">
        <div className="flex flex-wrap items-center gap-3">
          <span className="font-mono text-2xl font-black text-primary">{rec.symbol}</span>
          {rec.company_name && <span className="text-sm text-muted font-medium">{rec.company_name}</span>}
          <SignalBadge signal={rec.recommendation} confidence={rec.confidence} />
        </div>

        <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: "Confidence", value: rec.confidence != null ? `${rec.confidence}%` : "—" },
            { label: "Horizon", value: rec.horizon ?? "—" },
            { label: "Target Price", value: rec.target_price != null ? inr(rec.target_price) : "—" },
            { label: "Created", value: rec.created_at ? formatTime(rec.created_at) : "—" },
          ].map((m) => (
            <div key={m.label} className="rounded-lg border border-border p-3">
              <p className="text-[10px] uppercase tracking-wide font-bold text-muted">{m.label}</p>
              <p className="mt-1 font-mono text-sm font-black text-primary">{m.value}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Two-column layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">

        {/* Timeline */}
        <div className="lg:col-span-7 space-y-6">

          {/* Step 1: Run */}
          <TimelineStep
            icon={<PlayCircle size={20} className="text-primary" fill="#1C2A39" stroke="white" />}
            title="Analysis Run"
            accentColor="#1C2A39"
          >
            <MetaRow label="Run ID" value={rec.run_id ? `${rec.run_id.slice(0, 16)}…` : "—"} />
            <MetaRow label="Rec ID" value={id ? `${id.slice(0, 16)}…` : "—"} />
            <MetaRow label="Symbol" value={rec.symbol} />
            <MetaRow label="Created" value={rec.created_at ? formatTime(rec.created_at) : "—"} />
          </TimelineStep>

          {/* Step 2: Agent Signals */}
          <TimelineStep
            icon={<Cpu size={20} className="text-muted" />}
            title="Specialist Agent Signals"
            subLabel="4 AI specialists evaluated this stock independently"
            accentColor="#5A6E85"
          >
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {agentEntries.map((a) => (
                <AgentCard key={a.name} name={a.name} signal={a.signal} confidence={a.confidence} />
              ))}
            </div>
          </TimelineStep>

          {/* Step 3: Debate */}
          <TimelineStep
            icon={<MessageSquare size={20} className="text-accent" />}
            title="Multi-Agent Debate"
            accentColor="#B85A10"
          >
            {debateText ? (
              <p className="text-sm leading-relaxed text-primary">{debateText}</p>
            ) : (
              <p className="text-sm text-muted">No debate summary available.</p>
            )}
            {rec.debate_summary?.bear_case && debateText !== rec.debate_summary.bear_case && (
              <div className="mt-3 rounded-lg bg-amber-50 border border-amber-200 p-3">
                <p className="text-xs font-bold text-amber-800">Bear case</p>
                <p className="mt-1 text-xs leading-relaxed text-amber-700">{rec.debate_summary.bear_case}</p>
              </div>
            )}
            {dissenters.length > 0 && (
              <div className="mt-3 flex items-start gap-2 rounded-lg bg-amber-50 border border-amber-200 p-3">
                <AlertTriangle size={14} className="mt-0.5 shrink-0 text-amber-600" />
                <p className="text-xs leading-relaxed text-amber-800">
                  <span className="font-bold">Dissenting: </span>
                  {dissenters.map((d) => `${d.name} (${d.signal})`).join(", ")} diverged from consensus.
                </p>
              </div>
            )}
          </TimelineStep>

          {/* Step 4: Validator */}
          <TimelineStep
            icon={
              rec.validator_status === "accepted"
                ? <ShieldCheck size={20} className="text-signal-buy" />
                : <ShieldX size={20} className="text-signal-sell" />
            }
            title="Validator Review"
            accentColor={rec.validator_status === "accepted" ? "#16A34A" : "#DC2626"}
          >
            <span
              className="inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-black"
              style={
                rec.validator_status === "accepted"
                  ? { backgroundColor: "#DCFCE7", color: "#166534", borderColor: "#BBF7D0" }
                  : { backgroundColor: "#FEE2E2", color: "#991B1B", borderColor: "#FECACA" }
              }
            >
              {rec.validator_status === "accepted" ? "ACCEPTED" : "ADJUSTED"}
            </span>
            {rec.validator_issues && rec.validator_issues.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {rec.validator_issues.map((issue, i) => (
                  <span
                    key={i}
                    className="rounded-full px-2 py-0.5 text-[11px] font-semibold bg-amber-100 text-amber-800"
                  >
                    L{issue.layer}: {issue.action} ({issue.field})
                  </span>
                ))}
              </div>
            )}
          </TimelineStep>

          {/* Step 5: Final */}
          <TimelineStep
            icon={
              rec.recommendation === "SELL"
                ? <XCircle size={20} style={{ color: "#DC2626" }} />
                : <CheckCircle2 size={20} style={{ color: "#16A34A" }} />
            }
            title="Final Recommendation"
            accentColor={finalColor}
            isLast
          >
            <div className="flex items-center justify-between">
              <SignalBadge signal={rec.recommendation} confidence={rec.confidence} />
              {rec.confidence != null && (
                <span className="font-mono text-2xl font-black" style={{ color: finalColor }}>
                  {rec.confidence}%
                </span>
              )}
            </div>
            {rec.narrative ? (
              <div
                className="mt-3 text-sm leading-relaxed text-primary prose prose-sm max-w-none"
                dangerouslySetInnerHTML={{ __html: rec.narrative }}
              />
            ) : null}
            {rec.confidence != null && (
              <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-neutral-100">
                <div
                  className="h-full rounded-full transition-all"
                  style={{ width: `${rec.confidence}%`, backgroundColor: finalColor }}
                />
              </div>
            )}
            {rec.key_risks.length > 0 && (
              <div className="mt-4">
                <p className="text-[10px] font-black uppercase tracking-wide text-muted mb-2">Key Risks</p>
                <ul className="space-y-1">
                  {rec.key_risks.map((r, i) => (
                    <li key={i} className="flex items-start gap-2 text-xs text-primary">
                      <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-signal-sell" />
                      {r}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {rec.key_catalysts.length > 0 && (
              <div className="mt-4">
                <p className="text-[10px] font-black uppercase tracking-wide text-muted mb-2">Key Catalysts</p>
                <ul className="space-y-1">
                  {rec.key_catalysts.map((c, i) => (
                    <li key={i} className="flex items-start gap-2 text-xs text-primary">
                      <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-signal-buy" />
                      {c}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </TimelineStep>
        </div>

        {/* Right: price targets */}
        <div className="lg:col-span-5">
          <div className="sticky top-6 rounded-xl border border-border bg-white p-4 shadow-sm space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-black text-primary">Price Targets</h3>
                <p className="text-[10px] text-muted font-medium">Tracked in Amazon Aurora PostgreSQL</p>
              </div>
              <div className="p-2 bg-emerald-50 rounded-lg">
                <Database size={16} className="text-signal-buy" />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              {[
                { label: "Entry Price", value: rec.entry_price != null ? inr(rec.entry_price) : "—" },
                { label: "Target Price", value: rec.target_price != null ? inr(rec.target_price) : "—" },
                { label: "Stop Loss", value: rec.stop_loss != null ? inr(rec.stop_loss) : "—" },
                { label: "Risk : Reward", value: rec.risk_reward != null ? `${rec.risk_reward.toFixed(1)}x` : "—" },
              ].map((m) => (
                <div key={m.label} className="rounded-lg border border-border p-3">
                  <p className="text-[10px] uppercase tracking-wide font-bold text-muted">{m.label}</p>
                  <p className="mt-1 font-mono text-sm font-black text-primary">{m.value}</p>
                </div>
              ))}
            </div>

            {rec.entry_price != null && rec.target_price != null && (
              <div className="rounded-lg border border-border p-3">
                <p className="text-[10px] uppercase tracking-wide font-bold text-muted">Upside Potential</p>
                {(() => {
                  const upside = ((rec.target_price - rec.entry_price) / rec.entry_price) * 100;
                  const c = upside >= 0 ? "#16A34A" : "#DC2626";
                  return (
                    <p className="mt-1 font-mono text-2xl font-black" style={{ color: c }}>
                      {upside >= 0 ? "+" : ""}{upside.toFixed(1)}%
                    </p>
                  );
                })()}
              </div>
            )}

            <div className="rounded-lg border border-border p-3 font-mono text-[10px] text-muted break-all">
              <p className="font-bold uppercase tracking-wide text-muted mb-1">Recommendation ID</p>
              {id}
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}
