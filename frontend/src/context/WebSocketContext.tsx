import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from "react";
import { useAuth } from "./AuthContext";
import { apiService } from "../services/api";
import { config } from "../config";
import { 
  TrendingUp, 
  TrendingDown, 
  Newspaper, 
  AlertTriangle, 
  Info, 
  X
} from "lucide-react";

export type AlertType = "TARGET_HIT" | "STOP_LOSS" | "SENTIMENT_DROP" | "NEWS_SPIKE" | "REVIEW_NEEDED" | "INFO";

export interface AlertItem {
  id: string;
  type: AlertType;
  message: string;
  date: string;
  is_read: boolean;
}

export interface ToastItem {
  id: string;
  type: AlertType;
  message: string;
  title: string;
  duration?: number;
}

interface WebSocketContextValue {
  status: "connected" | "connecting" | "disconnected";
  alerts: AlertItem[];
  toasts: ToastItem[];
  addToast: (type: AlertType, title: string, message: string, duration?: number) => void;
  removeToast: (id: string) => void;
  fetchInitialAlerts: () => Promise<void>;
}

const WebSocketContext = createContext<WebSocketContextValue | null>(null);

export function WebSocketProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const [status, setStatus] = useState<"connected" | "connecting" | "disconnected">("disconnected");
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const reconnectAttemptsRef = useRef(0);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const addToast = useCallback((type: AlertType, title: string, message: string, duration = 6000) => {
    const id = Math.random().toString(36).substring(2, 9);
    setToasts((prev) => [...prev, { id, type, title, message, duration }]);

    if (duration > 0) {
      setTimeout(() => {
        removeToast(id);
      }, duration);
    }
  }, [removeToast]);



  const fetchInitialAlerts = useCallback(async () => {
    if (!user) return;
    try {
      const data = await apiService.getAlerts();
      if (data && data.alerts) {
        setAlerts(data.alerts);
      }
    } catch (err) {
      console.warn("Failed to load initial alerts from REST endpoint:", err);
    }
  }, [user]);

  // Connect to WebSocket endpoint
  const connect = useCallback(() => {
    if (!user) return;

    // Build WebSocket URL from configuration
    let apiBase = config.API_BASE_URL || window.location.origin;
    if (apiBase.endsWith("/")) {
      apiBase = apiBase.slice(0, -1);
    }
    const wsBaseUrl = apiBase.replace(/^http/, "ws");
    const wsUrl = `${wsBaseUrl}/alerts/ws`;

    console.log(`Connecting to WebSocket: ${wsUrl}`);
    setStatus("connecting");

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log("WebSocket connected successfully!");
        setStatus("connected");
        reconnectAttemptsRef.current = 0;
        if (reconnectTimeoutRef.current) {
          clearTimeout(reconnectTimeoutRef.current);
          reconnectTimeoutRef.current = null;
        }
        // Fetch fresh list of alerts on initial connection
        fetchInitialAlerts();
      };

      ws.onmessage = (event) => {
        try {
          const rawData = JSON.parse(event.data);
          console.log("Received WebSocket alert:", rawData);

          const alertData: AlertItem = {
            id: rawData.id || Math.random().toString(36).substring(2, 9),
            type: (rawData.type || "INFO") as AlertType,
            message: rawData.message || "",
            date: rawData.date || new Date().toISOString(),
            is_read: rawData.is_read || false
          };

          // Append to state
          setAlerts((prev) => [alertData, ...prev].slice(0, 50));

          // Render beautiful toast
          let title = "System Notification";
          switch (alertData.type) {
            case "TARGET_HIT":
              title = "⭐ Target Price Achieved";
              break;
            case "STOP_LOSS":
              title = "⚠️ Stop Loss Breached";
              break;
            case "SENTIMENT_DROP":
              title = "📉 Market Sentiment Drop";
              break;
            case "NEWS_SPIKE":
              title = "📰 Critical News Alert";
              break;
            case "REVIEW_NEEDED":
              title = "🔍 Agent Review Required";
              break;
            case "INFO":
              title = "ℹ️ System Update";
              break;
          }

          addToast(alertData.type, title, alertData.message, 6000);
        } catch (err) {
          console.error("Error parsing WebSocket JSON data:", err);
        }
      };

      ws.onclose = () => {
        console.log("WebSocket disconnected.");
        setStatus("disconnected");
        wsRef.current = null;

        // Exponential backoff reconnect
        if (user) {
          const backoff = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current), 30000);
          reconnectAttemptsRef.current += 1;
          console.log(`Attempting reconnection in ${backoff / 1000}s...`);
          reconnectTimeoutRef.current = setTimeout(() => {
            connect();
          }, backoff) as unknown as number;
        }
      };

      ws.onerror = (error) => {
        console.error("WebSocket connection error:", error);
        ws.close();
      };

    } catch (err) {
      console.error("Fatal error establishing WebSocket:", err);
      setStatus("disconnected");
    }
  }, [user, addToast, fetchInitialAlerts]);

  // Handle lifecycle of connection relative to user session
  useEffect(() => {
    if (user) {
      connect();
    } else {
      // Disconnect if user logs out
      if (wsRef.current) {
        wsRef.current.close();
      }
      setStatus("disconnected");
      setAlerts([]);
    }

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, [user, connect]);

  // Helper icons component
  const getToastIcon = (type: AlertType) => {
    switch (type) {
      case "TARGET_HIT":
        return <TrendingUp className="text-emerald-500 w-5 h-5" />;
      case "STOP_LOSS":
        return <TrendingDown className="text-red-500 w-5 h-5" />;
      case "SENTIMENT_DROP":
        return <TrendingDown className="text-orange-500 w-5 h-5" />;
      case "NEWS_SPIKE":
        return <Newspaper className="text-purple-500 w-5 h-5" />;
      case "REVIEW_NEEDED":
        return <AlertTriangle className="text-amber-500 w-5 h-5" />;
      default:
        return <Info className="text-blue-500 w-5 h-5" />;
    }
  };

  const getToastBorderColor = (type: AlertType) => {
    switch (type) {
      case "TARGET_HIT":
        return "border-l-emerald-500";
      case "STOP_LOSS":
        return "border-l-red-500";
      case "SENTIMENT_DROP":
        return "border-l-orange-500";
      case "NEWS_SPIKE":
        return "border-l-purple-500";
      case "REVIEW_NEEDED":
        return "border-l-amber-500";
      default:
        return "border-l-blue-500";
    }
  };

  return (
    <WebSocketContext.Provider value={{ status, alerts, toasts, addToast, removeToast, fetchInitialAlerts }}>
      {children}

      {/* Floating Modern Toast Notification Container */}
      <div className="fixed top-4 right-4 z-50 flex flex-col gap-3 w-full max-w-sm pointer-events-none select-none px-4 sm:px-0">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`group w-full bg-white/95 backdrop-blur-md border-l-4 border border-border/80 ${getToastBorderColor(toast.type)} shadow-2xl rounded-xl p-4 flex gap-3 text-primary pointer-events-auto relative overflow-hidden transition-all duration-300 animate-in slide-in-from-right duration-200`}
            role="alert"
          >
            <div className="mt-0.5 shrink-0">
              {getToastIcon(toast.type)}
            </div>
            <div className="flex-1 space-y-0.5">
              <h4 className="font-extrabold text-[12px] uppercase tracking-wider text-primary flex items-center gap-1.5 leading-tight">
                {toast.title}
              </h4>
              <p className="text-xs text-muted font-medium leading-relaxed font-sans pr-4">
                {toast.message}
              </p>
            </div>
            
            <button
              onClick={() => removeToast(toast.id)}
              className="absolute right-2 top-2 p-1 text-neutral-400 hover:text-primary hover:bg-neutral-100/60 rounded-md transition-colors shrink-0"
            >
              <X size={14} />
            </button>

            {/* Progress bar — pauses on hover via group-hover */}
            {toast.duration && toast.duration > 0 && (
              <div 
                className="absolute bottom-0 left-0 h-[2px] bg-accent/20 group-hover:[animation-play-state:paused]"
                style={{ 
                  width: "100%", 
                  animation: `shrinkWidth ${toast.duration}ms linear forwards` 
                }}
              />
            )}
          </div>
        ))}
      </div>
    </WebSocketContext.Provider>
  );
}

export function useWebSocket() {
  const context = useContext(WebSocketContext);
  if (!context) {
    throw new Error("useWebSocket must be used within a WebSocketProvider");
  }
  return context;
}
