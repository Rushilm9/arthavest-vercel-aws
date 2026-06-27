import { useState, useEffect } from "react";
import { apiService } from "../services/api";
import { Spinner } from "../components/shared/Spinner";
import { Sparkles, CheckCircle2, FileText, AlertCircle, RefreshCw, Copy, Check, ChevronDown } from "lucide-react";
import type { ImproveProposeResponse } from "../types";

const KNOWN_PROMPTS = [
  { id: "decision-narrative-prompt", name: "Decision Narrative Agent" },
  { id: "technical-analysis-prompt", name: "Technical Analysis Agent" },
  { id: "fundamental-analysis-prompt", name: "Fundamental Analysis Agent" },
  { id: "sentiment-analysis-prompt", name: "Sentiment Analysis Agent" },
  { id: "chart-pattern-prompt", name: "Chart Pattern Agent" },
];

export function Improve() {
  const [promptName, setPromptName] = useState(KNOWN_PROMPTS[0].id);
  
  const [isProposing, setIsProposing] = useState(false);
  const [proposeResult, setProposeResult] = useState<ImproveProposeResponse | { error: string } | null>(null);
  
  const [isCopied, setIsCopied] = useState(false);
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    setIsCopied(true);
    setTimeout(() => setIsCopied(false), 2000);
  };

  // Auto-fetch when the selected prompt changes
  useEffect(() => {
    handlePropose(promptName);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [promptName]);

  const handlePropose = async (targetPrompt: string) => {
    setIsProposing(true);
    setProposeResult(null);
    try {
      const res = await apiService.improvePropose(targetPrompt);
      setProposeResult(res);
    } catch (err: any) {
      setProposeResult({ error: err?.response?.data?.detail || err.message || "Failed to propose fixes." });
    } finally {
      setIsProposing(false);
    }
  };

  const hasError = proposeResult && "error" in proposeResult;

  return (
    <div className="space-y-6 animate-in fade-in duration-200 pb-8">
      {/* Target Prompt Form */}
      <div className="bg-white rounded-xl border border-border p-5 md:p-6 shadow-sm flex flex-col md:flex-row gap-5 items-end">
        <div className="flex-1 w-full relative">
          <label className="text-xs font-bold text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
            <FileText className="w-4 h-4" />
            Select Agent Queue
          </label>
          <div className="relative">
            <button
              onClick={() => setIsDropdownOpen(!isDropdownOpen)}
              className="w-full flex items-center justify-between px-4 py-3 bg-neutral-50 hover:bg-neutral-100 border border-border rounded-lg focus:outline-none focus:border-navy focus:ring-1 focus:ring-navy transition-all text-sm font-bold text-primary shadow-inner"
            >
              <span className="flex items-center gap-2">
                {KNOWN_PROMPTS.find(p => p.id === promptName)?.name || promptName}
                <span className="text-xs font-mono text-muted bg-white px-2 py-0.5 rounded shadow-sm border border-neutral-200">
                  {KNOWN_PROMPTS.find(p => p.id === promptName)?.id}
                </span>
              </span>
              <ChevronDown size={16} className={`text-muted transition-transform duration-200 ${isDropdownOpen ? 'rotate-180' : ''}`} />
            </button>

            {isDropdownOpen && (
              <>
                <div 
                  className="fixed inset-0 z-40" 
                  onClick={() => setIsDropdownOpen(false)}
                />
                <div className="absolute top-full left-0 right-0 mt-2 bg-white border border-border rounded-xl shadow-xl z-50 overflow-hidden animate-in fade-in slide-in-from-top-2 duration-200">
                  {KNOWN_PROMPTS.map((p) => (
                    <button
                      key={p.id}
                      onClick={() => {
                        setPromptName(p.id);
                        setIsDropdownOpen(false);
                      }}
                      className={`w-full flex flex-col items-start px-4 py-3 hover:bg-neutral-50 transition-colors border-b border-neutral-100 last:border-0 ${promptName === p.id ? 'bg-blue-50/50' : ''}`}
                    >
                      <span className={`text-sm font-bold ${promptName === p.id ? 'text-blue-700' : 'text-primary'}`}>
                        {p.name}
                      </span>
                      <span className="text-xs font-mono text-muted mt-0.5">
                        {p.id}
                      </span>
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>
        
        <button
          onClick={() => handlePropose(promptName)}
          disabled={isProposing}
          className="w-full md:w-auto px-6 py-3 bg-white border border-border hover:bg-neutral-50 text-primary text-xs font-black uppercase tracking-wide rounded-lg transition-all shadow-sm flex items-center justify-center gap-2 disabled:opacity-60"
        >
          {isProposing ? <Spinner size="sm" className="text-primary border-primary" /> : <RefreshCw size={16} />}
          Refresh Queue
        </button>
      </div>



      {/* Loading State */}
      {isProposing && !proposeResult && (
        <div className="flex flex-col items-center justify-center p-12 bg-white border border-border rounded-xl shadow-sm text-center">
          <Spinner size="lg" className="mb-4" />
          <h4 className="text-sm font-bold text-primary">Analyzing Traces & Generating Proposals...</h4>
          <p className="text-xs text-muted mt-1">This may take a moment while the Improver LLM synthesizes failures.</p>
        </div>
      )}

      {/* Result Panel */}
      {proposeResult && !hasError && !isProposing && (
        <div className="space-y-4 animate-in slide-in-from-bottom-2 duration-300">
          <div className="bg-white border border-border p-6 md:p-8 rounded-xl shadow-sm relative overflow-hidden">
            {/* Status Header */}
            <div className="flex items-center gap-3 mb-5 pb-5 border-b border-neutral-100">
              <div className={`p-2 rounded-lg ${
                (proposeResult as ImproveProposeResponse).status === "no_failures" 
                  ? "bg-green-100 text-signal-buy" 
                  : "bg-accent-soft text-accent-dark"
              }`}>
                {(proposeResult as ImproveProposeResponse).status === "no_failures" ? (
                  <CheckCircle2 className="w-6 h-6" />
                ) : (
                  <Sparkles className="w-6 h-6" />
                )}
              </div>
              <div>
                <h3 className="text-base font-black text-primary capitalize">
                  {(proposeResult as ImproveProposeResponse).status.replace("_", " ")}
                </h3>
                <p className="text-xs text-muted font-medium mt-0.5">Automated Evaluation Result</p>
              </div>
              {((proposeResult as ImproveProposeResponse).failures_analyzed ?? 0) > 0 && (
                <div className="ml-auto flex items-center gap-2 bg-neutral-100 px-3 py-1.5 rounded-lg border border-neutral-200">
                  <AlertCircle size={14} className="text-amber-500" />
                  <span className="text-[11px] font-bold text-primary">
                    {(proposeResult as ImproveProposeResponse).failures_analyzed} Failures Analyzed
                  </span>
                </div>
              )}
            </div>
            
            {/* Analysis Box */}
            {((proposeResult as ImproveProposeResponse).message || (proposeResult as ImproveProposeResponse).analysis) && (
              <div className="mb-6">
                <h4 className="text-[10px] font-bold text-muted uppercase tracking-wider mb-2">What this will improve & Why this will help</h4>
                <p className="text-sm text-primary/90 bg-neutral-50 p-4 rounded-lg border border-neutral-200 leading-relaxed shadow-inner">
                  {(proposeResult as ImproveProposeResponse).message || (proposeResult as ImproveProposeResponse).analysis}
                </p>
              </div>
            )}

            {/* New Rule Box */}
            {(proposeResult as ImproveProposeResponse).rule && (
              <div className="mb-6">
                <h4 className="text-[10px] font-bold text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                  <span className="bg-emerald-500 text-white px-2 py-0.5 rounded shadow-sm">EXTRACTED RULE</span>
                </h4>
                <p className="text-sm font-semibold text-emerald-900 bg-emerald-50 p-4 rounded-lg border border-emerald-200 leading-relaxed shadow-inner">
                  {(proposeResult as ImproveProposeResponse).rule}
                </p>
              </div>
            )}

            {/* Candidate Prompt */}
            {((proposeResult as ImproveProposeResponse).candidate_prompt || (proposeResult as ImproveProposeResponse).proposed_prompt) && (
              <div className="mt-6">
                <div className="flex items-center justify-between mb-2">
                  <h4 className="text-[10px] font-bold text-muted uppercase tracking-wider flex items-center gap-2">
                    <span className="bg-accent text-white px-2 py-0.5 rounded shadow-sm">NEW CANDIDATE TEMPLATE</span>
                  </h4>
                  <button 
                    onClick={() => handleCopy((proposeResult as ImproveProposeResponse).proposed_prompt || (proposeResult as ImproveProposeResponse).candidate_prompt || "")}
                    className="flex items-center gap-1 text-[10px] font-bold text-muted hover:text-primary transition-colors bg-neutral-100 hover:bg-neutral-200 px-2 py-1 rounded"
                  >
                    {isCopied ? <Check size={12} className="text-emerald-500" /> : <Copy size={12} />}
                    {isCopied ? "COPIED!" : "COPY PROMPT"}
                  </button>
                </div>
                <div className="bg-[#0f111a] text-[#a6accd] p-5 rounded-xl overflow-x-auto text-[13px] font-mono leading-relaxed max-h-[400px] overflow-y-auto shadow-inner border border-slate-800">
                  <pre className="whitespace-pre-wrap font-inherit">
                    {(proposeResult as ImproveProposeResponse).proposed_prompt || (proposeResult as ImproveProposeResponse).candidate_prompt}
                  </pre>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Error Panel */}
      {hasError && (
        <div className="bg-red-50 p-6 rounded-xl border border-red-200 shadow-sm animate-in zoom-in-95 duration-200">
          <h3 className="text-red-800 font-bold text-sm mb-2 flex items-center gap-2">
            <AlertCircle className="w-5 h-5" />
            Error Processing Queue
          </h3>
          <p className="text-red-600/90 text-sm">{(proposeResult as { error: string }).error}</p>
        </div>
      )}
    </div>
  );
}

