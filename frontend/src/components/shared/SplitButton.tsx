import React, { useState, useRef, useEffect } from "react";
import { ChevronDown } from "lucide-react";
import { Spinner } from "./Spinner";

interface DropdownItem {
  label: string;
  subLabel?: string;
  onClick: () => void;
  disabled?: boolean;
}

interface SplitButtonProps {
  mainLabel: string;
  onMainClick: () => void;
  dropdownItems: DropdownItem[];
  disabled?: boolean;
  isLoading?: boolean;
  icon?: React.ReactNode;
  className?: string;
}

export function SplitButton({
  mainLabel,
  onMainClick,
  dropdownItems,
  disabled = false,
  isLoading = false,
  icon,
  className = "",
  variant = "primary",
}: SplitButtonProps & { variant?: "primary" | "secondary" }) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const buttonClass = variant === "primary"
    ? "bg-accent hover:bg-accent-dark text-white border-r border-accent-dark"
    : "bg-white hover:bg-neutral-50 text-muted hover:text-primary border border-border border-r-0";

  const triggerClass = variant === "primary"
    ? "bg-accent hover:bg-accent-dark text-white"
    : "bg-white hover:bg-neutral-50 text-muted hover:text-primary border border-border border-l-border";

  return (
    <div ref={containerRef} className={`relative inline-flex rounded-md shadow-sm ${className}`}>
      {/* Main button */}
      <button
        type="button"
        disabled={disabled || isLoading}
        onClick={onMainClick}
        className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs md:text-sm font-semibold rounded-l-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${buttonClass}`}
      >
        {isLoading ? <Spinner size="sm" className={variant === "primary" ? "border-t-transparent border-white" : ""} /> : icon}
        <span>{mainLabel}</span>
      </button>

      {/* Dropdown trigger */}
      <button
        type="button"
        disabled={disabled || isLoading}
        onClick={() => setIsOpen(!isOpen)}
        className={`inline-flex items-center px-1.5 py-1.5 text-xs md:text-sm font-semibold rounded-r-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${triggerClass}`}
        aria-haspopup="menu"
        aria-expanded={isOpen}
      >
        <ChevronDown size={16} className={`transition-transform duration-200 ${isOpen ? "rotate-180" : ""}`} />
      </button>

      {/* Dropdown items */}
      {isOpen && (
        <div className="absolute right-0 top-full mt-1.5 w-56 bg-card border border-border shadow-lg rounded-md overflow-hidden z-30 animate-in fade-in slide-in-from-top-1 duration-150">
          <ul className="py-1 text-primary text-xs md:text-sm" role="menu">
            {dropdownItems.map((item, idx) => (
              <li key={idx} role="none">
                <button
                  type="button"
                  disabled={item.disabled || disabled}
                  onClick={() => {
                    if (item.disabled || disabled) return;
                    item.onClick();
                    setIsOpen(false);
                  }}
                  className={`w-full text-left px-4 py-2 transition-colors flex flex-col items-start ${item.disabled || disabled ? "opacity-40 cursor-not-allowed" : "hover:bg-accent-soft hover:text-accent-dark"}`}
                  role="menuitem"
                >
                  <span className="font-semibold">{item.label}</span>
                  {item.subLabel && <span className="text-[10px] md:text-xs text-muted mt-0.5">{item.subLabel}</span>}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
