import { useState, useRef, useEffect, useCallback } from "react";
import { useSymbolSearch } from "../hooks/useSymbolSearch";
import { apiService } from "../services/api";
import { useIdempotentAction } from "../hooks/useIdempotentAction";
import { StockDetail } from "../components/analysis/StockDetail";
import { Spinner } from "../components/shared/Spinner";
import type { AnalyzeResponse, Horizon } from "../types";
import { Search, X, Loader2, Microscope, Play, ChevronDown } from "lucide-react";

const HORIZONS: { value: Horizon; label: string; desc: string }[] = [
  { value: "SHORT", label: "Short Term", desc: "1-2 weeks · Technical focus" },
  { value: "MID", label: "Mid Term", desc: "4-6 weeks · Balanced approach" },
  { value: "LONG", label: "Long Term", desc: "3+ months · Value compounding" },
];

export function Analyse() {
  // Search
  const [searchQuery, setSearchQuery] = useState("");
  const [showDropdown, setShowDropdown] = useState(false);
  const { data: suggestions, isLoading: isSearching } = useSymbolSearch(searchQuery);

  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown on click outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setShowDropdown(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Selected stock
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [selectedHorizon, setSelectedHorizon] = useState<Horizon>("MID");

  // Analysis state
  const [analysisResult, setAnalysisResult] = useState<AnalyzeResponse | null>(null);
  const [analyseError, setAnalyseError] = useState<string | null>(null);

  const handleSelectSymbol = (symbol: string) => {
    setSelectedSymbol(symbol.toUpperCase());
    setSearchQuery(symbol.toUpperCase());
    setShowDropdown(false);
    setAnalyseError(null);
  };

  const handleClear = () => {
    setSearchQuery("");
    setShowDropdown(false);
  };

  // Synchronize with URL search query parameter
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const searchSym = params.get("search");
    if (searchSym) {
      const sym = searchSym.toUpperCase();
      handleSelectSymbol(sym);
      
      // Auto-run analysis when navigated with a symbol
      // Use a microtask to ensure handleRunAnalysis is stable after state updates
      setTimeout(() => {
        handleRunAnalysis();
      }, 0);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const _runAnalysis = useCallback(async () => {
    if (!selectedSymbol) return;
    setAnalyseError(null);

    try {
      const result = await apiService.analyzeStock(selectedSymbol, selectedHorizon);
      setAnalysisResult(result);
    } catch (err: any) {
      if (!err.isDuplicate) {
        const detail =
          err?.response?.data?.detail || err?.message || "Analysis failed. Please try again.";
        setAnalyseError(detail);
      }
    }
  }, [selectedSymbol, selectedHorizon]);
  const [handleRunAnalysis, isAnalysing] = useIdempotentAction(_runAnalysis);

  return (
    <div className="space-y-5 animate-in fade-in duration-200">

      {/* HEADER */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 bg-white border border-border rounded-xl p-4 shadow-sm">
        <div className="flex items-center gap-2">
          <div className="p-2 bg-accent/10 rounded-lg text-accent border border-accent/20">
            <Microscope size={20} className="text-accent" />
          </div>
          <div>
            <h2 className="text-base md:text-lg font-black text-primary tracking-tight">Stock Analyser</h2>
            <p className="text-xs text-muted font-medium">Search any NSE/BSE equity and run a full multi-agent deep analysis.</p>
          </div>
        </div>
      </div>

      {/* SEARCH + CONTROLS */}
      <div className="bg-white border border-border rounded-xl p-4 sm:p-5 shadow-sm space-y-4">

        {/* Search Bar */}
        <div className="space-y-1.5">
          <label className="text-xs font-bold text-muted uppercase tracking-wider">Symbol Search</label>
          <div ref={dropdownRef} className="relative">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
            <input
              type="text"
              placeholder="Search equity symbol (e.g. RELIANCE, INFY, TCS)..."
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setShowDropdown(true);
              }}
              onFocus={() => setShowDropdown(true)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && searchQuery.trim()) {
                  if (suggestions && suggestions.length > 0) {
                    handleSelectSymbol(suggestions[0].symbol);
                  } else {
                    handleSelectSymbol(searchQuery.trim());
                  }
                }
              }}
              className="w-full text-sm pl-10 pr-10 py-3 border border-border rounded-xl focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 transition-all font-semibold text-primary font-mono placeholder:font-sans uppercase"
            />
            {searchQuery && (
              <button
                onClick={handleClear}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-primary transition-colors"
              >
                <X size={16} />
              </button>
            )}
            {isSearching && (
              <div className="absolute right-10 top-1/2 -translate-y-1/2">
                <Loader2 size={14} className="animate-spin text-accent" />
              </div>
            )}

            {/* Dropdown */}
            {showDropdown && searchQuery.trim().length > 0 && (
              <div className="absolute left-0 right-0 top-full mt-1.5 bg-card border border-border shadow-xl rounded-lg overflow-hidden z-50 animate-in fade-in slide-in-from-top-1 duration-150 max-h-56 overflow-y-auto font-mono">
                {suggestions && suggestions.length > 0 ? (
                  <ul className="py-1">
                    {suggestions.map((item, idx) => (
                      <li key={idx}>
                        <button
                          type="button"
                          onClick={() => handleSelectSymbol(item.symbol)}
                          className="w-full text-left px-4 py-2.5 hover:bg-accent-soft hover:text-accent-dark transition-colors flex justify-between items-center text-xs md:text-sm font-bold"
                        >
                          <span className="text-primary">{item.symbol}</span>
                          <span className="text-[10px] md:text-xs text-muted font-sans font-medium truncate ml-3 max-w-[200px]">
                            {item.name}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : !isSearching ? (
                  <div className="px-4 py-3 text-xs text-muted text-center font-sans">
                    No matches. Press <strong className="font-mono bg-neutral-100 px-1 rounded text-primary">Enter</strong> to use this symbol.
                  </div>
                ) : null}
              </div>
            )}
          </div>
        </div>

        {/* Horizon Selector + Run Button */}
        {selectedSymbol && (
          <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-end pt-2 border-t border-neutral-100 animate-in fade-in slide-in-from-top-1 duration-200">
            {/* Horizon Pills */}
            <div className="flex-1 space-y-1.5">
              <label className="text-xs font-bold text-muted uppercase tracking-wider flex items-center gap-1.5">
                <ChevronDown size={12} />
                Investment Horizon
              </label>
              <div className="flex gap-2">
                {HORIZONS.map((h) => (
                  <button
                    key={h.value}
                    type="button"
                    onClick={() => setSelectedHorizon(h.value)}
                    className={`flex-1 px-3 py-2.5 rounded-lg border text-xs font-bold transition-all ${
                      selectedHorizon === h.value
                        ? "bg-navy text-white border-navy shadow-md shadow-navy/20"
                        : "bg-neutral-50 text-muted border-border hover:border-navy/40 hover:text-primary"
                    }`}
                  >
                    <span className="block">{h.label}</span>
                    <span className={`block text-[9px] mt-0.5 font-medium ${
                      selectedHorizon === h.value ? "text-white/70" : "text-muted/60"
                    }`}>
                      {h.desc}
                    </span>
                  </button>
                ))}
              </div>
            </div>

            {/* Run CTA */}
            <button
              type="button"
              onClick={handleRunAnalysis}
              disabled={isAnalysing}
              className="inline-flex items-center gap-2 px-6 py-3 bg-navy hover:bg-navy-light text-white font-bold text-sm rounded-xl shadow-lg shadow-navy/20 hover:shadow-navy/30 transition-all disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
            >
              {isAnalysing ? (
                <>
                  <Spinner size="sm" className="text-white" />
                  <span>Analysing...</span>
                </>
              ) : (
                <>
                  <Play size={16} />
                  <span>Analyse {selectedSymbol}</span>
                </>
              )}
            </button>
          </div>
        )}
      </div>

      {/* ERROR BANNER */}
      {analyseError && (
        <div className="bg-red-50 border border-red-200 text-red-800 text-xs font-semibold px-4 py-3 rounded-xl animate-in fade-in slide-in-from-top-1 duration-150">
          <strong>Analysis Error:</strong> {analyseError}
        </div>
      )}

      {/* ANALYSIS IN PROGRESS */}
      {isAnalysing && (
        <div className="flex flex-col items-center justify-center py-16 bg-white border border-border rounded-xl shadow-sm text-center animate-in fade-in duration-200">
          <Spinner size="lg" className="mb-4" />
          <h4 className="text-sm font-bold text-primary">Running Full Multi-Agent Analysis</h4>
          <p className="text-xs text-muted mt-1.5 max-w-[340px]">
            Deploying technical, fundamental, sentiment, and chart-pattern specialists for <strong className="font-mono text-accent-dark">{selectedSymbol}</strong>.
            This typically takes 20-40 seconds.
          </p>
          <div className="flex gap-2 mt-4">
            {["Technical", "Fundamental", "Sentiment", "Chart Pattern"].map((agent, i) => (
              <span
                key={agent}
                className="text-[9px] font-bold uppercase bg-accent/10 text-accent-dark px-2 py-1 rounded-full border border-accent/20 animate-pulse"
                style={{ animationDelay: `${i * 200}ms` }}
              >
                {agent}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* RESULT DISPLAY */}
      {!isAnalysing && analysisResult && (
        <div className="animate-in fade-in slide-in-from-bottom-2 duration-300">
          <StockDetail
            data={analysisResult}
            isLoading={false}
            onAnalyseClick={handleRunAnalysis}
            isAnalysing={isAnalysing}
            symbolName={selectedSymbol}
          />
        </div>
      )}

      {/* EMPTY STATE — no symbol selected yet */}
      {!selectedSymbol && !analysisResult && !isAnalysing && (
        <div className="flex flex-col items-center justify-center py-20 bg-white/50 border border-dashed border-border rounded-xl text-center select-none">
          <Microscope size={44} className="text-muted/25 mb-3" />
          <h4 className="text-sm font-bold text-primary">Search & Analyse Any Stock</h4>
          <p className="text-xs text-muted mt-1 max-w-[320px]">
            Type a symbol above to search the NSE/BSE universe. Select a stock and horizon, then click Analyse to deploy the full AI specialist pipeline.
          </p>
        </div>
      )}
    </div>
  );
}
