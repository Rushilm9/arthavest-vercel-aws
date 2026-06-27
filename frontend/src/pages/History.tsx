import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { apiService } from "../services/api";
import type { AnalyzeResponse } from "../types";
import { SignalBadge } from "../components/shared/SignalBadge";
import { StockDetail } from "../components/analysis/StockDetail";
import { Search, RefreshCw, ChevronRight, ChevronLeft, FileSpreadsheet, ArrowLeft, Download, GitBranch } from "lucide-react";
import { Spinner } from "../components/shared/Spinner";
import { generateAnalysisPdf } from "../utils/generateAnalysisPdf";

export function History() {
  const navigate = useNavigate();
  const [symbolQuery, setSymbolQuery] = useState("");
  const [selectedSignal, setSelectedSignal] = useState<string>("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [limit, setLimit] = useState<number>(50);

  const [currentPage, setCurrentPage] = useState(1);

  const [selectedRecId, setSelectedRecId] = useState<string | null>(null);
  const [selectedRecData, setSelectedRecData] = useState<AnalyzeResponse | null>(null);
  const [isDetailLoading, setIsDetailLoading] = useState(false);

  // TanStack Query to fetch recommendations history
  const { data: historyData, isLoading, isError, refetch } = useQuery({
    queryKey: ["historyList", symbolQuery, selectedSignal, dateFrom, dateTo, limit, currentPage],
    queryFn: () =>
      apiService.getHistory({
        symbol: symbolQuery.trim() || undefined,
        signal: selectedSignal || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        limit: limit,
        page: currentPage,
      }),
  });

  const historyList = historyData?.recommendations || [];
  const totalPages = historyData?.total_pages || 1;

  // Fetch full analysis for drill-down when a row is clicked
  useEffect(() => {
    async function loadDetail() {
      if (!selectedRecId) {
        setSelectedRecData(null);
        return;
      }
      setIsDetailLoading(true);
      try {
        const detail = await apiService.getHistoryDetail(selectedRecId);
        setSelectedRecData(detail);
      } catch (err) {
        console.error("Failed to load historical record details", err);
      } finally {
        setIsDetailLoading(false);
      }
    }
    loadDetail();
  }, [selectedRecId]);

  return (
    <div className="space-y-5 animate-in fade-in duration-200 select-none">
      
      {/* HEADER SECTION */}
      <div className="flex justify-between items-center bg-white border border-border rounded-xl p-4 shadow-sm">
        <div className="flex items-center gap-2">
          <div className="p-2 bg-neutral-100 rounded-lg text-primary border border-border">
            <FileSpreadsheet size={20} className="text-accent" />
          </div>
          <div>
            <h2 className="text-base md:text-lg font-black text-primary tracking-tight">Recommendation History</h2>
            <p className="text-xs text-muted font-medium">Historical catalog of deployed specialist quant signals and entry triggers.</p>
          </div>
        </div>
        <button
          onClick={() => refetch()}
          className="p-2 text-muted hover:text-accent rounded-lg border hover:bg-neutral-50 transition-colors"
          title="Refresh ledger"
        >
          <RefreshCw size={15} />
        </button>
      </div>

      {/* FILTERS PANEL */}
      <div className="bg-white border border-border rounded-xl p-4 shadow-sm grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-3 items-end">
        {/* Symbol Search */}
        <div className="space-y-1">
          <label className="text-[10px] md:text-xs font-bold text-muted uppercase">Symbol</label>
          <div className="relative">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted" />
            <input
              type="text"
              placeholder="e.g. RELIANCE"
              value={symbolQuery}
              onChange={(e) => setSymbolQuery(e.target.value.toUpperCase())}
              className="w-full text-xs pl-8 pr-3 py-1.5 border border-border rounded-lg focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/25 uppercase font-medium text-primary font-mono"
            />
          </div>
        </div>

        {/* Signal Dropdown */}
        <div className="space-y-1">
          <label className="text-[10px] md:text-xs font-bold text-muted uppercase">Verdict Signal</label>
          <select
            value={selectedSignal}
            onChange={(e) => setSelectedSignal(e.target.value)}
            className="w-full text-xs px-3 py-1.5 border border-border rounded-lg focus:outline-none focus:border-accent bg-white font-medium text-primary"
          >
            <option value="">ALL SIGNALS</option>
            <option value="BUY">BUY</option>
            <option value="SELL">SELL</option>
            <option value="WAIT">WAIT</option>
          </select>
        </div>

        {/* Date From */}
        <div className="space-y-1">
          <label className="text-[10px] md:text-xs font-bold text-muted uppercase">Date From</label>
          <div className="relative">
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="w-full text-xs px-3 py-1.5 border border-border rounded-lg focus:outline-none focus:border-accent font-medium text-primary uppercase font-mono"
            />
          </div>
        </div>

        {/* Date To */}
        <div className="space-y-1">
          <label className="text-[10px] md:text-xs font-bold text-muted uppercase">Date To</label>
          <div className="relative">
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="w-full text-xs px-3 py-1.5 border border-border rounded-lg focus:outline-none focus:border-accent font-medium text-primary uppercase font-mono"
            />
          </div>
        </div>

        {/* Limits Filter */}
        <div className="space-y-1">
          <label className="text-[10px] md:text-xs font-bold text-muted uppercase">Display Limit</label>
          <select
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
            className="w-full text-xs px-3 py-1.5 border border-border rounded-lg focus:outline-none focus:border-accent bg-white font-medium text-primary font-mono"
          >
            <option value={20}>20 records</option>
            <option value={50}>50 records</option>
            <option value={100}>100 records</option>
          </select>
        </div>
      </div>

      {/* TWO-COLUMN RESULTS LAYOUT
          On narrow screens this collapses to a master→detail flow: selecting a row
          swaps the table out for the full-width audit report (with a Back button). */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">

        {/* Table list pane (7 Columns) — hidden on narrow screens once a row is picked */}
        <div className={`lg:col-span-7 bg-white border border-border rounded-xl shadow-sm overflow-hidden flex-col ${selectedRecId ? "hidden lg:flex" : "flex"}`}>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-border bg-neutral-50 font-bold text-primary">
                  <th className="p-3">Asset</th>
                  <th className="p-3">Verdict</th>
                  <th className="p-3 text-center">Horizon</th>
                  <th className="p-3 text-right">Target Metrics</th>
                  <th className="p-3 text-right">Scanned Date</th>
                  <th className="p-3 text-center">Detail</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-100">
                {isLoading ? (
                  <tr>
                    <td colSpan={6} className="p-12 text-center">
                      <Spinner size="md" className="mb-3 mx-auto" />
                      <p className="text-[10px] font-bold text-primary animate-pulse tracking-wider uppercase">Retrieving ledgers from database...</p>
                    </td>
                  </tr>
                ) : isError || !historyList || historyList.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="p-12 text-center text-muted font-semibold">
                      No historical recommendations found matching active filters.
                    </td>
                  </tr>
                ) : (
                  historyList.map((rec: AnalyzeResponse, rowIdx: number) => {
                    const isSelected = selectedRecId === rec.recommendation_id || selectedRecId === rec.id;
                    const rowId = rec.recommendation_id || rec.id || `row-${rowIdx}`;
                    return (
                      <tr
                        key={rowId}
                        onClick={() => setSelectedRecId(rowId)}
                        className={`hover:bg-neutral-50/60 cursor-pointer transition-colors ${
                          isSelected ? "bg-accent-soft/30" : ""
                        }`}
                      >
                        <td className="p-3">
                          <span className="font-bold text-primary font-mono block">{rec.symbol}</span>
                          <span className="text-[10px] text-muted truncate max-w-[120px] block">
                            {rec.company_name || rec.symbol}
                          </span>
                        </td>
                        <td className="p-3">
                          <SignalBadge signal={rec.recommendation} confidence={rec.confidence} className="scale-90 origin-left" />
                        </td>
                        <td className="p-3 text-center font-bold text-accent-dark">{rec.horizon || "MID"}</td>
                        <td className="p-3 text-right font-mono space-y-0.5">
                          <span className="block font-bold text-emerald-800">
                            {rec.target_price ? `T: ₹${rec.target_price.toLocaleString("en-IN")}` : "T: —"}
                          </span>
                          <span className="block text-[10px] text-muted font-sans font-semibold">
                            {rec.risk_reward ? `R:R ${rec.risk_reward.toFixed(1)}x` : ""}
                          </span>
                        </td>
                        <td className="p-3 text-right text-muted font-mono">
                          {(() => {
                            const dateStr = rec.created_at || rec.timestamp;
                            if (!dateStr) return "—";
                            // Ensure naive dates from backend are parsed as UTC
                            const isoStr = dateStr.includes("Z") || dateStr.includes("+") ? dateStr : `${dateStr}Z`;
                            return new Date(isoStr).toLocaleDateString("en-IN", {
                              day: "2-digit",
                              month: "short",
                              year: "numeric",
                            });
                          })()}
                        </td>
                        <td className="p-3 text-center">
                          <ChevronRight size={14} className="mx-auto text-muted" />
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination Controls */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between border-t border-border p-3 text-xs font-bold text-muted bg-white">
              <button
                type="button"
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                className="px-2.5 py-1.5 rounded-lg border border-border/80 hover:bg-neutral-50 text-primary transition-all disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1.5"
              >
                <ChevronLeft size={13} />
                <span>Previous</span>
              </button>
              <span className="font-mono text-[10px] bg-neutral-100 text-muted border px-2.5 py-1 rounded font-black">
                Page {currentPage} of {totalPages}
              </span>
              <button
                type="button"
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
                className="px-2.5 py-1.5 rounded-lg border border-border/80 hover:bg-neutral-50 text-primary transition-all disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1.5"
              >
                <span>Next</span>
                <ChevronRight size={13} />
              </button>
            </div>
          )}
        </div>

        {/* Drill down preview details pane (5 Columns) — hidden on narrow screens until a row is picked */}
        <div className={`lg:col-span-5 h-full ${selectedRecId ? "block" : "hidden lg:block"}`}>
          <div className="bg-white border border-border rounded-xl p-4 space-y-3 shadow-sm min-h-[300px]">
            <div className="pb-2 border-b border-neutral-100 flex justify-between items-center gap-2">
              <h4 className="text-xs font-black text-accent-dark uppercase tracking-wider">Historical Audit Report</h4>
              {selectedRecId && selectedRecData && (
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => generateAnalysisPdf(selectedRecData)}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1.5 bg-white border border-border rounded-lg text-xs font-bold text-muted hover:text-primary hover:bg-neutral-50 transition-all shadow-sm"
                    title="Download Report"
                  >
                    <Download size={13} />
                    <span className="hidden lg:inline">Download</span>
                  </button>
                  <button
                    onClick={() => navigate(`/audit/${selectedRecId}`)}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1.5 bg-navy text-white rounded-lg text-xs font-bold hover:opacity-90 transition-all shadow-sm"
                    title="View Decision Audit Trail"
                  >
                    <GitBranch size={13} />
                    <span className="hidden lg:inline">Audit Trail</span>
                  </button>
                  <button
                    onClick={() => {
                      setSelectedRecId(null);
                      setSelectedRecData(null);
                    }}
                    className="inline-flex items-center gap-1 text-xs text-muted hover:text-primary font-semibold shrink-0"
                  >
                    <ArrowLeft size={13} className="lg:hidden" />
                    <span className="lg:hidden">Back to ledger</span>
                    <span className="hidden lg:inline">Clear preview</span>
                  </button>
                </div>
              )}
            </div>
            <StockDetail
              data={selectedRecData}
              isLoading={isDetailLoading}
              symbolName={selectedRecData?.symbol}
            />
          </div>
        </div>

      </div>

    </div>
  );
}
