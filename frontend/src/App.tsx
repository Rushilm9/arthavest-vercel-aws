import { BrowserRouter, Routes, Route, useNavigate, Navigate, useLocation } from "react-router-dom";
import { Sidebar } from "./components/layout/Sidebar";
import { Header } from "./components/layout/Header";
import { BottomNav } from "./components/layout/BottomNav";
import { Dashboard } from "./pages/Dashboard";
import { Discovery } from "./pages/Discovery";
import { History } from "./pages/History";
import { Analyse } from "./pages/Analyse";
import { AnalyseDetail } from "./pages/AnalyseDetail";
import { AuditTrail } from "./pages/AuditTrail";
import { Login } from "./pages/Login";
import { useAuth } from "./context/AuthContext";
import { Spinner } from "./components/shared/Spinner";
import { ErrorBoundary } from "./components/shared/ErrorBoundary";

// Auth guard — redirects to /login if no user
function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div className="flex h-[100dvh] w-full overflow-hidden bg-cream font-sans text-primary">
        <div className="hidden md:block shrink-0 w-16 lg:w-48 pointer-events-none" />
        <div className="flex-1 flex flex-col items-center justify-center space-y-4">
          <Spinner size="lg" />
          <p className="text-xs font-bold text-primary animate-pulse tracking-wide uppercase">Authenticating...</p>
        </div>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <>{children}</>;
}

function AppContent() {
  const navigate = useNavigate();

  // Search coordination bridge:
  // When a search is triggered from header, redirect to discovery with search param
  const handleSearchSelect = (symbol: string) => {
    // If we're already on discovery, we can dispatch a custom event or navigate to trigger the query param
    navigate(`/discovery/${symbol}${window.location.search}`);
    
    // Dispatch a custom event to notify Dashboard if it's already mounted
    const event = new CustomEvent("stockSearchSelect", { detail: { symbol } });
    window.dispatchEvent(event);
  };

  return (
    <div className="flex h-[100dvh] overflow-hidden bg-cream font-sans text-primary">
      {/* 1. Desktop left sidebar navigation */}
      <Sidebar />

      {/* 2. Main content area containing Header, Body scroll, and Mobile footer */}
      <div className="flex-1 flex flex-col min-w-0 h-full relative">
        
        {/* Top Header */}
        <Header onSearchSelect={handleSearchSelect} />

        {/* Dynamic Route Body Container */}
        <main className="flex-1 overflow-y-auto px-4 py-5 pb-24 md:pb-6 scrollbar-thin">
          <div className="max-w-6xl mx-auto w-full">
            <ErrorBoundary>
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/discovery" element={<Discovery />} />
                <Route path="/discovery/:symbol" element={<Discovery />} />
                <Route path="/analyse" element={<Analyse />} />
                <Route path="/analyze/:id" element={<AnalyseDetail />} />
                <Route path="/history" element={<History />} />
                <Route path="/audit" element={<AuditTrail />} />
                <Route path="/audit/:id" element={<AuditTrail />} />
              </Routes>
            </ErrorBoundary>

            {/* Disclaimer Footer */}
            <div className="mt-8 pt-4 border-t border-border/60 text-center">
              <p className="text-[10px] sm:text-xs text-muted/70 font-semibold tracking-wide">
                ⚠️ Disclaimer: All content is AI-generated. Do check and then only take a call.
              </p>
            </div>
          </div>
        </main>

        {/* Mobile bottom navigation bar */}
        <BottomNav />

      </div>
    </div>
  );
}

// Master component wrapping AppContent inside router context
export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Login page — no sidebar/header chrome */}
        <Route path="/login" element={<Login />} />

        {/* All other routes require auth */}
        <Route
          path="/*"
          element={
            <RequireAuth>
              <AppContent />
            </RequireAuth>
          }
        />
      </Routes>
    </BrowserRouter>
  );
}
