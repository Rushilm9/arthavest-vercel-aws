import { useState, useEffect } from "react";
import { useMarketContext } from "../../hooks/useMarketContext";
import { TrendingUp, BarChart2, Newspaper, Globe2, ChevronDown, ChevronUp } from "lucide-react";
import type { MarketContextResponse, Horizon } from "../../types";
import { SafeHtmlText } from "../shared/SafeHtmlText";



export function MarketContextPanel() {
  const { data: apiData, dataUpdatedAt } = useMarketContext();
  const [expandedCard, setExpandedCard] = useState<string | null>(null);
  const [showPlanner, setShowPlanner] = useState(false);

  const [lastUpdated, setLastUpdated] = useState<string>(() => {
    return sessionStorage.getItem("marketContextLastUpdated") || new Date().toISOString();
  });

  useEffect(() => {
    if (dataUpdatedAt) {
      const ts = new Date(dataUpdatedAt).toISOString();
      setLastUpdated(ts);
      sessionStorage.setItem("marketContextLastUpdated", ts);
    } else if (apiData) {
      const ts = apiData.economic?.built_at || new Date().toISOString();
      setLastUpdated(ts);
      sessionStorage.setItem("marketContextLastUpdated", ts);
    }
  }, [apiData, dataUpdatedAt]);

  // Use apiData directly if available. Only use mock if apiData is completely undefined.
  // When apiData explicitly returns null for a card, we provide a clean empty state rather than showing fake mock data.
  if (!apiData) {
    return (
      <div className="bg-white border border-border p-8 rounded-xl shadow-sm text-center flex flex-col items-center justify-center space-y-3 animate-pulse">
        <div className="h-6 w-6 border-2 border-accent border-t-transparent rounded-full animate-spin"></div>
        <p className="text-xs text-muted font-bold tracking-tight">Consulting market context panel...</p>
      </div>
    );
  }

  const data: MarketContextResponse = {
    date: apiData.date || new Date().toISOString().split("T")[0],
    economic: apiData.economic ? {
      score: apiData.economic.score ?? null,
      regime: apiData.economic.regime || "STABLE",
      positives: apiData.economic.positives || [],
      risks: apiData.economic.risks || [],
      overweight_sectors: apiData.economic.overweight_sectors || [],
      underweight_sectors: apiData.economic.underweight_sectors || [],
      reasoning: apiData.economic.reasoning || "Economic reasoning is currently unavailable.",
      model_used: apiData.economic.model_used || "N/A",
      built_at: apiData.economic.built_at || new Date().toISOString(),
    } : {
      score: null,
      regime: "STABLE",
      positives: [],
      risks: [],
      overweight_sectors: [],
      underweight_sectors: [],
      reasoning: "Economic context is currently unavailable.",
      model_used: "N/A",
      built_at: new Date().toISOString(),
    },
    market_pulse: apiData.market_pulse ? {
      score: apiData.market_pulse.score ?? null,
      regime: apiData.market_pulse.regime || "SIDEWAYS",
      india_vix: apiData.market_pulse.india_vix ?? null,
      nifty_level: apiData.market_pulse.nifty_level ?? null,
      advance_decline_ratio: apiData.market_pulse.advance_decline_ratio ?? null,
      sector_strength: apiData.market_pulse.sector_strength || [],
      breadth_signal: apiData.market_pulse.breadth_signal || null,
      market_health: apiData.market_pulse.market_health || null,
      reasoning: apiData.market_pulse.reasoning || "Market pulse reasoning is currently unavailable.",
    } : {
      score: null,
      regime: "SIDEWAYS",
      india_vix: null,
      nifty_level: null,
      advance_decline_ratio: null,
      sector_strength: [],
      breadth_signal: null,
      market_health: null,
      reasoning: "Market pulse context is currently unavailable.",
    },
    news: apiData.news ? {
      market_sentiment: apiData.news.market_sentiment ?? null,
      hot_sectors: apiData.news.hot_sectors || [],
      avoid_sectors: apiData.news.avoid_sectors || [],
      anomaly_alerts: apiData.news.anomaly_alerts || [],
      reasoning: apiData.news.reasoning || "News analysis is currently unavailable.",
      model_used: apiData.news.model_used || "N/A",
    } : {
      market_sentiment: null,
      hot_sectors: [],
      avoid_sectors: [],
      anomaly_alerts: [],
      reasoning: "News analysis is currently unavailable.",
      model_used: "N/A",
    },
    macro_context: apiData.macro_context ? {
      regime: apiData.macro_context.regime || "SIDEWAYS",
      confidence: apiData.macro_context.confidence ?? null,
      triggers: apiData.macro_context.triggers || {},
      reasoning: apiData.macro_context.reasoning || "Macro reasoning is currently unavailable.",
      model_used: apiData.macro_context.model_used || "N/A",
    } : {
      regime: "SIDEWAYS",
      confidence: null,
      triggers: {},
      reasoning: "Macro context is currently unavailable.",
      model_used: "N/A",
    },
    planner: apiData.planner ? {
      active_horizons: apiData.planner.active_horizons || [],
      overall_caution: apiData.planner.overall_caution || "NORMAL",
      horizon_plans: apiData.planner.horizon_plans || {},
      reasoning: apiData.planner.reasoning || "Planner strategy is currently unavailable.",
    } : {
      active_horizons: [],
      overall_caution: "NORMAL",
      horizon_plans: {},
      reasoning: "Planner strategy is currently unavailable.",
    },
  };

  const economicScore = data.economic.score ?? null;
  const marketPulseScore = data.market_pulse.score ?? null;
  const marketSentiment = data.news.market_sentiment ?? null;

  const toggleExpand = (card: string) => {
    if (expandedCard === card) {
      setExpandedCard(null);
    } else {
      setExpandedCard(card);
    }
  };

  const getRegimeColor = (regime: string) => {
    switch (regime) {
      case "EXPANSION":
      case "BULL":
        return "text-signal-buy bg-signal-buy/10 border-signal-buy/20";
      case "STABLE":
      case "HEALTHY":
      case "STRONG":
        return "text-emerald-700 bg-emerald-50 border-emerald-200";
      case "SLOWING":
      case "SIDEWAYS":
      case "MODERATE":
        return "text-signal-wait bg-signal-wait/10 border-signal-wait/20";
      case "CONTRACTION":
      case "BEAR":
      case "WEAK":
      case "FRAGILE":
        return "text-signal-sell bg-signal-sell/10 border-signal-sell/20";
      case "CRISIS":
      default:
        return "text-red-700 bg-red-100 border-red-200 animate-pulse";
    }
  };

  const formattedLastUpdated = () => {
    try {
      return new Date(lastUpdated).toLocaleString("en-IN", {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit"
      });
    } catch (e) {
      return lastUpdated;
    }
  };

  return (
    <div className="space-y-4">
      {/* Timestamp */}
      <div className="flex justify-between items-center bg-white border border-border p-3 rounded-xl shadow-sm">
        <span className="text-xs text-muted font-medium">
          Last Updated: {formattedLastUpdated()}
        </span>
      </div>

      {/* 4-Card Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        
        {/* Card 1: Economic */}
        <div className="bg-card rounded-xl border border-border shadow-sm overflow-hidden flex flex-col justify-between transition-all hover:shadow-md">
          <div className="p-4 space-y-3">
            <div className="flex justify-between items-start">
              <div className="p-2 bg-emerald-50 rounded-lg text-emerald-700 border border-emerald-100">
                <TrendingUp size={18} />
              </div>
              <span className={`text-[10px] md:text-xs font-bold px-2 py-0.5 rounded-full border ${getRegimeColor(data.economic.regime)}`}>
                {data.economic.regime}
              </span>
            </div>
            <div>
              <h4 className="text-xs text-muted font-medium uppercase tracking-wider">Economic Context</h4>
              <div className="flex items-baseline gap-1 mt-1">
                <span className="text-2xl font-bold text-primary">{economicScore !== null ? economicScore : "N/A"}</span>
                {economicScore !== null && <span className="text-xs text-muted">/100</span>}
              </div>
            </div>
            <div className="text-xs text-primary space-y-1.5 pt-1 border-t border-neutral-100">
              <div className="flex justify-between">
                <span className="text-muted">Overweight:</span>
                <span className="font-semibold text-right max-w-[120px] truncate">
                  {data.economic.overweight_sectors.length > 0 ? data.economic.overweight_sectors[0] : "None"}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted">Underweight:</span>
                <span className="font-semibold text-right max-w-[120px] truncate">
                  {data.economic.underweight_sectors.length > 0 ? data.economic.underweight_sectors[0] : "None"}
                </span>
              </div>
            </div>
          </div>
          
          <button
            onClick={() => toggleExpand("economic")}
            className="w-full px-4 py-2 border-t border-neutral-100 hover:bg-neutral-50 transition-colors flex justify-between items-center text-xs text-muted hover:text-accent-dark font-medium"
          >
            <span>Show reasoning</span>
            {expandedCard === "economic" ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
        </div>

        {/* Card 2: Market Pulse */}
        <div className="bg-card rounded-xl border border-border shadow-sm overflow-hidden flex flex-col justify-between transition-all hover:shadow-md">
          <div className="p-4 space-y-3">
            <div className="flex justify-between items-start">
              <div className="p-2 bg-blue-50 rounded-lg text-blue-700 border border-blue-100">
                <BarChart2 size={18} />
              </div>
              <span className={`text-[10px] md:text-xs font-bold px-2 py-0.5 rounded-full border ${getRegimeColor(data.market_pulse.regime)}`}>
                {data.market_pulse.regime}
              </span>
            </div>
            <div>
              <h4 className="text-xs text-muted font-medium uppercase tracking-wider">Market Pulse</h4>
              <div className="flex items-baseline gap-1 mt-1">
                <span className="text-2xl font-bold text-primary">{marketPulseScore !== null ? marketPulseScore : "N/A"}</span>
                {marketPulseScore !== null && <span className="text-xs text-muted">/100</span>}
              </div>
            </div>
            <div className="text-xs text-primary space-y-1.5 pt-1 border-t border-neutral-100">
              <div className="flex justify-between">
                <span className="text-muted">India VIX:</span>
                <span className="font-mono font-semibold">{data.market_pulse.india_vix ?? "N/A"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted">A/D Ratio:</span>
                <span className="font-mono font-semibold">{data.market_pulse.advance_decline_ratio ?? "N/A"}</span>
              </div>
            </div>
          </div>
          
          <button
            onClick={() => toggleExpand("pulse")}
            className="w-full px-4 py-2 border-t border-neutral-100 hover:bg-neutral-50 transition-colors flex justify-between items-center text-xs text-muted hover:text-accent-dark font-medium"
          >
            <span>Show reasoning</span>
            {expandedCard === "pulse" ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
        </div>

        {/* Card 3: News Sentiment */}
        <div className="bg-card rounded-xl border border-border shadow-sm overflow-hidden flex flex-col justify-between transition-all hover:shadow-md">
          <div className="p-4 space-y-3">
            <div className="flex justify-between items-start">
              <div className="p-2 bg-amber-50 rounded-lg text-amber-700 border border-amber-100">
                <Newspaper size={18} />
              </div>
              <span className={`text-[10px] md:text-xs font-bold px-2 py-0.5 rounded-full border ${
                marketSentiment === null
                  ? "text-muted bg-neutral-100 border-neutral-200"
                  : marketSentiment > 0
                  ? "text-signal-buy bg-signal-buy/10 border-signal-buy/20"
                  : marketSentiment < 0
                  ? "text-signal-sell bg-signal-sell/10 border-signal-sell/20"
                  : "text-muted bg-neutral-100 border-neutral-200"
              }`}>
                {marketSentiment === null ? "N/A" : marketSentiment > 0 ? "POSITIVE" : marketSentiment < 0 ? "NEGATIVE" : "NEUTRAL"}
              </span>
            </div>
            <div>
              <h4 className="text-xs text-muted font-medium uppercase tracking-wider">News Sentiment</h4>
              <div className="flex items-baseline gap-1 mt-1">
                <span className="text-2xl font-bold text-primary">
                  {marketSentiment === null
                    ? "N/A"
                    : `${marketSentiment > 0 ? "+" : ""}${marketSentiment}`}
                </span>
                {marketSentiment !== null && <span className="text-xs text-muted">score</span>}
              </div>
            </div>
            <div className="text-xs text-primary space-y-1.5 pt-1 border-t border-neutral-100">
              <div className="flex justify-between">
                <span className="text-muted">Hot Sectors:</span>
                <span className="font-semibold text-right max-w-[120px] truncate">{data.news.hot_sectors[0] || "None"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted">Avoid Sectors:</span>
                <span className="font-semibold text-right max-w-[120px] truncate">{data.news.avoid_sectors[0] || "None"}</span>
              </div>
            </div>
          </div>
          
          <button
            onClick={() => toggleExpand("news")}
            className="w-full px-4 py-2 border-t border-neutral-100 hover:bg-neutral-50 transition-colors flex justify-between items-center text-xs text-muted hover:text-accent-dark font-medium"
          >
            <span>Show reasoning</span>
            {expandedCard === "news" ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
        </div>

        {/* Card 4: Macro Context */}
        <div className="bg-card rounded-xl border border-border shadow-sm overflow-hidden flex flex-col justify-between transition-all hover:shadow-md">
          <div className="p-4 space-y-3">
            <div className="flex justify-between items-start">
              <div className="p-2 bg-orange-50 rounded-lg text-accent-dark border border-orange-100">
                <Globe2 size={18} />
              </div>
              <span className={`text-[10px] md:text-xs font-bold px-2 py-0.5 rounded-full border ${getRegimeColor(data.macro_context.regime)}`}>
                {data.macro_context.regime}
              </span>
            </div>
            <div>
              <h4 className="text-xs text-muted font-medium uppercase tracking-wider">Macro Context</h4>
              <div className="flex items-baseline gap-1 mt-1">
                <span className="text-2xl font-bold text-primary">
                  {data.macro_context.confidence !== null ? `${Math.round(data.macro_context.confidence <= 1 ? data.macro_context.confidence * 100 : data.macro_context.confidence)}%` : "N/A"}
                </span>
                <span className="text-xs text-muted">confidence</span>
              </div>
            </div>
            <div className="text-xs text-primary space-y-1.5 pt-1 border-t border-neutral-100">
              <div className="flex justify-between">
                <span className="text-muted">Fed policy:</span>
                <span className="font-semibold text-right max-w-[120px] truncate">{data.macro_context.triggers["Fed policy"] || "None"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted">Elections:</span>
                <span className="font-semibold text-right max-w-[120px] truncate">{data.macro_context.triggers["Elections"] || "None"}</span>
              </div>
            </div>
          </div>
          
          <button
            onClick={() => toggleExpand("macro")}
            className="w-full px-4 py-2 border-t border-neutral-100 hover:bg-neutral-50 transition-colors flex justify-between items-center text-xs text-muted hover:text-accent-dark font-medium"
          >
            <span>Show reasoning</span>
            {expandedCard === "macro" ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
        </div>

      </div>

      {/* Expanded Reasoning view */}
      {expandedCard && (
        <div className="p-4 bg-white border border-border shadow-inner rounded-xl animate-in slide-in-from-top-2 duration-200">
          <div className="flex justify-between items-center pb-2 border-b border-neutral-100">
            <h5 className="text-xs font-bold text-accent-dark uppercase tracking-wider flex items-center gap-1.5">
              <span>{expandedCard} analysis reasoning</span>
              {expandedCard === "macro" && (
                <button
                  onClick={() => setShowPlanner(!showPlanner)}
                  className="ml-4 normal-case text-xs text-accent hover:underline font-semibold"
                >
                  {showPlanner ? "Hide Horizon Plans" : "Show Horizon Plans & Weights"}
                </button>
              )}
            </h5>
            <span className="text-[10px] font-mono text-muted">
              Source: {expandedCard === "pulse" ? "Deterministic Rule Engine" : (data as any)[expandedCard]?.model_used || "Agent Reasoning"}
            </span>
          </div>
          <SafeHtmlText text={(data as any)[expandedCard]?.reasoning} className="text-xs md:text-sm text-primary leading-relaxed mt-2.5" />

          {/* Render Economic specifics */}
          {expandedCard === "economic" && (
            <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-4 pt-3 border-t border-neutral-100 text-xs">
              <div>
                <h6 className="font-bold text-emerald-800">Supportive Drivers (Positives)</h6>
                <ul className="list-disc pl-4 mt-1 space-y-1 text-muted">
                  {data.economic.positives.map((p, idx) => <li key={idx} className="inline-block w-full"><SafeHtmlText text={p} className="inline" /></li>)}
                </ul>
              </div>
              <div>
                <h6 className="font-bold text-signal-sell">Identified Risks</h6>
                <ul className="list-disc pl-4 mt-1 space-y-1 text-muted">
                  {data.economic.risks.map((r, idx) => <li key={idx} className="inline-block w-full"><SafeHtmlText text={r} className="inline" /></li>)}
                </ul>
              </div>
            </div>
          )}

          {/* Render Market Pulse specifics */}
          {expandedCard === "pulse" && (
            <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-4 pt-3 border-t border-neutral-100 text-xs">
              <div>
                <h6 className="font-bold text-primary">Sector Breadth Strength</h6>
                <div className="flex flex-wrap gap-2 mt-1.5">
                  {data.market_pulse.sector_strength.map((s, idx) => (
                    <span key={idx} className="bg-neutral-100 border border-neutral-200 px-2 py-0.5 rounded font-medium">
                      {s.sector} (Rank {s.rank})
                    </span>
                  ))}
                </div>
              </div>
              <div className="space-y-1">
                <div className="flex justify-between">
                  <span className="text-muted">Breadth Signal:</span>
                  <span className="font-semibold text-emerald-700">{data.market_pulse.breadth_signal}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted">Market Health:</span>
                  <span className="font-semibold text-emerald-700">{data.market_pulse.market_health}</span>
                </div>
              </div>
            </div>
          )}

          {/* Render News specifics */}
          {expandedCard === "news" && (
            <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-4 pt-3 border-t border-neutral-100 text-xs">
              <div>
                <h6 className="font-bold text-emerald-800">Sector Bullish Flags</h6>
                <div className="flex flex-wrap gap-2 mt-1.5">
                  {data.news.hot_sectors.map((s, idx) => (
                    <span key={idx} className="bg-signal-buy/5 border border-signal-buy/20 text-signal-buy px-2 py-0.5 rounded font-bold uppercase">
                      {s}
                    </span>
                  ))}
                </div>
              </div>
              <div>
                <h6 className="font-bold text-signal-sell">Anomalies Detected</h6>
                <ul className="list-disc pl-4 mt-1 space-y-1 text-muted">
                  {data.news.anomaly_alerts.map((a, idx) => <li key={idx} className="inline-block w-full"><SafeHtmlText text={a} className="inline" /></li>)}
                </ul>
              </div>
            </div>
          )}

          {/* Render Planner/Macro weights sub-section */}
          {(showPlanner || expandedCard === "macro") && (
            <div className="mt-4 bg-cream/35 border border-border/80 rounded-lg p-3 space-y-3">
              <div className="flex justify-between items-center">
                <h6 className="text-xs font-bold text-primary uppercase tracking-wide">Macro Planner Strategy</h6>
                <span className="text-[10px] text-muted font-bold">Overall Caution: {data.planner.overall_caution}</span>
              </div>
              <div className="text-xs text-muted leading-relaxed italic">
                "<SafeHtmlText text={data.planner.reasoning} className="inline" />"
              </div>
              
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="border-b border-border bg-neutral-100/50">
                      <th className="py-1 px-2 font-bold text-primary">Timeframe</th>
                      <th className="py-1 px-2 font-bold text-primary text-center">Tech</th>
                      <th className="py-1 px-2 font-bold text-primary text-center">Fund</th>
                      <th className="py-1 px-2 font-bold text-primary text-center">Sent</th>
                      <th className="py-1 px-2 font-bold text-primary text-center">Pattern</th>
                      <th className="py-1 px-2 font-bold text-primary text-center">Min Conviction</th>
                      <th className="py-1 px-2 font-bold text-primary">Core Strategy</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(Object.keys(data.planner.horizon_plans) as Horizon[]).map((hor) => {
                      const plan = data.planner.horizon_plans[hor];
                      return (
                        <tr key={hor} className="border-b border-neutral-100/50 hover:bg-neutral-50/50">
                          <td className="py-2 px-2 font-bold text-accent-dark">{hor}</td>
                          <td className="py-2 px-2 text-center font-mono text-muted">{plan.agent_weights.technical}%</td>
                          <td className="py-2 px-2 text-center font-mono text-muted">{plan.agent_weights.fundamental}%</td>
                          <td className="py-2 px-2 text-center font-mono text-muted">{plan.agent_weights.sentiment}%</td>
                          <td className="py-2 px-2 text-center font-mono text-muted">{plan.agent_weights.chart_pattern}%</td>
                          <td className="py-2 px-2 text-center font-bold text-primary font-mono">{plan.min_conviction}%</td>
                          <td className="py-2 px-2 text-muted leading-snug">{plan.strategy}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

        </div>
      )}


    </div>
  );
}
