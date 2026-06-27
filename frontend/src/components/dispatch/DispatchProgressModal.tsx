import { useState } from "react";
import { useDispatchStatus } from "../../hooks/useDispatchStatus";
import { X, Play, AlertCircle, Check, Loader2, Award } from "lucide-react";
import { Spinner } from "../shared/Spinner";
import { StockDetail } from "../analysis/StockDetail";
import { apiService } from "../../services/api";

interface DispatchProgressModalProps {
  runId: string;
  horizon: string;
  onClose: () => void;
}

export function DispatchProgressModal({ runId, horizon, onClose }: DispatchProgressModalProps) {
  const { data: status, isLoading, isError } = useDispatchStatus(runId, true);
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [isCancelling, setIsCancelling] = useState(false);

  const handleCancel = async () => {
    setIsCancelling(true);
    try {
      await apiService.cancelDispatch(runId);
    } catch (err) {
      console.error("Failed to cancel dispatch run", err);
    } finally {
      setIsCancelling(false);
    }
  };


  if (isLoading) {
    return (
      <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
        <div className="bg-card w-full max-w-lg rounded-xl border border-border shadow-2xl p-6 text-center space-y-3">
          <Spinner size="lg" />
          <h3 className="font-bold text-primary text-base">Connecting to dispatcher run...</h3>
          <p className="text-xs text-muted">Registering stock symbols and firing specialist worker agents.</p>
        </div>
      </div>
    );
  }

  if (isError || !status) {
    return (
      <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
        <div className="bg-card w-full max-w-lg rounded-xl border border-border shadow-2xl p-6 text-center space-y-4">
          <AlertCircle size={40} className="text-signal-sell mx-auto" />
          <h3 className="font-bold text-primary text-base">Dispatcher Connection Failed</h3>
          <p className="text-xs text-muted">
            The status polling endpoint returned an error. Please verify that the backend is active.
          </p>
          <button
            onClick={onClose}
            className="px-4 py-2 bg-neutral-100 hover:bg-neutral-200 border border-neutral-300 rounded-lg text-xs font-semibold text-primary"
          >
            Go Back
          </button>
        </div>
      </div>
    );
  }

  const { total, done, running, queued, errors, complete, stocks } = status;

  // Progress Percentage
  const progressPct = total > 0 ? ((done + errors) / total) * 100 : 0;

  // Selected Stock full response inside status tile cache
  const selectedStockData = selectedSymbol ? (stocks[selectedSymbol]?.full_response || null) : null;

  return (
    <div 
      className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4 overflow-y-auto"
      onClick={onClose}
    >
      <div 
        className="bg-card w-full max-w-3xl rounded-xl border border-border shadow-2xl overflow-hidden animate-in zoom-in-95 duration-200 flex flex-col my-4 sm:my-8 max-h-[90dvh]"
        onClick={(e) => e.stopPropagation()}
      >

        {/* Header */}
        <div className="px-4 sm:px-5 py-4 border-b border-border flex items-center justify-between gap-3 bg-cream/35">
          <div className="min-w-0">
            <h3 className="font-semibold text-primary flex items-center gap-2">
              <span className="p-1 bg-accent/10 text-accent rounded shrink-0">
                <Play size={14} className="fill-accent text-accent" />
              </span>
              <span className="truncate">Analysing {horizon} Horizon Stocks</span>
            </h3>
            <p className="text-xs text-muted mt-0.5 truncate">Run ID: <span className="font-mono">{runId}</span></p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-full hover:bg-neutral-100 transition-colors text-muted hover:text-primary"
          >
            <X size={16} />
          </button>
        </div>

        {/* Modal content body */}
        <div className="p-4 sm:p-5 flex-1 overflow-y-auto space-y-5 min-h-0">
          {/* Progress bar */}
          <div className="space-y-2">
            <div className="flex justify-between text-xs font-semibold">
              <span className="text-primary">
                Progress: {done} done · {running} active · {queued} queued · {errors} errors
              </span>
              <span className="font-mono text-accent-dark">{Math.round(progressPct)}%</span>
            </div>
            <div className="w-full h-3 bg-neutral-100 rounded-full overflow-hidden border border-neutral-200/50">
              <div
                className="h-full rounded-full transition-all duration-300 bg-accent"
                style={{ width: `${progressPct}%` }}
              />
            </div>
          </div>

          {/* Tile Grid */}
          <div className="space-y-2.5">
            <h4 className="text-xs font-bold text-primary uppercase tracking-wider">Queue status map</h4>
            <div className="grid grid-cols-3 gap-2">
              {Object.entries(stocks).map(([symbol, item]) => {
                const isDone = item.status === "done";
                const isActive = item.status === "running";
                const isError = item.status === "error";

                let tileBg = "bg-neutral-50 border-neutral-200 text-muted";
                let tileIcon = <span className="w-1.5 h-1.5 bg-neutral-400 rounded-full shrink-0" />;

                if (isDone) {
                  // Simply use green for done to indicate successful processing
                  tileBg = "bg-emerald-50 border-emerald-300 text-emerald-700 cursor-pointer shadow-sm hover:scale-105 transition-transform";
                  tileIcon = <Check size={11} className="stroke-[3]" />;
                } else if (isActive) {
                  tileBg = "bg-blue-50 border-blue-300 text-blue-700 animate-pulse font-medium";
                  tileIcon = <Loader2 size={11} className="animate-spin" />;
                } else if (isError) {
                  tileBg = "bg-red-50 border-red-300 text-red-700 font-semibold";
                  tileIcon = <AlertCircle size={11} />;
                }

                const isSelected = selectedSymbol === symbol;

                return (
                  <button
                    key={symbol}
                    type="button"
                    disabled={!isDone}
                    onClick={() => setSelectedSymbol(isSelected ? null : symbol)}
                    className={`flex items-center justify-center gap-1.5 px-2 py-2 rounded-lg border text-xs font-mono font-bold transition-all ${tileBg} ${
                      isSelected ? "ring-2 ring-accent border-transparent scale-105" : ""
                    }`}
                  >
                    {tileIcon}
                    <span className="truncate">{symbol}</span>
                    {isDone && item.confidence && (
                      <span className="text-[9px] opacity-75 font-normal">
                        {Math.round(item.confidence)}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Drill-down analysis drawer if clicked */}
          {selectedSymbol && (
            <div className="border border-border rounded-xl overflow-hidden bg-neutral-50/50 p-4 space-y-3 animate-in slide-in-from-bottom-2 duration-200">
              <div className="flex justify-between items-center pb-2 border-b border-neutral-200">
                <h4 className="text-xs font-black text-accent-dark uppercase tracking-wider flex items-center gap-1">
                  <Award size={14} />
                  <span>Real-time Drilldown: {selectedSymbol}</span>
                </h4>
                <button
                  onClick={() => setSelectedSymbol(null)}
                  className="text-xs text-muted hover:text-primary font-bold"
                >
                  Close Report
                </button>
              </div>
              <StockDetail
                data={selectedStockData}
                isLoading={false}
                symbolName={selectedSymbol}
              />
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-4 sm:px-5 py-3 border-t border-border flex flex-col-reverse sm:flex-row justify-between items-stretch sm:items-center gap-3 bg-neutral-50">
          <span className="text-[10px] md:text-xs text-muted leading-none font-medium">
            {complete ? (
              Object.values(stocks).some((item: any) => item.error === "Cancelled by user") ? (
                <span className="text-red-700 font-bold flex items-center gap-1">
                  <AlertCircle size={14} /> Queue Dispatch Stopped by User
                </span>
              ) : (
                <span className="text-emerald-700 font-bold flex items-center gap-1">
                  <Check size={14} className="stroke-[3]" /> Queue Dispatch Completed!
                </span>
              )
            ) : (
              "Analyses will keep running in the background if closed."
            )}
          </span>
          <div className="flex gap-2 justify-end">
            {!complete && (
              <button
                type="button"
                disabled={isCancelling}
                onClick={handleCancel}
                className="px-4 py-2 sm:py-1.5 bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white text-xs font-bold rounded-md shadow-sm transition-colors shrink-0"
              >
                {isCancelling ? "Stopping..." : "Stop Queue"}
              </button>
            )}
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 sm:py-1.5 bg-accent hover:bg-accent-dark transition-colors text-white text-xs font-bold rounded-md shadow-sm shrink-0"
            >
              {complete ? "Close Modal" : "Keep Running in Background"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
