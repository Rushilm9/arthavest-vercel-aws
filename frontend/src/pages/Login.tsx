import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { Loader2, Eye, EyeOff, ArrowRight } from "lucide-react";
import logo from "../assets/arthvest-logo.png";

export function Login() {
  const { login, register } = useAuth();
  const navigate = useNavigate();

  const [mode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (!email.trim() || !password.trim()) {
      setError("Please fill in both fields.");
      return;
    }

    setIsSubmitting(true);
    try {
      if (mode === "login") {
        await login(email.trim(), password);
      } else {
        await register(email.trim(), password);
      }
      navigate("/", { replace: true });
    } catch (err: unknown) {
      const errorObj = err as { response?: { data?: { detail?: string } }; message?: string };
      const detail =
        errorObj?.response?.data?.detail ||
        errorObj?.message ||
        "Something went wrong. Please try again.";
      setError(detail);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleTestCredentials = async () => {
    setError("");
    const testEmail = "googl_arize_hack@gmail.com";
    const testPassword = "arize_google@1";
    setEmail(testEmail);
    setPassword(testPassword);

    setIsSubmitting(true);
    try {
      await login(testEmail, testPassword);
      navigate("/", { replace: true });
    } catch (err: unknown) {
      const errorObj = err as { response?: { data?: { detail?: string } }; message?: string };
      const detail =
        errorObj?.response?.data?.detail ||
        errorObj?.message ||
        "Something went wrong. Please try again.";
      setError(detail);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-[100dvh] flex items-center justify-center bg-cream px-4 py-8">
      {/* Subtle background decoration */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none select-none">
        <div className="absolute -top-40 -right-40 w-96 h-96 rounded-full bg-accent/5 blur-3xl" />
        <div className="absolute -bottom-40 -left-40 w-96 h-96 rounded-full bg-accent/8 blur-3xl" />
      </div>

      <div className="relative w-full max-w-md">
        {/* Brand Header */}
        <div className="text-center mb-8 bg-white p-5 rounded-2xl border border-border shadow-md">
          <img src={logo} alt="ArthaVest Logo" className="h-28 w-auto mx-auto object-contain transform scale-110" />
        </div>

        {/* Form Card */}
        <div className="bg-white border border-border rounded-2xl shadow-xl p-6 sm:p-8 space-y-6">
          {/* Registration option hidden for now */}

          {/* Error Banner */}
          {error && (
            <div className="bg-red-50 border border-red-200 text-red-800 text-xs font-semibold px-4 py-3 rounded-lg animate-in fade-in slide-in-from-top-1 duration-150">
              {error}
            </div>
          )}

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <label htmlFor="login-email" className="text-xs font-bold text-muted uppercase tracking-wider">
                Email Address
              </label>
              <input
                id="login-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                autoComplete="email"
                autoFocus
                className="w-full text-sm px-4 py-3 border border-border rounded-xl focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 transition-all font-medium text-primary placeholder:text-neutral-300"
              />
            </div>

            <div className="space-y-1.5">
              <label htmlFor="login-password" className="text-xs font-bold text-muted uppercase tracking-wider">
                Password
              </label>
              <div className="relative">
                <input
                  id="login-password"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  autoComplete={mode === "login" ? "current-password" : "new-password"}
                  className="w-full text-sm px-4 py-3 pr-12 border border-border rounded-xl focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 transition-all font-medium text-primary placeholder:text-neutral-300"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-primary transition-colors p-1"
                  tabIndex={-1}
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full flex items-center justify-center gap-2.5 px-5 py-3.5 bg-accent hover:bg-accent-dark text-white font-bold text-sm rounded-xl shadow-lg shadow-accent/25 hover:shadow-accent/35 transition-all disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {isSubmitting ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  <span>{mode === "login" ? "Signing in..." : "Creating account..."}</span>
                </>
              ) : (
                <>
                  <span>{mode === "login" ? "Sign In" : "Create Account"}</span>
                  <ArrowRight size={16} />
                </>
              )}
            </button>

            <button
              type="button"
              onClick={handleTestCredentials}
              disabled={isSubmitting}
              className="w-full flex items-center justify-center gap-2.5 px-5 py-3.5 border border-accent text-accent hover:bg-accent/5 font-bold text-sm rounded-xl transition-all disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {isSubmitting ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  <span>Loading...</span>
                </>
              ) : (
                <span>TEST CREDENTIALS</span>
              )}
            </button>
          </form>


        </div>

        {/* Footer */}
        <div className="text-center mt-6 space-y-2">
          <p className="text-[10px] text-muted/60 font-medium">
            ArthaVest Multi-Agent Intelligence · Powered by Google Gemini
          </p>
          <p className="text-[9px] sm:text-[10px] text-muted/50 font-bold max-w-xs mx-auto">
            ⚠️ Disclaimer: All content is AI-generated. Do check and then only take a call.
          </p>
        </div>
      </div>
    </div>
  );
}
