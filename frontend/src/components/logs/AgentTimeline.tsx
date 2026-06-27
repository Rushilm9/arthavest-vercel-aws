import { useQuery } from "@tanstack/react-query";
import { apiService } from "../../services/api";
import { Spinner } from "../shared/Spinner";
import { Cpu, Clock, Zap, AlertTriangle, CheckCircle2, ChevronRight } from "lucide-react";
import { useState } from "react";

export function AgentTimeline() {
  const { data: runsData, isLoading } = useQuery({
    queryKey: ["agentLogRuns"],
    queryFn: () => apiService.getAgentLogRuns({ limit: 20 }),
    refetchInterval: 30000,
  });

  const { data: statsData } = useQuery({
    queryKey: ["agentStats"],
    queryFn: () => apiService.getAgentStats(24),
    refetchInterval: 60000,
  });

  const [expandedRun, setExpandedRun] = useState<string | null>(null);
  const [runDetail, setRunDetail] = useState<any>(null);
  const [isDetailLoading, setIsDetailLoading] = useState(false);

  const handleExpandRun = async (runId: string) => {
    if (expandedRun === runId) {
      setExpandedRun(null);
      setRunDetail(null);
      return;
    }
    setExpandedRun(runId);
    setIsDetailLoading(true);
    try {
      const detail = await apiService.getAgentLogRunDetail(runId);
      setRunDetail(detail);
    } catch (err) {
      console.error("Failed to load run detail", err);
    } finally {
      setIsDetailLoading(false);
    }
  };

  const runs = runsData?.runs || [];
  const agents = statsData?.agents || [];

  return (
    <div className="space-y-5 p-4">

      {/* Agent Stats Summary Cards */}
      {agents.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          {agents.map((agent: any) => (
            <div key={agent.agent_name} className="bg-white rounded-xl border border-border p-3 shadow-sm hover:shadow-md transition-all group">
              <div className="flex items-center gap-2 mb-2">
                <Cpu size={14} className="text-accent" />
                <span className="text-[10px] font-black text-primary uppercase tracking-wider truncate">{agent.agent_name.replace("Agent", "")}</span>
              </div>
              <div className="space-y-1">
                <div className="flex justify-between text-[10px]">
                  <span className="text-muted font-medium">Runs</span>
                  <span className="font-bold text-primary">{agent.count}</span>
                </div>
                <div className="flex justify-between text-[10px]">
                  <span className="text-muted font-medium">Failures</span>
                  <span className={`font-bold ${agent.failures > 0 ? "text-red-500" : "text-emerald-600"}`}>{agent.failures}</span>
                </div>
                <div className="flex justify-between text-[10px]">
                  <span className="text-muted font-medium">p50 Latency</span>
                  <span className="font-bold text-primary font-mono">{agent.p50_latency_ms ? `${Math.round(agent.p50_latency_ms)}ms` : "—"}</span>
                </div>
                <div className="flex justify-between text-[10px]">
                  <span className="text-muted font-medium">Tokens</span>
                  <span className="font-bold text-primary font-mono">{((agent.total_tokens_in || 0) + (agent.total_tokens_out || 0)).toLocaleString()}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Runs Timeline */}
      <div className="bg-white rounded-xl border border-border shadow-sm overflow-hidden">
        <div className="p-3 border-b border-border bg-neutral-50/50">
          <h3 className="text-xs font-black text-primary uppercase tracking-wider">Pipeline Run History</h3>
        </div>

        {isLoading ? (
          <div className="p-12 text-center"><Spinner size="md" /><p className="text-xs text-muted mt-2">Loading runs...</p></div>
        ) : runs.length === 0 ? (
          <div className="p-12 text-center text-sm text-muted font-medium">No pipeline runs found.</div>
        ) : (
          <div className="divide-y divide-neutral-100">
            {runs.map((run: any) => (
              <div key={run.id}>
                <button
                  onClick={() => handleExpandRun(run.id)}
                  className={`w-full text-left px-4 py-3 hover:bg-neutral-50/60 transition-colors flex items-center gap-3 ${expandedRun === run.id ? "bg-accent-soft/20" : ""}`}
                >
                  <div className={`w-2 h-2 rounded-full shrink-0 ${run.status === "COMPLETED" ? "bg-emerald-500" : run.status === "FAILED" ? "bg-red-500" : "bg-amber-400 animate-pulse"}`} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold text-primary">{run.workflow_name || "pipeline"}</span>
                      {run.symbol && <span className="text-[10px] font-mono font-bold bg-accent/10 text-accent-dark px-1.5 py-0.5 rounded">{run.symbol}</span>}
                    </div>
                    <div className="flex items-center gap-3 mt-0.5 text-[10px] text-muted font-medium">
                      <span className="flex items-center gap-1"><Cpu size={10} />{run.agent_count ?? 0} agents</span>
                      {run.elapsed_sec != null && <span className="flex items-center gap-1"><Clock size={10} />{run.elapsed_sec}s</span>}
                      {run.failed_count > 0 && <span className="flex items-center gap-1 text-red-500"><AlertTriangle size={10} />{run.failed_count} failed</span>}
                    </div>
                  </div>
                  <span className="text-[10px] text-muted font-mono">
                    {run.started_at ? new Date(run.started_at).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }) : ""}
                  </span>
                  <ChevronRight size={14} className={`text-muted transition-transform ${expandedRun === run.id ? "rotate-90" : ""}`} />
                </button>

                {/* Expanded Detail */}
                {expandedRun === run.id && (
                  <div className="px-4 pb-4 bg-neutral-50/30 border-t border-neutral-100 animate-in fade-in slide-in-from-top-1 duration-200">
                    {isDetailLoading ? (
                      <div className="py-6 text-center"><Spinner size="sm" /></div>
                    ) : runDetail?.agents ? (
                      <div className="space-y-2 pt-3">
                        {runDetail.agents.map((agent: any) => (
                          <div key={agent.id} className="flex items-center gap-3 p-2.5 bg-white rounded-lg border border-border text-xs">
                            {agent.status === "SUCCESS" ? <CheckCircle2 size={14} className="text-emerald-500 shrink-0" /> : <AlertTriangle size={14} className="text-red-500 shrink-0" />}
                            <span className="font-bold text-primary w-32 truncate">{agent.agent_name}</span>
                            <span className="font-mono text-muted">{agent.model_used || "—"}</span>
                            <span className={`ml-auto font-bold px-2 py-0.5 rounded text-[10px] ${
                              agent.signal === "BUY" ? "bg-emerald-50 text-emerald-700" :
                              agent.signal === "SELL" ? "bg-red-50 text-red-700" :
                              "bg-neutral-100 text-neutral-600"
                            }`}>{agent.signal || "—"}</span>
                            <span className="font-mono text-muted flex items-center gap-1"><Zap size={10} />{agent.latency_ms ? `${Math.round(agent.latency_ms)}ms` : "—"}</span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="py-4 text-xs text-muted text-center">No agent details available.</p>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
