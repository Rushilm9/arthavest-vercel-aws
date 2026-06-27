import { useState } from "react";
import { DebugConsole } from "../components/logs/DebugConsole";
import { AgentTimeline } from "../components/logs/AgentTimeline";
import { CredentialsPanel } from "../components/logs/CredentialsPanel";
import { Terminal, Cpu, Activity } from "lucide-react";

type LogTab = "system" | "agent";

export function Logs() {
  const [activeTab, setActiveTab] = useState<LogTab>("agent");

  return (
    <div className="space-y-5 animate-in fade-in duration-200">
      
      {/* Credentials & Connections Live diagnostics board */}
      <CredentialsPanel />
      
      {/* HEADER CONTROLS AREA */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 bg-white border border-border rounded-xl p-4 shadow-sm">
        <div className="flex items-center gap-2">
          <div className="p-2 bg-neutral-900 rounded-lg text-neutral-100 border border-neutral-800">
            <Terminal size={20} className="text-accent" />
          </div>
          <div>
            <h2 className="text-base md:text-lg font-black text-primary tracking-tight">System Logs</h2>
            <p className="text-xs text-muted font-medium">Drilldown agent logic pipelines, audit worker logs, and inspect LLM trace parameters.</p>
          </div>
        </div>

        {/* Tab switchers */}
        <div className="flex bg-neutral-100 p-1 border rounded-lg select-none">
          <button
            type="button"
            onClick={() => setActiveTab("agent")}
            className={`px-3 py-1.5 rounded-md text-xs font-bold transition-all flex items-center gap-1.5 ${
              activeTab === "agent"
                ? "bg-white text-navy shadow-sm"
                : "text-muted hover:text-primary"
            }`}
          >
            <Cpu size={13} />
            <span>Worker Timelines</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("system")}
            className={`px-3 py-1.5 rounded-md text-xs font-bold transition-all flex items-center gap-1.5 ${
              activeTab === "system"
                ? "bg-white text-navy shadow-sm"
                : "text-muted hover:text-primary"
            }`}
          >
            <Activity size={13} />
            <span>System Diagnostics</span>
          </button>
        </div>
      </div>

      {/* RENDER ACTIVE DIAGNOSTIC PANE */}
      <div className="bg-cream/20 rounded-xl border border-dashed border-border mt-4">
        {activeTab === "agent" ? <AgentTimeline /> : <DebugConsole />}
      </div>

    </div>
  );
}
