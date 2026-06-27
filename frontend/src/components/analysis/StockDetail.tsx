import { useState, useEffect } from "react";
import type { AnalyzeResponse } from "../../types";
import { ReasoningAccordion } from "./ReasoningAccordion";
import { SignalBadge } from "../shared/SignalBadge";
import { PlayCircle, ClipboardCopy, Info, Maximize2, X, RefreshCw, Download } from "lucide-react";
import { Spinner } from "../shared/Spinner";
import { generateAnalysisPdf } from "../../utils/generateAnalysisPdf";

interface StockDetailProps {
  data: AnalyzeResponse | null;
  isLoading: boolean;
  onAnalyseClick?: () => void;
  isAnalysing?: boolean;
  symbolName?: string | null;
}

export function StockDetail({
  data,
  isLoading,
  onAnalyseClick,
  isAnalysing = false,
  symbolName,
}: StockDetailProps) {
  const [isFullscreen, setIsFullscreen] = useState(false);
  
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, [symbolName]);
  
  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center p-12 h-64 bg-white border border-border rounded-xl shadow-sm text-center">
        <Spinner size="lg" className="mb-3" />
        <h4 className="text-sm font-bold text-primary">Assembling specialist intelligence reports...</h4>
        <p className="text-xs text-muted mt-1 max-w-[280px]">Synthesizing technical levels, sentiment feeds, and fundamental balance sheets.</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="flex flex-col items-center justify-center p-8 h-80 bg-white/50 border border-dashed border-border rounded-xl text-center select-none">
        <ClipboardCopy size={36} className="text-muted opacity-30 mb-2.5 animate-pulse" />
        <h4 className="text-xs md:text-sm font-bold text-primary">No Stock Selected</h4>
        <p className="text-xs text-muted mt-1 max-w-[300px]">
          Select a discovered stock from the list, search for a symbol above, or click Analyse All to begin.
        </p>
      </div>
    );
  }

  // If recommendation is empty or wait and no entry/target has been set (meaning not analysed)
  const isNotAnalysed = !data.run_id && !data.recommendation_id && !data.id;

  if (isNotAnalysed) {
    return (
      <div className="flex flex-col items-center justify-center p-8 h-80 bg-white border border-border rounded-xl text-center shadow-sm">
        <Info size={36} className="text-accent opacity-60 mb-2.5" />
        <h4 className="text-sm md:text-base font-bold text-primary">{data.symbol} - Not Analysed Today</h4>
        <p className="text-xs text-muted mt-1 max-w-[350px]">
          This stock was discovered in the morning scans but has not yet been processed by the specialist multi-agent team.
        </p>
        
        {onAnalyseClick && (
          <button
            type="button"
            disabled={isAnalysing}
            onClick={onAnalyseClick}
            className="inline-flex items-center gap-1.5 mt-5 px-5 py-2.5 bg-accent hover:bg-accent-dark text-white rounded-lg text-xs md:text-sm font-bold shadow-md transition-colors disabled:opacity-50"
          >
            {isAnalysing ? (
              <>
                <Spinner size="sm" className="border-t-transparent border-white" />
                <span>Running Specialist Team...</span>
              </>
            ) : (
              <>
                <PlayCircle size={16} />
                <span>Analyse {data.symbol} Now</span>
              </>
            )}
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-4 animate-in fade-in duration-200">
      
      {/* 1. KEY QUANT PARAMETERS SUMMARY */}
      <div className="bg-white border border-border rounded-xl p-4 md:p-5 shadow-sm space-y-4">
        {/* Header Name & Badges */}
        <div className="flex justify-between items-start gap-4 flex-wrap">
          <div>
            <h3 className="text-lg md:text-xl font-black text-primary tracking-tight">{data.symbol}</h3>
            <p className="text-xs text-muted font-medium mt-0.5">
              {data.company_name || symbolName || "Indian Equity Market Asset"}
            </p>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {onAnalyseClick && !isNotAnalysed && (
              <button
                type="button"
                disabled={isAnalysing}
                onClick={onAnalyseClick}
                className="inline-flex items-center gap-1.5 px-2.5 py-1.5 bg-accent hover:bg-accent-dark text-white rounded-lg text-[10px] md:text-xs font-bold transition-all disabled:opacity-50 shadow-sm border border-accent/20"
                title="Run F2 Analysis Specialists Again"
              >
                {isAnalysing ? (
                  <>
                    <Spinner size="sm" className="border-t-transparent border-white w-3 h-3" />
                    <span>Analysing...</span>
                  </>
                ) : (
                  <>
                    <RefreshCw size={11} className={isAnalysing ? "animate-spin" : ""} />
                    <span>Re-Analyse</span>
                  </>
                )}
              </button>
            )}
            <button
              type="button"
              onClick={() => setIsFullscreen(true)}
              className="inline-flex items-center gap-1.5 px-2.5 py-1.5 bg-white border border-border rounded-lg text-[10px] md:text-xs font-bold text-muted hover:text-primary hover:bg-neutral-50 transition-all shadow-sm"
              title="View Detailed Report in Full Screen Modal"
            >
              <Maximize2 size={11} />
              <span>Full Screen</span>
            </button>
            <button
              type="button"
              onClick={() => generateAnalysisPdf(data)}
              className="inline-flex items-center gap-1.5 px-2.5 py-1.5 bg-white border border-border rounded-lg text-[10px] md:text-xs font-bold text-muted hover:text-primary hover:bg-neutral-50 transition-all shadow-sm"
              title="Download Detailed PDF Report"
            >
              <Download size={11} />
              <span>Download PDF</span>
            </button>
            {data.timestamp || data.created_at ? (
              <span className="text-[10px] text-muted font-mono font-bold uppercase bg-neutral-100 px-2 py-1.5 rounded border" title="Last Analyzed Time">
                Last Analyzed: {new Date(data.timestamp || data.created_at || "").toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
              </span>
            ) : null}
            <span className="text-[10px] text-muted font-mono font-bold uppercase bg-neutral-100 px-2 py-1.5 rounded border">
              Horizon: {data.horizon || "MID"}
            </span>
            <SignalBadge signal={data.recommendation} confidence={data.confidence} className="text-xs md:text-sm px-3 py-1" />
          </div>
        </div>

        {/* Quant Table: Entry / Target / Stop Loss / RR */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center border-t border-neutral-100 pt-4">
          <div className="bg-neutral-50 p-2.5 rounded-lg border border-neutral-200/50">
            <span className="text-[10px] text-muted font-bold block uppercase tracking-wider">Entry Price</span>
            <span className="text-sm md:text-base font-bold font-mono text-primary">
              {data.entry_price ? `₹${data.entry_price.toLocaleString("en-IN")}` : "—"}
            </span>
          </div>
          <div className="bg-emerald-50/20 p-2.5 rounded-lg border border-emerald-200/40">
            <span className="text-[10px] text-muted font-bold block uppercase tracking-wider text-emerald-800">Target Price</span>
            <span className="text-sm md:text-base font-bold font-mono text-signal-buy">
              {data.target_price ? `₹${data.target_price.toLocaleString("en-IN")}` : "—"}
            </span>
          </div>
          <div className="bg-red-50/20 p-2.5 rounded-lg border border-red-200/40">
            <span className="text-[10px] text-muted font-bold block uppercase tracking-wider text-red-800">Stop Loss</span>
            <span className="text-sm md:text-base font-bold font-mono text-signal-sell">
              {data.stop_loss ? `₹${data.stop_loss.toLocaleString("en-IN")}` : "—"}
            </span>
          </div>
          <div className="bg-neutral-50 p-2.5 rounded-lg border border-neutral-200/50">
            <span className="text-[10px] text-muted font-bold block uppercase tracking-wider">Risk / Reward</span>
            <span className="text-sm md:text-base font-bold font-mono text-accent-dark">
              {data.risk_reward ? `${data.risk_reward.toFixed(1)}x` : "—"}
            </span>
          </div>
        </div>

        {/* Additional Stats: Upside %, Timeframe, Capital Size */}
        <div className="grid grid-cols-3 gap-3 border-t border-neutral-100 pt-4 text-[10px] md:text-xs">
          <div className="flex justify-between items-center bg-neutral-50 px-3 py-1.5 rounded border border-neutral-100">
            <span className="text-muted">Est. Return:</span>
            <span className="font-bold text-signal-buy font-mono">
              {data.upside_pct ? `+${data.upside_pct.toFixed(1)}%` : "—"}
            </span>
          </div>
          <div className="flex justify-between items-center bg-neutral-50 px-3 py-1.5 rounded border border-neutral-100">
            <span className="text-muted">Target Duration:</span>
            <span className="font-bold text-primary">{data.timeframe || `${data.horizon_days || 30} days`}</span>
          </div>
          <div className="flex justify-between items-center bg-neutral-50 px-3 py-1.5 rounded border border-neutral-100">
            <span className="text-muted">Position Size:</span>
            <span className="font-bold text-accent-dark font-mono">
              {data.position_size_pct ? `${data.position_size_pct}%` : "—"}
            </span>
          </div>
        </div>
      </div>

      {/* 2. REASONING ACCORDION FOR PROGRESSIVE DISCLOSURE */}
      <ReasoningAccordion data={data} />

      {/* 3. FULL SCREEN OVERLAY MODAL */}
      {isFullscreen && (
        <div className="fixed inset-0 z-[100] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 md:p-6 overflow-hidden animate-in fade-in duration-200">
          <div className="bg-cream border border-border rounded-2xl w-full max-w-6xl h-[90vh] flex flex-col shadow-2xl relative animate-in zoom-in-95 duration-200">
            {/* Modal Header */}
            <div className="flex justify-between items-center border-b border-border bg-white px-6 py-4 rounded-t-2xl">
              <div>
                <h3 className="text-base md:text-lg font-black text-primary tracking-tight">
                  Detailed Analysis: {data.symbol}
                </h3>
                <p className="text-xs text-muted font-medium mt-0.5">
                  {data.company_name || symbolName || "Indian Equity Market Asset"}
                </p>
              </div>

              <div className="flex items-center gap-3">
                {onAnalyseClick && !isNotAnalysed && (
                  <button
                    type="button"
                    disabled={isAnalysing}
                    onClick={onAnalyseClick}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-accent hover:bg-accent-dark text-white rounded-lg text-xs font-bold transition-all disabled:opacity-50 shadow-sm border border-accent/20"
                    title="Run F2 Analysis Specialists Again"
                  >
                    {isAnalysing ? (
                      <>
                        <Spinner size="sm" className="border-t-transparent border-white w-3.5 h-3.5" />
                        <span>Analysing...</span>
                      </>
                    ) : (
                      <>
                        <RefreshCw size={12} />
                        <span>Re-Analyse Stock</span>
                      </>
                    )}
                  </button>
                )}
                {data.timestamp || data.created_at ? (
                  <span className="text-[10px] text-muted font-mono font-bold uppercase bg-neutral-100 px-2.5 py-1 rounded border" title="Last Analyzed Time">
                    Last Analyzed: {new Date(data.timestamp || data.created_at || "").toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                  </span>
                ) : null}
                <span className="text-[10px] text-muted font-mono font-bold uppercase bg-neutral-100 px-2.5 py-1 rounded border">
                  Horizon: {data.horizon || "MID"}
                </span>
                <SignalBadge signal={data.recommendation} confidence={data.confidence} className="text-xs md:text-sm px-3 py-1" />

                <button
                  type="button"
                  onClick={() => generateAnalysisPdf(data)}
                  className="p-1.5 text-muted hover:text-primary hover:bg-neutral-100 rounded-lg transition-colors border border-border ml-2"
                  title="Download PDF"
                >
                  <Download size={18} />
                </button>

                <button
                  type="button"
                  onClick={() => setIsFullscreen(false)}
                  className="p-1.5 text-muted hover:text-primary hover:bg-neutral-100 rounded-lg transition-colors border border-border"
                  title="Close Full Screen View"
                >
                  <X size={18} />
                </button>
              </div>
            </div>

            {/* Modal Content Scroll Body */}
            <div className="flex-1 overflow-y-auto p-6 space-y-5 scrollbar-thin">
              {/* 1. KEY QUANT PARAMETERS SUMMARY */}
              <div className="bg-white border border-border rounded-xl p-5 md:p-6 shadow-sm space-y-5">
                {/* Quant Table: Entry / Target / Stop Loss / RR */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-center">
                  <div className="bg-neutral-50 p-3.5 rounded-lg border border-neutral-200/50">
                    <span className="text-[10px] md:text-xs text-muted font-bold block uppercase tracking-wider">Entry Price</span>
                    <span className="text-base md:text-lg font-bold font-mono text-primary mt-1 block">
                      {data.entry_price ? `₹${data.entry_price.toLocaleString("en-IN")}` : "—"}
                    </span>
                  </div>
                  <div className="bg-emerald-50/20 p-3.5 rounded-lg border border-emerald-200/40">
                    <span className="text-[10px] md:text-xs text-muted font-bold block uppercase tracking-wider text-emerald-800">Target Price</span>
                    <span className="text-base md:text-lg font-bold font-mono text-signal-buy mt-1 block">
                      {data.target_price ? `₹${data.target_price.toLocaleString("en-IN")}` : "—"}
                    </span>
                  </div>
                  <div className="bg-red-50/20 p-3.5 rounded-lg border border-red-200/40">
                    <span className="text-[10px] md:text-xs text-muted font-bold block uppercase tracking-wider text-red-800">Stop Loss</span>
                    <span className="text-base md:text-lg font-bold font-mono text-signal-sell mt-1 block">
                      {data.stop_loss ? `₹${data.stop_loss.toLocaleString("en-IN")}` : "—"}
                    </span>
                  </div>
                  <div className="bg-neutral-50 p-3.5 rounded-lg border border-neutral-200/50">
                    <span className="text-[10px] md:text-xs text-muted font-bold block uppercase tracking-wider">Risk / Reward</span>
                    <span className="text-base md:text-lg font-bold font-mono text-accent-dark mt-1 block">
                      {data.risk_reward ? `${data.risk_reward.toFixed(1)}x` : "—"}
                    </span>
                  </div>
                </div>

                {/* Additional Stats: Upside %, Timeframe, Capital Size */}
                <div className="grid grid-cols-3 gap-4 border-t border-neutral-100 pt-4 text-xs md:text-sm">
                  <div className="flex justify-between items-center bg-neutral-50 px-4 py-2 rounded border border-neutral-100">
                    <span className="text-muted">Est. Return:</span>
                    <span className="font-bold text-signal-buy font-mono">
                      {data.upside_pct ? `+${data.upside_pct.toFixed(1)}%` : "—"}
                    </span>
                  </div>
                  <div className="flex justify-between items-center bg-neutral-50 px-4 py-2 rounded border border-neutral-100">
                    <span className="text-muted">Target Duration:</span>
                    <span className="font-bold text-primary">{data.timeframe || `${data.horizon_days || 30} days`}</span>
                  </div>
                  <div className="flex justify-between items-center bg-neutral-50 px-4 py-2 rounded border border-neutral-100">
                    <span className="text-muted">Position Size:</span>
                    <span className="font-bold text-accent-dark font-mono">
                      {data.position_size_pct ? `${data.position_size_pct}%` : "—"}
                    </span>
                  </div>
                </div>
              </div>

              {/* 2. REASONING ACCORDION FOR PROGRESSIVE DISCLOSURE */}
              <ReasoningAccordion data={data} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
