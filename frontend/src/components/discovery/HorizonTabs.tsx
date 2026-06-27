import type { Horizon } from "../../types";

interface HorizonTabsProps {
  selected: Horizon;
  onChange: (horizon: Horizon) => void;
  counts: Record<Horizon, number>;
}

export function HorizonTabs({ selected, onChange, counts }: HorizonTabsProps) {
  const timeframes: { id: Horizon; label: string; desc: string }[] = [
    { id: "SHORT", label: "Short Term", desc: "1-2 weeks" },
    { id: "MID", label: "Medium Term", desc: "4-6 weeks" },
    { id: "LONG", label: "Long Term", desc: "3+ months" },
  ];

  return (
    <div className="border-b border-border flex items-center justify-between w-full">
      <div className="flex gap-1 overflow-x-auto select-none scrollbar-none">
        {timeframes.map((tf) => {
          const isSelected = selected === tf.id;
          const count = counts[tf.id] || 0;
          return (
            <button
              key={tf.id}
              type="button"
              onClick={() => onChange(tf.id)}
              className={`px-3 sm:px-4 py-2.5 border-b-2 font-semibold text-xs md:text-sm transition-all duration-150 flex items-center gap-1.5 sm:gap-2 shrink-0 ${
                isSelected
                  ? "border-accent text-accent-dark font-bold bg-white/30"
                  : "border-transparent text-muted hover:text-primary hover:border-neutral-300"
              }`}
            >
              <span>{tf.label}</span>
              <span className={`text-[10px] md:text-xs px-1.5 py-0.5 rounded-full font-mono font-bold ${
                isSelected ? "bg-accent-soft text-accent-dark" : "bg-neutral-100 text-muted"
              }`}>
                {count}
              </span>
              <span className="hidden sm:inline text-[10px] opacity-60 font-normal">({tf.desc})</span>
            </button>
          );
        })}
      </div>

    </div>
  );
}
