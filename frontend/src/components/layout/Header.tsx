import React, { useState, useRef, useEffect } from "react";
import { useSymbolSearch } from "../../hooks/useSymbolSearch";
import { useAuth } from "../../context/AuthContext";
import { Search, Loader2, Sparkles, X, LogOut } from "lucide-react";
import logo from "../../assets/arthvest-logo.png";

interface HeaderProps {
  onSearchSelect: (symbol: string) => void;
}

export function Header({ onSearchSelect }: HeaderProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [showDropdown, setShowDropdown] = useState(false);
  const [showProfileCard, setShowProfileCard] = useState(false);
  
  const dropdownRef = useRef<HTMLDivElement>(null);
  const profileCardRef = useRef<HTMLDivElement>(null);
  
  const { data: suggestions, isLoading } = useSymbolSearch(searchQuery);
  const { user, logout } = useAuth();

  // Close dropdowns on click outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setShowDropdown(false);
      }
      if (profileCardRef.current && !profileCardRef.current.contains(event.target as Node)) {
        setShowProfileCard(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleSelect = (symbol: string) => {
    onSearchSelect(symbol.toUpperCase());
    setSearchQuery("");
    setShowDropdown(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && searchQuery.trim().length > 0) {
      if (suggestions && suggestions.length > 0) {
        handleSelect(suggestions[0].symbol);
      } else {
        handleSelect(searchQuery.trim());
      }
    }
  };

  const getISTDate = () => {
    const options: Intl.DateTimeFormatOptions = {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      timeZone: "Asia/Kolkata",
    };
    return new Date().toLocaleString("en-US", options) + " IST";
  };

  const getUserName = (email: string) => {
    const localPart = email.split("@")[0];
    if (localPart.toLowerCase() === "rushilmehta") {
      return "Rushil Mehta";
    }
    return localPart
      .split(/[._-]/)
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
      .join(" ");
  };

  const getInitials = (email: string) => {
    const name = getUserName(email);
    const parts = name.split(" ");
    if (parts.length >= 2) {
      return (parts[0].charAt(0) + parts[1].charAt(0)).toUpperCase();
    }
    return name.slice(0, 2).toUpperCase();
  };



  return (
    <header className="h-14 bg-card border-b border-border px-3 sm:px-4 flex items-center justify-between z-40 select-none shadow-sm gap-2 sm:gap-4 shrink-0">

      {/* Mobile Brand Label */}
      <div className="flex items-center gap-2 md:hidden shrink-0">
        <img src={logo} alt="ArthaVest Logo" className="h-10 w-auto object-contain shrink-0 transform scale-[1.15]" />
      </div>

      {/* Date Indicator (Desktop Only) */}
      <div className="hidden md:flex items-center gap-1.5 text-xs text-muted font-bold font-mono">
        <Sparkles size={13} className="text-accent" />
        <span>{getISTDate()}</span>
      </div>

      {/* Center Search typeahead bar */}
      <div ref={dropdownRef} className="relative flex-1 max-w-sm md:max-w-md">
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
          <input
            type="text"
            placeholder="Search equity symbol (e.g. INFY, TCS)..."
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setShowDropdown(true);
            }}
            onFocus={() => setShowDropdown(true)}
            onKeyDown={handleKeyDown}
            className="w-full text-xs md:text-sm pl-9 pr-8 py-1.5 md:py-2 border border-border rounded-lg focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/20 transition-all font-semibold text-primary font-mono placeholder:font-sans uppercase"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted hover:text-primary transition-colors"
            >
              <X size={14} />
            </button>
          )}
          {isLoading && (
            <div className="absolute right-8 top-1/2 -translate-y-1/2">
              <Loader2 size={13} className="animate-spin text-accent" />
            </div>
          )}
        </div>

        {/* Suggestions list dropdown */}
        {showDropdown && searchQuery.trim().length > 0 && (
          <div className="absolute left-0 right-0 top-full mt-1.5 bg-card border border-border shadow-xl rounded-lg overflow-hidden z-50 animate-in fade-in slide-in-from-top-1 duration-150 max-h-56 overflow-y-auto font-mono">
            {suggestions && suggestions.length > 0 ? (
              <ul className="py-1">
                {suggestions.map((item, idx) => (
                  <li key={idx}>
                    <button
                      type="button"
                      onClick={() => handleSelect(item.symbol)}
                      className="w-full text-left px-4 py-2 hover:bg-accent-soft hover:text-accent-dark transition-colors flex justify-between items-center text-xs md:text-sm font-bold"
                    >
                      <span className="text-primary">{item.symbol}</span>
                      <span className="text-[10px] md:text-xs text-muted font-sans font-medium truncate ml-3 max-w-[200px]">
                        {item.name}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : !isLoading ? (
              <div className="px-4 py-3 text-xs text-muted text-center font-sans">
                No matching symbols. Press <strong className="font-mono bg-neutral-100 px-1 rounded text-primary">Enter</strong> to analyze ad-hoc.
              </div>
            ) : null}
          </div>
        )}
      </div>

      {/* Right: WebSocket Status + Sim Trigger + Quota + User Dropdown */}
      <div className="flex items-center gap-2 sm:gap-3 shrink-0">
        
        {/* Live WebSocket Status Indicator removed as per user request */}



        {/* Clickable User profile avatar with dropdown card */}
        {user && (
          <div ref={profileCardRef} className="relative flex items-center border-l border-border pl-2 sm:pl-3">
            <button
              onClick={() => setShowProfileCard(!showProfileCard)}
              className={`w-9 h-9 rounded-full flex items-center justify-center font-black text-sm uppercase shrink-0 transition-all shadow-sm font-mono border ${
                showProfileCard
                  ? "bg-navy border-navy text-white ring-4 ring-navy/15"
                  : "bg-navy/10 border-navy/20 text-navy hover:bg-navy/20"
              }`}
              title="View Account Details"
            >
              {getInitials(user.email)}
            </button>

            {/* Profile Detail Dropdown Card */}
            {showProfileCard && (
              <div className="absolute right-0 top-full mt-2 w-64 bg-white border border-border shadow-2xl rounded-xl overflow-hidden z-50 animate-in fade-in slide-in-from-top-1 duration-150 p-4 space-y-4">
                {/* User Info Header */}
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-full bg-navy text-white flex items-center justify-center font-black text-xs uppercase shadow">
                    {getInitials(user.email)}
                  </div>
                  <div className="leading-none min-w-0 flex-1">
                    <h4 className="text-xs font-black text-primary truncate leading-tight">
                      {getUserName(user.email)}
                    </h4>
                    <p className="text-[10px] text-muted font-mono font-semibold truncate mt-1">
                      {user.email}
                    </p>
                  </div>
                </div>

                {/* Account details */}
                <div className="border-t border-neutral-100 pt-3 flex items-center justify-between">
                  <span className="text-[10px] text-muted font-semibold uppercase tracking-wider">Trading Role</span>
                  <span className="text-navy bg-navy/10 border border-navy/20 px-2 py-0.5 rounded-full text-[9px] font-black uppercase tracking-wider">
                    PRO TRADER
                  </span>
                </div>

                {/* High Fidelity Sign Out Button inside Card */}
                <button
                  type="button"
                  onClick={() => {
                    setShowProfileCard(false);
                    logout();
                  }}
                  className="w-full flex items-center justify-center gap-2 px-3 py-2.5 bg-red-50 hover:bg-red-100 text-signal-sell hover:text-red-700 font-bold text-xs rounded-xl border border-red-100 hover:border-red-200 transition-all shadow-sm"
                >
                  <LogOut size={12} />
                  <span>Sign Out Account</span>
                </button>
              </div>
            )}
          </div>
        )}
      </div>

    </header>
  );
}


