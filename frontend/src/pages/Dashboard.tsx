import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiService } from "../services/api";
import { Spinner } from "../components/shared/Spinner";
import { ChevronLeft, ChevronRight, Search, X, TrendingUp, TrendingDown, BarChart3, Activity } from "lucide-react";

// Format an RSS `published` string into a compact, human-readable label.
// RSS dates are RFC-822 GMT (e.g. "Tue, 09 Jun 2026 10:49:27 GMT") which Date
// parses natively — the old "+ Z" hack mangled them. Shows relative time for
// recent items ("2h ago"), an absolute date otherwise ("Jun 5"), so a fresh
// headline and a 4-day-old one are no longer both shown as just a clock time.
function formatNewsDate(published: string | undefined): string {
  if (!published) return "";
  const d = new Date(published);
  if (isNaN(d.getTime())) return published;
  const diffMs = Date.now() - d.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay < 7) return `${diffDay}d ago`;
  const sameYear = d.getFullYear() === new Date().getFullYear();
  return d.toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    ...(sameYear ? {} : { year: "numeric" }),
  });
}

// Simple seeded PRNG to generate deterministic sparklines per symbol
function seededRandom(seed: string) {
  let hash = 0;
  for (let i = 0; i < seed.length; i++) {
    const char = seed.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash |= 0;
  }
  return function () {
    hash = (hash * 16807) % 2147483647;
    return (hash & 0x7fffffff) / 0x7fffffff;
  };
}

// SVG sparkline component — deterministic per-symbol seed, no random flicker
const MiniSparkline = ({ seed, isUp, width = 72, height = 36 }: { seed: string; isUp: boolean; width?: number; height?: number }) => {
  const color = isUp ? "#16a34a" : "#dc2626";

  const points = useMemo(() => {
    const rng = seededRandom(seed);
    const pts = Array.from({ length: 15 }, (_, i) => {
      const x = (i / 14) * width;
      const y = height - (rng() * (height * 0.8) + (height * 0.1));
      return `${x},${y}`;
    });
    // Force start/end to make it look like a trend
    if (isUp) {
      pts[0] = `0,${height - 4}`;
      pts[14] = `${width},4`;
    } else {
      pts[0] = `0,4`;
      pts[14] = `${width},${height - 4}`;
    }
    return pts;
  }, [seed, isUp, width, height]);

  const pathD = "M" + points.join(" L");
  const areaD = pathD + ` L${width},${height} L0,${height} Z`;

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} style={{ overflow: "visible" }}>
      <defs>
        <linearGradient id={`sg-${seed}-${isUp ? 'up' : 'down'}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.25" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={areaD} fill={`url(#sg-${seed}-${isUp ? 'up' : 'down'})`} />
      <path d={pathD} stroke={color} strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
};

export function Dashboard() {
  const [currentPage, setCurrentPage] = useState(1);
  const [selectedCategory, setSelectedCategory] = useState("All");
  const [newsSearchQuery, setNewsSearchQuery] = useState("");
  const itemsPerPage = 5;

  const { data, isLoading, isError, error, refetch, dataUpdatedAt, isFetching } = useQuery({
    queryKey: ["marketDashboard"],
    queryFn: () => apiService.getMarketDashboard(),
    refetchInterval: 60000,
  });

  const { data: newsData, isLoading: isNewsLoading } = useQuery({
    queryKey: ["marketNews", selectedCategory, newsSearchQuery, currentPage, itemsPerPage],
    queryFn: () => apiService.getMarketNews(selectedCategory, newsSearchQuery, currentPage, itemsPerPage),
    refetchInterval: 60000,
  });

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center h-[50dvh] text-muted space-y-4">
        <Spinner size="lg" />
        <p className="text-xs font-bold text-primary animate-pulse tracking-wide uppercase">Loading Market Dashboard...</p>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="bg-red-50 p-6 rounded-xl border border-red-200 text-center">
        <h3 className="text-red-800 font-bold mb-2">Failed to load market dashboard</h3>
        <p className="text-red-600/80 text-sm">{(error as any)?.message}</p>
      </div>
    );
  }

  // Derive market summary stats from live index data
  const indices = data?.indices || [];
  const validIndices = indices.filter((idx) => !idx.error);
  const gainers = validIndices.filter((idx) => idx.change >= 0).length;
  const decliners = validIndices.length - gainers;
  const avgChangePct = validIndices.length > 0
    ? validIndices.reduce((sum, idx) => sum + idx.change_pct, 0) / validIndices.length
    : 0;

  // Dynamic news category extraction (from dashboard summary)
  const categories = ["All", ...Array.from(new Set(data?.news?.map((n) => n.category) || []))];

  // News Pagination logic (now server-side)
  const totalItems = newsData?.count || 0;
  const totalPages = newsData?.total_pages || 1;
  const paginatedNews = newsData?.items || [];

  const handleCategoryChange = (cat: string) => {
    setSelectedCategory(cat);
    setCurrentPage(1);
  };

  const handleSearchChange = (val: string) => {
    setNewsSearchQuery(val);
    setCurrentPage(1);
  };

  return (
    <div className="space-y-5 animate-in fade-in duration-200 select-none pb-8">
      
      {/* ── Market Overview Summary ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 bg-white rounded-xl border border-border overflow-hidden shadow-sm">
        {[
          {
            label: "Indices Tracked",
            value: validIndices.length.toString(),
            sub: `${indices.length} total configured`,
            icon: BarChart3,
            valColor: "text-primary",
            subColor: "text-muted",
          },
          {
            label: "Market Breadth",
            value: (
              <>
                <span className="text-signal-buy">{gainers}↑</span> <span className="text-muted">/</span> <span className="text-[#B85A10]">{decliners}↓</span>
              </>
            ),
            sub: gainers > decliners ? "Bullish breadth" : gainers < decliners ? "Bearish breadth" : "Neutral",
            icon: Activity,
            valColor: "",
            subColor: gainers >= decliners ? "text-signal-buy" : "text-signal-sell",
          },
          {
            label: "Avg Change",
            value: `${avgChangePct >= 0 ? "+" : ""}${avgChangePct.toFixed(2)}%`,
            sub: "Across all indices",
            icon: avgChangePct >= 0 ? TrendingUp : TrendingDown,
            valColor: avgChangePct >= 0 ? "text-signal-buy" : "text-signal-sell",
            subColor: "text-muted",
          },
          {
            label: "News Articles",
            value: totalItems.toString(),
            sub: `${categories.length - 1} categories`,
            icon: Search,
            valColor: "text-navy",
            subColor: "text-muted",
          },
        ].map((s, i) => {
          const Icon = s.icon;
          return (
            <div key={i} className="p-4 md:border-r border-b md:border-b-0 border-border last:border-0 bg-white">
              <div className="flex items-center gap-1.5 mb-1.5">
                <Icon size={12} className="text-muted" />
                <div className="text-[10px] text-muted font-semibold uppercase tracking-wider">{s.label}</div>
              </div>
              <div className={`font-mono font-black text-xl leading-none mb-1 ${s.valColor}`}>{s.value}</div>
              <div className={`text-[11px] font-medium ${s.subColor}`}>{s.sub}</div>
            </div>
          );
        })}
      </div>

      {/* ── Market Indices ── */}
      <div>
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-3 gap-2">
          <div className="text-[11px] font-bold text-muted uppercase tracking-wider flex items-center gap-2">
            <span>📊 Market Indices</span>
          </div>
          <div className="flex items-center gap-3">
            {dataUpdatedAt > 0 && (
              <span className="text-[10px] font-bold text-muted flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-signal-buy animate-pulse" />
                Latest: {new Date(dataUpdatedAt).toLocaleTimeString()}
              </span>
            )}
            <button
              onClick={() => refetch()}
              disabled={isFetching}
              className="px-3 py-1 bg-white border border-border text-primary rounded-lg text-[10px] font-bold shadow-sm hover:bg-neutral-50 transition-colors disabled:opacity-50 flex items-center gap-1.5"
            >
              {isFetching ? <Spinner size="sm" /> : null}
              Refresh
            </button>
          </div>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {indices.map((idx) => {
            const isUp = idx.change >= 0;
            const isError = !!idx.error;
            let prefix = "";
            let suffix = "";
            const n = idx.name.toUpperCase();
            if (n.includes("GOLD")) { prefix = "₹"; suffix = " / g"; }
            else if (n.includes("CRUDE OIL")) { prefix = "$"; suffix = " / bbl"; }
            else if (n.includes("S&P 500") || n.includes("NASDAQ") || n.includes("DOW JONES")) prefix = "$";
            else if (n.includes("FTSE")) prefix = "£";
            else if (n.includes("NIKKEI")) prefix = "¥";
            else if (n.includes("HANG SENG")) prefix = "HK$";
            else if (n.includes("NIFTY") || n.includes("SENSEX")) prefix = "₹";

            return (
              <div key={idx.symbol} className="bg-white rounded-xl border border-border p-3 shadow-sm flex justify-between items-center gap-2">
                <div>
                  <div className="text-[11px] text-muted font-medium mb-1 truncate">{idx.name}</div>
                  {isError ? (
                    <div className="text-xs text-muted/60 italic">Unavailable</div>
                  ) : (
                    <>
                      <div className="font-mono font-bold text-base text-primary leading-tight">
                        {prefix}{idx.price.toLocaleString("en-IN", { minimumFractionDigits: 2 })}{suffix}
                      </div>
                      <div className={`text-[11px] font-bold mt-1 flex items-center gap-1 ${isUp ? "text-signal-buy" : "text-signal-sell"}`}>
                        {isUp ? "+" : ""}{idx.change_pct.toFixed(2)}%
                      </div>
                    </>
                  )}
                </div>
                {!isError && <MiniSparkline seed={idx.symbol} isUp={isUp} width={60} height={30} />}
              </div>
            );
          })}
        </div>
      </div>

      {/* ── News Feed (full width) ── */}
      <div className="space-y-3 flex flex-col h-full">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-white border border-border p-4 rounded-xl shadow-sm">
          <div className="flex items-center justify-between sm:justify-start gap-3">
            <div className="font-extrabold text-[14px] text-primary tracking-tight uppercase">Market Feed</div>
            <div className="text-[10px] text-accent-dark font-black bg-accent/10 px-2 py-0.5 rounded border border-accent/20 flex items-center gap-1">
              <span className="w-1 h-1 rounded-full bg-accent animate-pulse" />
              Live
            </div>
          </div>
          
          {/* Search Input Bar */}
          <div className="relative w-full sm:w-48">
            <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted" />
            <input
              type="text"
              placeholder="Search market news..."
              value={newsSearchQuery}
              onChange={(e) => handleSearchChange(e.target.value)}
              className="w-full text-[11px] font-semibold pl-8 pr-7 py-1.5 border border-border rounded-lg focus:outline-none focus:border-accent bg-neutral-50/50 focus:bg-white transition-all text-primary"
            />
            {newsSearchQuery && (
              <button
                onClick={() => handleSearchChange("")}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted hover:text-primary p-0.5 rounded-md hover:bg-neutral-100"
              >
                <X size={11} />
              </button>
            )}
          </div>
        </div>

        {/* Dynamic Categories Scrollbar */}
        {categories.length > 1 && (
          <div className="overflow-x-auto flex gap-1.5 pb-1 scrollbar-none whitespace-nowrap">
            {categories.map((cat) => {
              const isActive = selectedCategory === cat;
              return (
                <button
                  key={cat}
                  onClick={() => handleCategoryChange(cat)}
                  className={`px-3 py-1 rounded-full text-[10px] font-black tracking-wide border uppercase transition-all ${
                    isActive
                      ? "bg-navy border-navy text-white shadow-sm"
                      : "bg-white border-border text-muted hover:text-primary hover:border-navy/40"
                  }`}
                >
                  {cat}
                </button>
              );
            })}
          </div>
        )}

        {/* Paginated Feed List */}
        <div className="flex-1 flex flex-col gap-3 min-h-[300px]">
          {isNewsLoading ? (
            <div className="flex-1 flex flex-col items-center justify-center py-16 bg-white border border-dashed border-border rounded-xl text-center">
              <Spinner size="md" className="mb-3" />
              <p className="text-[10px] font-bold text-primary animate-pulse tracking-wider uppercase">Syncing Market Feed...</p>
            </div>
          ) : paginatedNews.length > 0 ? (
            paginatedNews.map((n, i) => (
              <a 
                key={i} 
                href={n.link} 
                target="_blank" 
                rel="noreferrer" 
                className="group block bg-white rounded-xl border-l-4 border-l-accent border-y border-r border-border p-4 shadow-sm hover:shadow-md transition-shadow animate-in fade-in slide-in-from-bottom-1 duration-150"
              >
                <div className="flex justify-between items-start gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="text-[13px] font-bold text-primary leading-snug mb-1 group-hover:text-accent-dark transition-colors line-clamp-2">
                      {n.title}
                    </div>
                    <div className="text-[11px] text-muted/80 mt-1 truncate">{n.source}</div>
                  </div>
                  <div className="flex flex-col items-end gap-1.5 shrink-0 text-right">
                    <span className="text-[9px] font-black uppercase px-2 py-0.5 rounded bg-neutral-100 text-neutral-600 border border-neutral-200/80 tracking-wider">
                      {n.category}
                    </span>
                    <span className="text-[10px] text-muted font-semibold font-mono">
                      {formatNewsDate(n.published)}
                    </span>
                  </div>
                </div>
              </a>
            ))
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center py-16 bg-white border border-dashed border-border rounded-xl text-center">
              <Search size={28} className="text-muted/30 mb-2" />
              <h5 className="text-xs font-bold text-primary">No Matching Market News</h5>
              <p className="text-[10px] text-muted mt-1 max-w-[200px]">
                Try adjusting your filters or search keywords to explore general updates.
              </p>
            </div>
          )}
        </div>

        {/* Centered Pagination Control Panel */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between border-t border-border pt-4 mt-2 text-xs font-bold text-muted bg-white border px-4 py-2.5 rounded-xl shadow-sm">
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
    </div>
  );
}
