import React, { useState } from "react";
import { ChevronDown, ChevronUp, ShieldAlert, Award, FileText } from "lucide-react";
import type { AnalyzeResponse, Signal } from "../../types";
import { SignalBadge } from "../shared/SignalBadge";
import { SafeHtmlText } from "../shared/SafeHtmlText";
import { toVerdict } from "../../utils/verdict";

interface ReasoningAccordionProps {
  data: AnalyzeResponse;
}

export function ReasoningAccordion({ data }: ReasoningAccordionProps) {
  // All sections open by default to ensure detailed reasoning is clearly visible.
  const [openSections, setOpenSections] = useState<Record<string, boolean>>({
    decision: true,
    debate: true,
    technical: true,
    fundamental: true,
    sentiment: true,
    chart_pattern: true,
    horizon: true,
    market: true,
  });

  const toggleSection = (section: string) => {
    setOpenSections((prev) => ({
      ...prev,
      [section]: !prev[section],
    }));
  };

  const renderSectionHeader = (
    id: string,
    title: string,
    icon: string,
    badgeValue?: Signal | null,
    badgeConf?: number | null,
    extraBadge?: React.ReactNode
  ) => {
    const isOpen = openSections[id];
    return (
      <button
        type="button"
        onClick={() => toggleSection(id)}
        className="w-full px-4 py-3 bg-neutral-50 hover:bg-neutral-100/80 transition-colors flex justify-between items-center text-xs md:text-sm font-bold text-primary select-none focus:outline-none border-b border-border"
        style={{ minHeight: "48px" }} // Mobile friendly touch target size
      >
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-base md:text-lg">{icon}</span>
          <span className="tracking-tight">{title}</span>
          {badgeValue && (
            <SignalBadge signal={badgeValue} confidence={badgeConf} className="ml-1 text-[10px] md:text-xs scale-90 md:scale-100" />
          )}
          {extraBadge}
        </div>
        <div>
          {isOpen ? <ChevronUp size={16} className="text-muted" /> : <ChevronDown size={16} className="text-muted" />}
        </div>
      </button>
    );
  };

  return (
    <div className="border border-border rounded-xl bg-white overflow-hidden shadow-sm divide-y divide-border">
      
      {/* 1. DECISION PANEL */}
      <div>
        {renderSectionHeader("decision", "Decision & Catalysts", "🏛️", toVerdict(data.recommendation), data.confidence)}
        {openSections.decision && (
          <div className="p-4 space-y-4 text-xs md:text-sm text-primary leading-relaxed animate-in slide-in-from-top-1 duration-150">
            {/* Decision Narrative */}
            <SafeHtmlText text={data.narrative} className="leading-relaxed font-medium text-neutral-800" />

            {/* Catalysts & Risks Dual Column */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-3 border-t border-neutral-100">
              <div className="bg-emerald-50/50 border border-emerald-200/55 p-3 rounded-lg space-y-2">
                <h5 className="font-bold text-emerald-950 flex items-center gap-1.5 text-xs">
                  <Award size={14} className="text-signal-buy" />
                  <span>Key Catalysts</span>
                </h5>
                <ul className="list-disc pl-4 space-y-1.5 text-muted text-[11px] md:text-xs">
                  {data.key_catalysts && data.key_catalysts.length > 0 ? (
                    data.key_catalysts.map((c, i) => <li key={i} className="inline-block w-full"><SafeHtmlText text={c} className="inline" /></li>)
                  ) : (
                    <li>No positive catalysts specified.</li>
                  )}
                </ul>
              </div>

              <div className="bg-red-50/50 border border-red-200/55 p-3 rounded-lg space-y-2">
                <h5 className="font-bold text-red-950 flex items-center gap-1.5 text-xs">
                  <ShieldAlert size={14} className="text-signal-sell" />
                  <span>Key Risks</span>
                </h5>
                <ul className="list-disc pl-4 space-y-1.5 text-muted text-[11px] md:text-xs">
                  {data.key_risks && data.key_risks.length > 0 ? (
                    data.key_risks.map((r, i) => <li key={i} className="inline-block w-full"><SafeHtmlText text={r} className="inline" /></li>)
                  ) : (
                    <li>No high risk parameters flagged.</li>
                  )}
                </ul>
              </div>
            </div>

            {/* Validator Issues Sub-section */}
            {data.validator_issues && data.validator_issues.length > 0 && (
              <div className="mt-3 bg-amber-50/60 border border-amber-200 rounded-lg p-3 space-y-2">
                <h5 className="font-bold text-amber-900 text-xs flex items-center gap-1">
                  <ShieldAlert size={13} className="text-signal-wait" />
                  <span>Validator Adjustments ({data.validator_issues.length})</span>
                </h5>
                <div className="divide-y divide-amber-100 text-[11px] md:text-xs text-muted">
                  {data.validator_issues.map((issue, idx) => (
                    <div key={idx} className="py-1.5 first:pt-0 last:pb-0">
                      <div className="flex justify-between font-semibold">
                        <span className="text-amber-800">Field: {issue.field} (Layer {issue.layer})</span>
                        <span className="uppercase text-amber-950 font-bold">Action: {issue.action}</span>
                      </div>
                      {issue.note && <p className="mt-0.5">{issue.note}</p>}
                      {(issue.before || issue.after) && (
                        <p className="mt-0.5 font-mono text-[10px]">
                          Adjustment: {issue.before} &rarr; {issue.after}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* 2. DEBATE SPECIALIST */}
      {data.debate_summary && (
        <div>
          {renderSectionHeader(
            "debate",
            "Consensus Debate",
            "⚖️",
            // NOTE: this is the debate agent's OWN independent signal, NOT the final
            // verdict. It is intentionally allowed to differ from the Decision badge
            // above — the debate is one weighted voice, not the verdict. We prefix it
            // with "Debate:" so it never reads as a second, competing final call.
            null,
            null,
            <>
              {data.debate_summary.independent_signal && (
                <span className="inline-flex items-center gap-1 ml-1">
                  <span className="text-[9px] font-bold text-muted uppercase">Debate view:</span>
                  <SignalBadge
                    signal={data.debate_summary.independent_signal}
                    confidence={data.debate_summary.independent_confidence}
                    className="text-[10px] md:text-xs scale-90 md:scale-100"
                  />
                </span>
              )}
              <span
                className={`text-[9px] font-bold px-2 py-0.5 rounded border ml-1 ${
                  data.debate_summary.agrees_with_consensus
                    ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                    : "bg-amber-50 text-amber-700 border-amber-200"
                }`}
              >
                Agrees with verdict: {data.debate_summary.agrees_with_consensus ? "YES" : "NO"}
              </span>
            </>
          )}
          {openSections.debate && (
            <div className="p-4 space-y-4 text-xs md:text-sm animate-in slide-in-from-top-1 duration-150">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-1">
                  <h6 className="font-bold text-signal-buy">Bull Case (Consensus Expansion)</h6>
                  <SafeHtmlText text={data.debate_summary.bull_case || "No bull case arguments provided."} className="text-muted leading-relaxed" />
                </div>
                <div className="space-y-1">
                  <h6 className="font-bold text-signal-sell">Bear Case (Consensus Contraction)</h6>
                  <SafeHtmlText text={data.debate_summary.bear_case || "No bear case arguments provided."} className="text-muted leading-relaxed" />
                </div>
              </div>

              {data.debate_summary.synthesis && (
                <div className="pt-3 border-t border-neutral-100 space-y-1 bg-neutral-50/50 p-2.5 rounded">
                  <h6 className="font-bold text-primary">Debate Synthesis Verdict</h6>
                  <SafeHtmlText text={data.debate_summary.synthesis} className="text-muted leading-relaxed" />
                </div>
              )}

              {data.debate_summary.missed_risks && data.debate_summary.missed_risks.length > 0 && (
                <div className="pt-2 text-xs">
                  <h6 className="font-bold text-signal-sell">Debate Specialist Flags (Missed Consensus Risks)</h6>
                  <ul className="list-disc pl-4 mt-1 text-muted space-y-1">
                    {data.debate_summary.missed_risks.map((mr, idx) => <li key={idx} className="inline-block w-full"><SafeHtmlText text={mr} className="inline" /></li>)}
                  </ul>
                </div>
              )}

              {data.debate_summary.evidence_citations && data.debate_summary.evidence_citations.length > 0 && (
                <div className="pt-2 text-[10px] text-muted border-t border-neutral-100 flex items-center gap-1.5 flex-wrap">
                  <span className="font-bold uppercase tracking-wider">Evidence Citations:</span>
                  {data.debate_summary.evidence_citations.map((cite, idx) => (
                    <span key={idx} className="bg-neutral-100 px-2 py-0.5 rounded border border-neutral-200 flex items-center gap-0.5">
                      <FileText size={10} />
                      {cite}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* 3. TECHNICAL SPECIALIST */}
      {data.technical_summary && (
        <div>
          {renderSectionHeader("technical", "Technical Analysis", "📐", data.technical_summary.signal, data.technical_summary.confidence)}
          {openSections.technical && (
            <div className="p-4 space-y-3 text-xs md:text-sm animate-in slide-in-from-top-1 duration-150">
              <SafeHtmlText text={data.technical_summary.narrative} className="text-muted leading-relaxed" />
              
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-3 border-t border-neutral-100 font-mono text-[11px] md:text-xs">
                <div className="bg-neutral-50 p-2.5 rounded border border-neutral-200">
                  <span className="text-muted block font-sans">Current Price:</span>
                  <span className="font-bold text-primary">{data.technical_summary.current_price ? `₹${data.technical_summary.current_price}` : "—"}</span>
                </div>
                <div className="bg-neutral-50 p-2.5 rounded border border-neutral-200">
                  <span className="text-muted block font-sans">ATR:</span>
                  <span className="font-bold text-primary">{data.technical_summary.atr ? `₹${data.technical_summary.atr}` : "—"}</span>
                </div>
                <div className="bg-neutral-50 p-2.5 rounded border border-neutral-200">
                  <span className="text-muted block font-sans">RSI (14):</span>
                  <span className="font-bold text-primary">{data.technical_summary.rsi || "—"}</span>
                </div>
              </div>

              {data.technical_summary.key_levels && (
                <div className="pt-2 text-xs">
                  <h6 className="font-bold text-primary">Key Technical Levels</h6>
                  <div className="flex flex-wrap gap-2.5 mt-1.5">
                    {Object.entries(data.technical_summary.key_levels).map(([lvl, val]) => (
                      <span key={lvl} className="bg-neutral-100 border border-neutral-200 px-2 py-0.5 rounded font-mono">
                        <strong className="font-sans uppercase text-[10px] text-muted mr-1">{lvl}:</strong>
                        {String(val)}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* 4. FUNDAMENTAL SPECIALIST */}
      {data.fundamental_summary && (
        <div>
          {renderSectionHeader("fundamental", "Fundamental Analysis", "💰", data.fundamental_summary.signal, data.fundamental_summary.confidence)}
          {openSections.fundamental && (
            <div className="p-4 space-y-3 text-xs md:text-sm animate-in slide-in-from-top-1 duration-150">
              <SafeHtmlText text={data.fundamental_summary.narrative} className="text-muted leading-relaxed" />
              
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-3 border-t border-neutral-100">
                <div className="space-y-1.5">
                  <h6 className="font-bold text-emerald-800 text-[11px] md:text-xs">Core Strengths</h6>
                  <ul className="list-disc pl-4 text-muted space-y-1 text-[11px] md:text-xs">
                    {data.fundamental_summary.strengths.map((str, idx) => <li key={idx} className="inline-block w-full"><SafeHtmlText text={str} className="inline" /></li>)}
                  </ul>
                </div>
                <div className="space-y-1.5">
                  <h6 className="font-bold text-signal-sell text-[11px] md:text-xs">Identified Weaknesses</h6>
                  <ul className="list-disc pl-4 text-muted space-y-1 text-[11px] md:text-xs">
                    {data.fundamental_summary.weaknesses.map((weak, idx) => <li key={idx} className="inline-block w-full"><SafeHtmlText text={weak} className="inline" /></li>)}
                  </ul>
                </div>
              </div>

              <div className="pt-2 flex justify-between items-center text-xs font-mono border-t border-neutral-100">
                <span className="font-sans text-muted">Fundamental Weighted Score:</span>
                <span className="font-bold text-accent-dark">{data.fundamental_summary.weighted_score || 0} / 100</span>
              </div>
            </div>
          )}
        </div>
      )}

      {/* 5. SENTIMENT SPECIALIST */}
      {data.sentiment_summary && (
        <div>
          {renderSectionHeader("sentiment", "Sentiment Analysis", "💬", data.sentiment_summary.signal, data.sentiment_summary.confidence)}
          {openSections.sentiment && (
            <div className="p-4 space-y-3 text-xs md:text-sm animate-in slide-in-from-top-1 duration-150">
              <SafeHtmlText text={data.sentiment_summary.narrative} className="text-muted leading-relaxed" />

              {data.sentiment_summary.key_themes && data.sentiment_summary.key_themes.length > 0 && (
                <div className="flex flex-wrap gap-1.5 items-center pt-2 border-t border-neutral-100">
                  <span className="text-[10px] uppercase font-bold text-muted mr-1">Sentiment Themes:</span>
                  {data.sentiment_summary.key_themes.map((theme, i) => (
                    <span key={i} className="bg-neutral-100 border border-neutral-200 text-muted px-2 py-0.5 rounded text-[10px] md:text-xs font-medium">
                      {theme}
                    </span>
                  ))}
                </div>
              )}

              {/* Scored Headlines (Top 5) */}
              {data.sentiment_summary.headlines && data.sentiment_summary.headlines.length > 0 && (
                <div className="pt-3 space-y-1.5">
                  <h6 className="font-bold text-primary text-[11px] md:text-xs">Scored News Feeds</h6>
                  <div className="divide-y divide-neutral-100 border border-neutral-200/60 rounded-lg bg-neutral-50/50 overflow-hidden">
                    {data.sentiment_summary.headlines.slice(0, 5).map((hl, idx) => (
                      <div key={idx} className="p-2 flex items-start justify-between gap-3 text-[11px]">
                        <p className="text-primary leading-normal">{hl.text} <span className="text-[10px] text-muted font-mono">({hl.source || "Feed"})</span></p>
                        <span className={`font-mono font-bold shrink-0 text-[10px] px-1 rounded ${
                          hl.score > 0
                            ? "text-signal-buy bg-signal-buy/10"
                            : hl.score < 0
                            ? "text-signal-sell bg-signal-sell/10"
                            : "text-signal-hold bg-signal-hold/10"
                        }`}>
                          {hl.score >= 0 ? "+" : ""}{hl.score}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* 6. CHART PATTERN SPECIALIST */}
      {data.chart_pattern_summary && (
        <div>
          {renderSectionHeader("chart_pattern", "Chart Pattern Detections", "📊", data.chart_pattern_summary.signal, data.chart_pattern_summary.confidence)}
          {openSections.chart_pattern && (
            <div className="p-4 space-y-3 text-xs md:text-sm animate-in slide-in-from-top-1 duration-150">
              <SafeHtmlText text={data.chart_pattern_summary.narrative} className="text-muted leading-relaxed" />

              {data.chart_pattern_summary.patterns_detected && data.chart_pattern_summary.patterns_detected.length > 0 && (
                <div className="flex flex-wrap gap-1.5 items-center pt-2 border-t border-neutral-100">
                  <span className="text-[10px] uppercase font-bold text-muted mr-1">Patterns:</span>
                  {data.chart_pattern_summary.patterns_detected.map((p, i) => (
                    <span key={i} className="bg-orange-50 border border-orange-200 text-accent-dark px-2 py-0.5 rounded text-[10px] md:text-xs font-bold uppercase">
                      {p}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* 7. HORIZON CONFIRMATION */}
      {data.horizon_confirmation && (
        <div>
          {renderSectionHeader(
            "horizon",
            "Horizon Alignment",
            "🎯",
            null,
            null,
            <span className="text-[10px] md:text-xs font-bold text-muted ml-1 uppercase bg-neutral-100 border px-2 py-0.5 rounded">
              Suggested: {data.horizon_confirmation.suggested_horizon} &rarr; Final: {data.horizon_confirmation.final_horizon}
            </span>
          )}
          {openSections.horizon && (
            <div className="p-4 space-y-3 text-xs md:text-sm animate-in slide-in-from-top-1 duration-150">
              {data.horizon_confirmation.override_reason && (
                <div className="bg-neutral-50 p-3 border border-neutral-200 rounded-lg">
                  <h6 className="font-bold text-primary">Horizon Override Reason</h6>
                  <SafeHtmlText text={data.horizon_confirmation.override_reason} className="text-muted leading-relaxed mt-1" />
                </div>
              )}

              {data.horizon_confirmation.horizon_scores && (
                <div className="space-y-1.5 pt-2">
                  <h6 className="font-bold text-primary">Timeframe Scoring Breakdown</h6>
                  <div className="flex flex-wrap gap-3 mt-1 text-[11px] md:text-xs font-mono">
                    {Object.entries(data.horizon_confirmation.horizon_scores).map(([hor, score]) => (
                      <span key={hor} className="bg-neutral-100 border border-neutral-200 px-2 py-1 rounded">
                        <strong className="font-sans uppercase text-[10px] text-muted mr-1">{hor}:</strong>
                        {score} pts
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* 8. MARKET CONTEXT AT ANALYSIS */}
      <div>
        {renderSectionHeader(
          "market",
          "Analysis Pre-amble Context",
          "🌍",
          null,
          null,
          <span className="text-[10px] md:text-xs font-mono font-bold text-muted ml-1 bg-neutral-100 border px-2 py-0.5 rounded uppercase">
            Regime: {data.macro_regime} · Score: {data.market_pulse_score}/100
          </span>
        )}
        {openSections.market && (
          <div className="p-4 space-y-3 text-xs md:text-sm animate-in slide-in-from-top-1 duration-150">
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 text-center text-xs font-mono">
              <div className="bg-neutral-50 border border-neutral-200 rounded-lg p-2.5">
                <span className="font-sans text-muted block text-[10px]">Macro Regime</span>
                <span className="font-bold text-primary">{data.macro_regime}</span>
              </div>
              <div className="bg-neutral-50 border border-neutral-200 rounded-lg p-2.5">
                <span className="font-sans text-muted block text-[10px]">Pulse Score</span>
                <span className="font-bold text-primary">{data.market_pulse_score} / 100</span>
              </div>
              <div className="bg-neutral-50 border border-neutral-200 rounded-lg p-2.5">
                <span className="font-sans text-muted block text-[10px]">Economic Score</span>
                <span className="font-bold text-primary">{data.economic_score || "—"} / 100</span>
              </div>
              <div className="bg-neutral-50 border border-neutral-200 rounded-lg p-2.5">
                <span className="font-sans text-muted block text-[10px]">Economic Regime</span>
                <span className="font-bold text-primary">{data.economic_regime || "—"}</span>
              </div>
            </div>
            <p className="text-[11px] text-muted italic mt-2.5 text-center leading-normal">
              Analysis was timestamped on {(() => {
                const dateStr = data.created_at || data.timestamp;
                if (!dateStr) return "—";
                const isoStr = dateStr.includes("Z") || dateStr.includes("+") ? dateStr : `${dateStr}Z`;
                return new Date(isoStr).toLocaleString("en-IN");
              })()} in alignment with the active macro intelligence profile shown above.
            </p>
          </div>
        )}
      </div>

    </div>
  );
}
