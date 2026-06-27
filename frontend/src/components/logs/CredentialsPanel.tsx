import { useQuery } from "@tanstack/react-query";
import { apiService } from "../../services/api";
import { Wifi, WifiOff, Server, Database, Brain, Globe } from "lucide-react";

export function CredentialsPanel() {
  const { data, isLoading } = useQuery({
    queryKey: ["connectionsHealth"],
    queryFn: () => apiService.connectionsHealth(),
    refetchInterval: 30000,
    retry: 1,
  });

  const { data: healthData } = useQuery({
    queryKey: ["healthCheck"],
    queryFn: () => apiService.healthCheck(),
    refetchInterval: 30000,
    retry: 1,
  });

  const checks = (data as any)?.checks || {};

  const services = [
    { name: "Backend API", icon: Server, status: (healthData?.status === "ok" || healthData?.status === "healthy") ? "up" : isLoading ? "checking" : "down" },
    { name: "Database", icon: Database, status: checks?.database?.status === "ok" ? "up" : isLoading ? "checking" : checks?.database?.status || "unknown" },
    { name: "LLM (Vertex AI)", icon: Brain, status: checks?.gemini?.[0]?.status === "ok" ? "up" : isLoading ? "checking" : checks?.gemini?.[0]?.status || "not configured" },
    { name: "Vertex MCP", icon: Globe, status: checks?.vertex_mcp?.status === "ok" ? "up" : isLoading ? "checking" : "optional" },
    { name: "Arize MCP", icon: Globe, status: checks?.arize_mcp?.status === "ok" ? "up" : isLoading ? "checking" : "optional" },
  ];

  return (
    <div className="bg-white rounded-xl border border-border shadow-sm p-4">
      <h3 className="text-xs font-black text-muted uppercase tracking-wider mb-3">Live Connections</h3>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {services.map((svc) => {
          const Icon = svc.icon;
          const isUp = svc.status === "up" || svc.status === "ok" || svc.status === "connected";
          const isChecking = svc.status === "checking";
          return (
            <div key={svc.name} className="flex items-center gap-2.5 p-3 rounded-lg border border-border bg-neutral-50/50">
              <Icon size={16} className={isUp ? "text-emerald-500" : isChecking ? "text-amber-400 animate-pulse" : "text-red-400"} />
              <div className="min-w-0">
                <p className="text-xs font-bold text-primary truncate">{svc.name}</p>
                <p className={`text-[10px] font-semibold ${isUp ? "text-emerald-600" : isChecking ? "text-amber-500" : "text-red-500"}`}>
                  {isUp ? "Connected" : isChecking ? "Checking..." : typeof svc.status === "string" ? svc.status : "Offline"}
                </p>
              </div>
              {isUp ? <Wifi size={12} className="ml-auto text-emerald-400" /> : <WifiOff size={12} className="ml-auto text-red-300" />}
            </div>
          );
        })}
      </div>
    </div>
  );
}
