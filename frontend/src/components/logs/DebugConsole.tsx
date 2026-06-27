import { useQuery } from "@tanstack/react-query";
import { apiService } from "../../services/api";
import { Spinner } from "../shared/Spinner";
import { AlertCircle, CheckCircle2, Clock, Hash } from "lucide-react";

export function DebugConsole() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["debugSummary"],
    queryFn: () => apiService.getDebugSummary(50, 50),
    refetchInterval: 30000,
    retry: 1,
  });

  if (isLoading) {
    return (
      <div className="p-12 text-center">
        <Spinner size="md" />
        <p className="text-xs text-muted mt-2">Loading system diagnostics...</p>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="p-6 space-y-3">
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 text-xs">
          <div className="flex items-center gap-2 text-amber-800 font-bold mb-1">
            <AlertCircle size={14} />
            Debug endpoint unavailable
          </div>
          <p className="text-amber-600">{(error as any)?.message || "Could not reach /debug/summary. The endpoint may not be registered."}</p>
        </div>

        {/* Fallback: Show system info */}
        <div className="bg-[#0d1117] rounded-xl p-4 font-mono text-xs text-slate-300 space-y-1 overflow-x-auto">
          <p className="text-emerald-400">$ system status</p>
          <p>Backend:  <span className="text-emerald-300">http://localhost:8000</span></p>
          <p>Frontend: <span className="text-emerald-300">http://localhost:5173</span></p>
          <p>Database: <span className="text-emerald-300">SQLite (test.db)</span></p>
          <p>LLM:     <span className="text-amber-300">Not configured (LLM_API_KEY_1 missing)</span></p>
          <p className="text-slate-500 mt-2">Tip: Set LLM_API_KEY_1 in your environment to enable AI analysis.</p>
        </div>
      </div>
    );
  }

  const summary = data as any;
  const failures = summary?.recent_failures || [];
  const logs = summary?.recent_agent_logs || [];

  return (
    <div className="p-4 space-y-4">
      {/* Summary Stats */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: "Total Runs", value: summary.total_runs ?? "—", icon: Hash },
            { label: "Failed Runs", value: summary.failed_runs ?? 0, icon: AlertCircle },
            { label: "Success Rate", value: summary.total_runs ? `${Math.round(((summary.total_runs - (summary.failed_runs ?? 0)) / summary.total_runs) * 100)}%` : "—", icon: CheckCircle2 },
            { label: "Avg Latency", value: summary.avg_latency_ms ? `${Math.round(summary.avg_latency_ms)}ms` : "—", icon: Clock },
          ].map((stat) => {
            const Icon = stat.icon;
            return (
              <div key={stat.label} className="bg-white rounded-lg border border-border p-3 flex items-center gap-2.5">
                <Icon size={14} className="text-accent shrink-0" />
                <div>
                  <p className="text-[10px] text-muted font-bold uppercase tracking-wider">{stat.label}</p>
                  <p className="text-sm font-black text-primary">{stat.value}</p>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Recent Failures */}
      {failures.length > 0 && (
        <div className="bg-red-50/50 border border-red-100 rounded-xl p-4">
          <h4 className="text-xs font-black text-red-800 uppercase tracking-wider mb-2">Recent Failures</h4>
          <div className="space-y-2">
            {failures.slice(0, 5).map((f: any, i: number) => (
              <div key={i} className="bg-white p-2.5 rounded-lg border border-red-100 text-xs">
                <span className="font-bold text-red-700">{f.agent_name || f.workflow_name || "Unknown"}</span>
                <span className="text-red-500 ml-2">{f.error || "No error message"}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Terminal-style log output */}
      <div className="bg-[#0d1117] rounded-xl p-4 font-mono text-[11px] text-slate-300 max-h-96 overflow-y-auto space-y-0.5 border border-slate-800">
        <p className="text-emerald-400 mb-2">$ tail -f /var/log/arthavest/agents.log</p>
        {logs.length > 0 ? (
          logs.slice(0, 30).map((log: any, i: number) => (
            <p key={i}>
              <span className="text-slate-500">[{log.created_at ? new Date(log.created_at).toLocaleTimeString() : "??:??"}]</span>{" "}
              <span className={log.status === "SUCCESS" ? "text-emerald-400" : "text-red-400"}>{log.status}</span>{" "}
              <span className="text-blue-300">{log.agent_name}</span>{" "}
              <span className="text-slate-400">signal={log.signal || "—"} conf={log.confidence ?? "—"} latency={log.latency_ms ? `${Math.round(log.latency_ms)}ms` : "—"}</span>
            </p>
          ))
        ) : (
          <>
            <p className="text-slate-500">No recent agent logs available.</p>
            <p className="text-slate-500">Run a discovery or analysis to generate logs.</p>
          </>
        )}
      </div>
    </div>
  );
}
