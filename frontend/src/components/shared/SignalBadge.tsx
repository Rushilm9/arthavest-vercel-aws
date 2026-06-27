import type { Signal } from "../../types";

interface SignalBadgeProps {
  signal: Signal;
  className?: string;
  confidence?: number | null; // optional, can be 0..1 or 0..100
}

export function SignalBadge({ signal, className = "", confidence }: SignalBadgeProps) {
  const styles: Record<Signal, string> = {
    BUY: "bg-signal-buy/10 text-signal-buy border-signal-buy/30",
    SELL: "bg-signal-sell/10 text-signal-sell border-signal-sell/30",
    WAIT: "bg-signal-wait/10 text-signal-wait border-signal-wait/30",
    HOLD: "bg-signal-hold/10 text-signal-hold border-signal-hold/30",
  };

  const getConfidenceText = () => {
    if (confidence === undefined || confidence === null) return "";
    // If it's a decimal (0..1), multiply by 100
    const value = confidence <= 1 ? confidence * 100 : confidence;
    return ` · ${Math.round(value)}%`;
  };

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-bold border ${styles[signal] || "bg-signal-hold/10 text-signal-hold border-signal-hold/30"} ${className}`}
    >
      {signal}
      {getConfidenceText()}
    </span>
  );
}
