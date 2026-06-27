import { useState } from "react";
import type { DiscoveredStock, Signal } from "../../types";
import { StockRow } from "./StockRow";
import { Search, FolderOpen, SlidersHorizontal, Target, TrendingUp, CheckCircle2, ArrowUpDown, ChevronDown, Check } from "lucide-react";

interface CustomDropdownProps {
  value: string;
  options: { label: string; value: string }[];
  onChange: (value: string) => void;
}

function CustomDropdown({ value, options, onChange }: CustomDropdownProps) {
  const [isOpen, setIsOpen] = useState(false);
  const selectedLabel = options.find(o => o.value === value)?.label || value;

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between px-4 py-2.5 bg-white hover:bg-neutral-50 border border-border rounded-xl focus:outline-none focus:border-navy focus:ring-2 focus:ring-navy/10 transition-all text-sm font-bold text-primary shadow-sm"
      >
        <span className="truncate">{selectedLabel}</span>
        <ChevronDown size={16} className={`text-muted transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isOpen && (
        <>
          <div 
            className="fixed inset-0 z-40" 
            onClick={() => setIsOpen(false)}
          />
          <div className="absolute top-full left-0 right-0 mt-2 bg-white border border-border rounded-xl shadow-xl z-50 overflow-hidden animate-in fade-in slide-in-from-top-2 duration-200">
            {options.map((opt) => (
              <button
                key={opt.value}
                onClick={() => {
                  onChange(opt.value);
                  setIsOpen(false);
                }}
                className={`w-full flex items-center justify-between px-4 py-3 hover:bg-neutral-50 transition-colors border-b border-neutral-100 last:border-0 ${value === opt.value ? 'bg-navy/5 text-navy' : 'text-primary'}`}
              >
                <span className={`text-sm font-bold ${value === opt.value ? 'text-navy' : ''}`}>
                  {opt.label}
                </span>
                {value === opt.value && <Check size={14} className="text-navy" />}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

interface StockListProps {
  stocks: DiscoveredStock[];
  selectedSymbol: string | null;
  onSelect: (symbol: string) => void;
  dispatchState?: Record<string, any>;
}

export function StockList({ stocks, selectedSymbol, onSelect, dispatchState = {} }: StockListProps) {
  const [filterText, setFilterText] = useState("");
  const [minConfidence, setMinConfidence] = useState<number>(0);
  const [sortBy, setSortBy] = useState<"rank" | "return">("rank");
  const [signalFilter, setSignalFilter] = useState<"ALL" | "BUY" | "SELL" | "HOLD" | "WAIT">("ALL");
  const [analysisFilter, setAnalysisFilter] = useState<"ALL" | "ANALYSED" | "NOT_ANALYSED">("ALL");
  const [showFilters, setShowFilters] = useState(false);

  const activeFiltersCount = 
    (minConfidence > 0 ? 1 : 0) + 
    (signalFilter !== "ALL" ? 1 : 0) + 
    (analysisFilter !== "ALL" ? 1 : 0);

  const filteredStocks = stocks.filter((stock) => {
    const matchesText =
      stock.symbol.toLowerCase().includes(filterText.toLowerCase().trim()) ||
      (stock.sector && stock.sector.toLowerCase().includes(filterText.toLowerCase().trim()));
    
    // Normalize confidence to 0-100 scale
    const conf = stock.confidence ?? 0;
    const normalizedConf = conf > 1 ? conf : conf * 100;
    const normalizedMinConf = minConfidence * 100;
    const isHighConf = stock.confidence === undefined ? true : normalizedConf >= normalizedMinConf;
    
    const analysisState = dispatchState[stock.symbol];
    const signal: Signal = analysisState?.recommendation || (stock as any).recommendation || "WAIT";
    const isAnalysed = 
      analysisState?.status === "done" || 
      !!analysisState?.full_response || 
      !!(stock as any).recommendation_id;

    const matchesSignal = signalFilter === "ALL" || signal === signalFilter;
    const matchesAnalysis = 
      analysisFilter === "ALL" || 
      (analysisFilter === "ANALYSED" && isAnalysed) || 
      (analysisFilter === "NOT_ANALYSED" && !isAnalysed);

    return matchesText && isHighConf && matchesSignal && matchesAnalysis;
  });

  const sortedStocks = [...filteredStocks].sort((a, b) => {
    if (sortBy === "rank") {
      return (a.rank ?? 9999) - (b.rank ?? 9999);
    } else {
      // sort by expected_return_pct or change_pct descending
      const aReturn = a.expected_return_pct ?? a.change_pct ?? -9999;
      const bReturn = b.expected_return_pct ?? b.change_pct ?? -9999;
      return bReturn - aReturn;
    }
  });

  return (
    <div className="space-y-4 flex flex-col h-full">
      {/* Controls Bar */}
      {stocks.length > 0 && (
        <div className="flex flex-col gap-3 bg-neutral-50/50 p-3 rounded-xl border border-border">
          <div className="flex flex-row gap-3 items-center justify-between">
            {/* Search */}
            <div className="relative w-full sm:w-64 shrink-0">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
              <input
                type="text"
                placeholder="Search symbol or sector..."
                value={filterText}
                onChange={(e) => setFilterText(e.target.value)}
                className="w-full text-sm pl-9 pr-3 py-2 bg-white border border-border rounded-lg focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/20 transition-all font-medium text-primary shadow-sm"
              />
            </div>

            {/* Toggle Filters Button */}
            <button
              onClick={() => setShowFilters(!showFilters)}
              className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-bold transition-all relative ${
                showFilters 
                  ? "bg-navy text-white shadow-sm" 
                  : "bg-white border border-border text-primary hover:bg-neutral-50 shadow-sm"
              }`}
            >
              <SlidersHorizontal size={14} />
              <span className="hidden sm:inline">Filters & Sort</span>
              {activeFiltersCount > 0 && !showFilters && (
                <span className="absolute -top-1.5 -right-1.5 flex h-4 w-4 items-center justify-center rounded-full bg-accent text-[9px] text-white">
                  {activeFiltersCount}
                </span>
              )}
            </button>
          </div>

          {/* Expandable Filters Area */}
          {showFilters && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5 w-full pt-5 mt-2 border-t border-border/50 animate-in slide-in-from-top-2 duration-200">
              
              {/* Filter by Confidence */}
              <div className="flex flex-col gap-2">
                <div className="flex justify-between items-center w-full">
                  <span className="text-[10px] font-bold text-muted uppercase tracking-wider flex items-center gap-1.5">
                    <Target size={12} /> Confidence Level
                  </span>
                  <span className="text-xs font-black text-navy px-1.5 py-0.5 bg-navy/5 rounded border border-navy/10">
                    {minConfidence === 0 ? "All" : `>${minConfidence * 100}%`}
                  </span>
                </div>
                <div className="relative pt-2 pb-1 flex items-center h-[42px]">
                  <input 
                    type="range" 
                    min="0" 
                    max="1" 
                    step="0.05" 
                    value={minConfidence} 
                    onChange={(e) => setMinConfidence(parseFloat(e.target.value))}
                    className="w-full h-2 bg-neutral-200 rounded-full appearance-none cursor-pointer accent-navy hover:accent-navy/80 focus:outline-none focus:ring-2 focus:ring-navy/20 transition-all shadow-inner"
                  />
                </div>
              </div>

              {/* Filter by Signal */}
              <div className="flex flex-col gap-2">
                <span className="text-[10px] font-bold text-muted uppercase tracking-wider flex items-center gap-1.5">
                  <TrendingUp size={12} /> Trading Signal
                </span>
                <CustomDropdown
                  value={signalFilter}
                  onChange={(val) => setSignalFilter(val as any)}
                  options={[
                    { label: "All Signals", value: "ALL" },
                    { label: "Buy", value: "BUY" },
                    { label: "Wait", value: "WAIT" },
                    { label: "Sell", value: "SELL" },
                  ]}
                />
              </div>

              {/* Filter by Status */}
              <div className="flex flex-col gap-2">
                <span className="text-[10px] font-bold text-muted uppercase tracking-wider flex items-center gap-1.5">
                  <CheckCircle2 size={12} /> Analysis Status
                </span>
                <CustomDropdown
                  value={analysisFilter}
                  onChange={(val) => setAnalysisFilter(val as any)}
                  options={[
                    { label: "All Statuses", value: "ALL" },
                    { label: "Analysed", value: "ANALYSED" },
                    { label: "Pending", value: "NOT_ANALYSED" },
                  ]}
                />
              </div>

              {/* Sort By */}
              <div className="flex flex-col gap-2">
                <span className="text-[10px] font-bold text-muted uppercase tracking-wider flex items-center gap-1.5">
                  <ArrowUpDown size={12} /> Sort Results By
                </span>
                <CustomDropdown
                  value={sortBy}
                  onChange={(val) => setSortBy(val as any)}
                  options={[
                    { label: "Rank (Default)", value: "rank" },
                    { label: "Expected Return %", value: "return" },
                  ]}
                />
              </div>
            </div>
          )}
        </div>
      )}

      {/* Stock Cards Grid */}
    <div className="overflow-y-auto flex-1 min-h-[500px] scrollbar-thin select-none pb-10">
        {sortedStocks.length > 0 ? (
          <div className="flex flex-col gap-3">
            {sortedStocks.map((stock) => (
              <StockRow
                key={stock.symbol}
                stock={stock}
                isSelected={selectedSymbol === stock.symbol}
                onClick={() => onSelect(stock.symbol)}
                analysisState={dispatchState[stock.symbol]}
              />
            ))}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-20 px-4 bg-white/50 border border-dashed border-border rounded-xl text-center">
            <FolderOpen size={40} className="text-muted opacity-40 mb-3" />
            <p className="text-sm font-semibold text-primary">
              {stocks.length === 0 ? "No stocks in this horizon bucket today." : "No stocks matching your filters."}
            </p>
            {stocks.length > 0 && (
              <button
                onClick={() => { 
                  setFilterText(""); 
                  setMinConfidence(0); 
                  setSignalFilter("ALL"); 
                  setAnalysisFilter("ALL"); 
                }}
                className="text-sm text-accent hover:underline mt-2 font-bold"
              >
                Clear all filters
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

