import { Link, useLocation } from "react-router-dom";
import { Compass, FileSpreadsheet, Microscope, LogOut, LayoutDashboard, GitBranch } from "lucide-react";
import { useAuth } from "../../context/AuthContext";
import logo from "../../assets/arthvest-logo.png";

export function Sidebar() {
  const location = useLocation();
  const currentPath = location.pathname;
  const { logout } = useAuth();

  const menuItems = [
    { path: "/", label: "Dashboard", icon: LayoutDashboard },
    { path: "/discovery", label: "Discovery", icon: Compass },
    { path: "/analyse", label: "Analyse", icon: Microscope },
    { path: "/history", label: "History", icon: FileSpreadsheet },
    { path: "/audit", label: "Audit Trail", icon: GitBranch },
  ];

  return (
    <aside className="hidden md:flex flex-col h-[100dvh] bg-card border-r border-border shrink-0 transition-all duration-300 w-16 lg:w-48 select-none">
      {/* Brand area */}
      <div className="flex items-center justify-center p-2 border-b border-border bg-white w-full h-16 overflow-hidden shrink-0 shadow-sm">
        <img src={logo} alt="ArthaVest Logo" className="w-full h-full object-contain" />
      </div>

      {/* Nav items */}
      <nav className="flex-1 py-4 px-2 space-y-1.5">
        {menuItems.map((item) => {
          const isActive =
            item.path === "/"
              ? currentPath === "/"
              : currentPath.startsWith(item.path);
          const Icon = item.icon;

          return (
            <Link
              key={item.path}
              to={item.path}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-xs lg:text-sm font-bold transition-all ${
                isActive
                  ? "bg-navy-soft text-navy border-l-4 border-l-navy rounded-l-none"
                  : "text-muted hover:text-primary hover:bg-neutral-50"
              }`}
              title={item.label}
            >
              <Icon size={18} className={isActive ? "text-navy" : "text-muted"} />
              <span className="hidden lg:inline">{item.label}</span>
            </Link>
          );
        })}
      </nav>

      {/* Footer: Styled Big Sign Out Button */}
      <div className="p-3 border-t border-border bg-cream/15">
        <button
          type="button"
          onClick={logout}
          className="w-full flex items-center justify-center gap-2 px-2 lg:px-3 py-2.5 bg-red-50 hover:bg-red-100 text-signal-sell hover:text-red-700 font-bold text-xs rounded-xl border border-red-100 hover:border-red-200 transition-all shadow-sm h-9"
          title="Sign Out"
        >
          <LogOut size={13} className="shrink-0" />
          <span className="hidden lg:inline">Sign Out</span>
        </button>
      </div>
    </aside>
  );
}
