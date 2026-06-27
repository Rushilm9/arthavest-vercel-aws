import { useState } from "react";
import { useQuota } from "../../hooks/useQuota";
import { HelpCircle, RefreshCw, X } from "lucide-react";
import { Spinner } from "./Spinner";

export function QuotaMeter() {
  const { data: quota, isLoading, isError, refetch } = useQuota();
  const [isOpen, setIsOpen] = useState(false);

  if (isLoading) {
    return (
      <div className="flex items-center gap-1.5 text-xs text-muted">
        <Spinner size="sm" className="w-3.5 h-3.5" />
        <span>Quota loading...</span>
      </div>
    );
  }

  if (isError || !quota || !quota.tiers) {
    return (
      <div className="text-xs text-muted font-mono flex items-center gap-1">
        <span>Quota: —</span>
        <button
          onClick={() => refetch()}
          title="Retry loading quota"
          className="hover:text-accent transition-colors"
        >
          <RefreshCw size={10} />
        </button>
      </div>
    );
  }

  const { pro, flash, flash_lite, gemini_flash } = quota.tiers;

  // Calculate highest percentage to color-code
  const maxPct = Math.max(pro.pct, flash.pct, flash_lite?.pct || 0, gemini_flash?.pct || 0);

  let indicatorColor = "text-muted border-border hover:bg-neutral-100";
  if (maxPct > 95) {
    indicatorColor = "text-signal-sell border-signal-sell/30 bg-signal-sell/5 hover:bg-signal-sell/10 animate-pulse";
  } else if (maxPct > 80) {
    indicatorColor = "text-signal-wait border-signal-wait/30 bg-signal-wait/5 hover:bg-signal-wait/10";
  }

  const formatResetTime = (timestamp: string) => {
    try {
      const isoStr = timestamp.includes("Z") || timestamp.includes("+") ? timestamp : `${timestamp}Z`;
      const date = new Date(isoStr);
      return date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
    } catch {
      return "Midnight PT";
    }
  };

  return (
    <>
      {/* Compact indicator */}
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        className={`flex items-center gap-1 px-2 sm:px-2.5 py-1 rounded-md border text-[11px] md:text-xs font-mono transition-all duration-150 ${indicatorColor}`}
        title={`Resets at ${formatResetTime(quota.resets_at)}. Click for details.`}
      >
        {/* Mobile: collapse to a single dot + worst-tier % to avoid crushing the header row */}
        <span className="flex sm:hidden items-center gap-1">
          <span className={`w-1.5 h-1.5 rounded-full ${maxPct > 95 ? "bg-signal-sell" : maxPct > 80 ? "bg-signal-wait" : "bg-emerald-500"}`} />
          <span>Quota {Math.round(maxPct)}%</span>
        </span>

        {/* Tablet/Desktop: full per-tier breakdown */}
        <span className="hidden sm:flex items-center gap-1">
          <span>Pro: {pro.used}/{pro.ceiling}</span>
          <span className="opacity-50">·</span>
          <span>Flash: {flash.used}/{flash.ceiling}</span>
          {flash_lite && (
            <>
              <span className="opacity-50 hidden md:inline">·</span>
              <span className="hidden md:inline">Lite: {flash_lite.used}/{flash_lite.ceiling}</span>
            </>
          )}
          <span className="opacity-50">·</span>
          <span>Flash 1.5: {gemini_flash?.used || 0}/{gemini_flash?.ceiling || 0}</span>
        </span>
      </button>

      {/* Details Modal */}
      {isOpen && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-card w-full max-w-md rounded-xl border border-border shadow-2xl overflow-hidden animate-in zoom-in-95 duration-200">
            {/* Header */}
            <div className="px-5 py-4 border-b border-border flex items-center justify-between bg-cream/35">
              <div>
                <h3 className="font-semibold text-primary">LLM Quota Metrics</h3>
                <p className="text-xs text-muted mt-0.5">Resets today at {formatResetTime(quota.resets_at)}</p>
              </div>
              <button
                type="button"
                onClick={() => setIsOpen(false)}
                className="p-1 rounded-full hover:bg-neutral-100 transition-colors text-muted hover:text-primary"
              >
                <X size={16} />
              </button>
            </div>

            {/* Content */}
            <div className="p-5 space-y-4">
              {/* Tiers List */}
              {[
                { name: "Pro (gemini-2.5-pro)", data: pro },
                { name: "Flash (gemini-3.0-flash)", data: flash },
                { name: "Lite (gemini-3.1-flash-lite)", data: flash_lite },
                { name: "Flash 1.5 (gemini-1.5-flash)", data: gemini_flash },
              ].map((tier, idx) => {
                if (!tier.data) return null;
                const { used, ceiling, pct } = tier.data;
                const isOver95 = pct > 95;
                const isOver80 = pct > 80;

                let barColor = "bg-accent";
                if (isOver95) barColor = "bg-signal-sell";
                else if (isOver80) barColor = "bg-signal-wait";

                return (
                  <div key={idx} className="space-y-1.5">
                    <div className="flex justify-between text-xs font-semibold">
                      <span className="text-primary">{tier.name}</span>
                      <span className="text-muted font-mono">{used} / {ceiling} ({Math.round(pct)}%)</span>
                    </div>
                    <div className="w-full h-3 bg-neutral-100 rounded-full overflow-hidden border border-neutral-200/50">
                      <div
                        className={`h-full rounded-full transition-all duration-500 ${barColor}`}
                        style={{ width: `${Math.min(pct, 100)}%` }}
                      />
                    </div>
                  </div>
                );
              })}

              {/* Disclaimer */}
              <div className="bg-cream/40 border border-border/80 rounded-lg p-3 flex gap-2.5 items-start text-xs text-muted mt-4">
                <HelpCircle size={15} className="text-accent shrink-0 mt-0.5" />
                <p>
                  API quotas are managed per IST day. Once the limit is hit, queries will fail or automatically throttle. Run Discovery sparingly to optimize limits.
                </p>
              </div>
            </div>

            {/* Footer */}
            <div className="px-5 py-3 border-t border-border flex justify-end bg-neutral-50">
              <button
                type="button"
                onClick={() => setIsOpen(false)}
                className="px-4 py-1.5 bg-neutral-100 hover:bg-neutral-200 transition-colors text-primary text-xs font-semibold rounded-md border border-neutral-300"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
