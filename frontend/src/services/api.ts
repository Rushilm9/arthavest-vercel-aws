import axios from "axios";
import { config } from "../config";
import type {
  AuthResponse,
  DiscoveryResponse,
  AnalyzeResponse,
  DispatchStatusResponse,
  MarketContextResponse,
  MarketDashboardResponse,
  QuotaTodayResponse,
  DebugSummaryResponse,
  AgentLogRunListResponse,
  AgentLogDetail,
  AgentLogRunDetailResponse,
  AgentStatsResponse,
  PaginatedNewsResponse,
  ConnectionsHealthResponse,
  ImproveProposeResponse,
  ImproveActionResponse
} from "../types";
import type { AlertItem } from "../context/WebSocketContext";

const api = axios.create({
  baseURL: config.API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

// Handle 409 Conflict (duplicate/idempotent request) gracefully
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 409) {
      console.warn("Duplicate request blocked:", error.response.data?.detail);
      return Promise.reject({
        isDuplicate: true,
        message: error.response.data?.detail || "Operation already in progress",
      });
    }
    return Promise.reject(error);
  }
);

export const apiService = {
  // ── Auth ──────────────────────────────────────────────────
  authLogin: async (email: string, password: string) => {
    const { data } = await api.post<AuthResponse>("/auth/login", { email, password });
    return data;
  },

  authRegister: async (email: string, password: string) => {
    const { data } = await api.post<AuthResponse>("/auth/register", { email, password });
    return data;
  },

  authLogout: async () => {
    const { data } = await api.post<{ message: string }>("/auth/logout");
    return data;
  },

  // ── Health ────────────────────────────────────────────────
  healthCheck: async () => {
    const { data } = await api.get<{ status: string }>("/health");
    return data;
  },

  connectionsHealth: async () => {
    const { data } = await api.get<ConnectionsHealthResponse>("/connections/health");
    return data;
  },

  // ── Alerts ────────────────────────────────────────────────
  getAlerts: async () => {
    const { data } = await api.get<{ alerts: AlertItem[] }>("/alerts/");
    return data;
  },

  discoverToday: async () => {
    const { data } = await api.get<DiscoveryResponse>("/analysis/discover/today");
    return data;
  },

  discoverCached: async () => {
    const { data } = await api.get<DiscoveryResponse>("/analysis/discover/cached");
    return data;
  },

  // Async fire-and-poll discovery. The sync POST /analysis/discover blocks ~60-90s
  // (6-node F1 pipeline + LLM classify) which exceeds browser/proxy timeouts and
  // makes the UI appear to "return nothing". The backend exposes a job queue:
  // POST /discover/jobs returns a job_id instantly; we poll until it's done.
  runDiscovery: async (horizon: string) => {
    // 1. Queue the job (returns immediately; dedups any in-flight run).
    const { data: queued } = await api.post<{ job_id: string; status: string }>(
      `/analysis/discover/jobs?horizon=${horizon}`,
      {}
    );
    const jobId = queued.job_id;
    
    // Save to localStorage so it survives page reloads
    localStorage.setItem("active_discovery_job", jobId);
    localStorage.setItem("active_discovery_horizon", horizon);

    try {
      const res = await apiService.pollDiscoveryJob(jobId, horizon);
      localStorage.removeItem("active_discovery_job");
      localStorage.removeItem("active_discovery_horizon");
      return res;
    } catch (e) {
      localStorage.removeItem("active_discovery_job");
      localStorage.removeItem("active_discovery_horizon");
      throw e;
    }
  },

  pollDiscoveryJob: async (jobId: string, horizon: string) => {
    // 2. Poll until done / error. F1 typically finishes in 60-90s; cap at ~5 min.
    const POLL_MS = 3000;
    const MAX_POLLS = 100; // 100 * 3s = 300s ceiling
    for (let i = 0; i < MAX_POLLS; i++) {
      await new Promise((r) => setTimeout(r, POLL_MS));
      const { data: job } = await api.get<{
        status: string;
        error?: string | null;
        response?: DiscoveryResponse;
      }>(`/analysis/discover/jobs/${jobId}?horizon=${horizon}`);
      if (job.status === "done") {
        // The poll endpoint embeds the full DiscoveryResponse when finished.
        return (job.response ?? null) as DiscoveryResponse | null;
      }
      if (job.status === "error") {
        throw new Error(job.error || "Discovery job failed");
      }
    }
    throw new Error("Discovery job timed out after 5 minutes");
  },

  dispatchAnalyseAll: async (runId: string, horizon: string) => {
    const { data } = await api.post<{ run_id: string; queued: number; message: string }>(
      `/analysis/dispatch/${runId}?horizon=${horizon}&force_refresh=true`,
      {}
    );
    return data;
  },

  getDispatchStatus: async (runId: string) => {
    const { data } = await api.get<DispatchStatusResponse>(`/analysis/status/${runId}`);
    return data;
  },

  cancelDispatch: async (runId: string) => {
    const { data } = await api.post<{ run_id: string; status: string; message: string }>(
      `/analysis/cancel/${runId}`,
      {}
    );
    return data;
  },


  analyzeStock: async (symbol: string, suggestedHorizon?: string) => {
    const { data } = await api.post<AnalyzeResponse>("/analysis/analyze", {
      symbol,
      suggested_horizon: suggestedHorizon,
    });
    return data;
  },

  getLatestAnalysis: async (symbol: string, horizon: string) => {
    const { data } = await api.get<AnalyzeResponse>(`/analysis/latest/${symbol}?horizon=${horizon}`);
    return data;
  },

  getHistory: async (filters: {
    symbol?: string;
    signal?: string;
    date_from?: string;
    date_to?: string;
    limit?: number;
    page?: number;
  }) => {
    const params = new URLSearchParams();
    if (filters.symbol) params.append("symbol", filters.symbol);
    if (filters.signal) params.append("signal", filters.signal);
    if (filters.date_from) params.append("date_from", filters.date_from);
    if (filters.date_to) params.append("date_to", filters.date_to);
    if (filters.limit) params.append("limit", filters.limit.toString());
    if (filters.page) params.append("page", filters.page.toString());

    const { data } = await api.get<{ count: number; page: number; total_pages: number; recommendations: AnalyzeResponse[] }>(
      `/analysis/history?${params.toString()}`
    );
    return data;
  },

  getHistoryDetail: async (recId: string) => {
    const { data } = await api.get<AnalyzeResponse>(`/analysis/history/${recId}`);
    return data;
  },

  searchSymbols: async (q: string, limit: number = 10) => {
    const { data } = await api.get<{ symbol: string; name: string }[]>(
      `/analysis/symbols/search?q=${q}&limit=${limit}`
    );
    return data;
  },

  getMarketDashboard: async () => {
    const { data } = await api.get<MarketDashboardResponse>("/market/dashboard");
    return data;
  },

  getMarketNews: async (category?: string, search?: string, page: number = 1, limit: number = 10) => {
    const params = new URLSearchParams();
    if (category && category !== "All") params.append("category", category);
    if (search) params.append("search", search);
    params.append("page", page.toString());
    params.append("limit", limit.toString());

    const { data } = await api.get<PaginatedNewsResponse>(`/market/news?${params.toString()}`);
    return data;
  },

  getMarketContext: async () => {
    const { data } = await api.get<MarketContextResponse>("/analysis/context/today");
    return data;
  },

  getQuota: async () => {
    const { data } = await api.get<QuotaTodayResponse>("/quota/today");
    return data;
  },

  // Logs endpoints (§3.1)
  getDebugSummary: async (failuresLimit: number = 50, agentLogsLimit: number = 50) => {
    const { data } = await api.get<DebugSummaryResponse>(
      `/debug/summary?failures_limit=${failuresLimit}&agent_logs_limit=${agentLogsLimit}`
    );
    return data;
  },

  getAgentLogRuns: async (filters?: { status?: string; workflow?: string; symbol?: string; limit?: number; page?: number }) => {
    const params = new URLSearchParams();
    if (filters?.status) params.append("status", filters.status);
    if (filters?.workflow) params.append("workflow", filters.workflow);
    if (filters?.symbol) params.append("symbol", filters.symbol);
    if (filters?.limit) params.append("limit", filters.limit.toString());
    if (filters?.page) params.append("page", filters.page.toString());

    const { data } = await api.get<AgentLogRunListResponse>(`/api/agentlogs/runs?${params.toString()}`);
    return data;
  },

  getAgentLogRunDetail: async (runId: string) => {
    const { data } = await api.get<AgentLogRunDetailResponse>(`/api/agentlogs/runs/${runId}`);
    return data;
  },

  getAgentLogDetail: async (agentLogId: string) => {
    const { data } = await api.get<AgentLogDetail>(`/api/agentlogs/agents/${agentLogId}`);
    return data;
  },

  getAgentStats: async (hours: number = 24) => {
    const { data } = await api.get<AgentStatsResponse>(`/api/agentlogs/stats?hours=${hours}`);
    return data;
  },

  // ── Arize AI Improve ────────────────────────────────────────
  // propose runs the Improver agent + a Phoenix MCP call (cold-spawns npx, ~6s)
  // and takes ~30s end-to-end. Give it explicit headroom so the request doesn't
  // sit on the default timeout and look like a hang; approve/reject are MCP-only
  // (prompt-tag moves) but still spawn npx, so a 90s ceiling is safe.
  improvePropose: async (promptName: string) => {
    const { data } = await api.post<ImproveProposeResponse>(
      "/api/improve/propose",
      { prompt_name: promptName },
      { timeout: 120000 }
    );
    return data;
  },

  improveApprove: async (promptName: string) => {
    const { data } = await api.post<ImproveActionResponse>(
      "/api/improve/approve",
      { prompt_name: promptName },
      { timeout: 90000 }
    );
    return data;
  },

  improveReject: async (promptName: string) => {
    const { data } = await api.post<ImproveActionResponse>(
      "/api/improve/reject",
      { prompt_name: promptName },
      { timeout: 90000 }
    );
    return data;
  }
};
