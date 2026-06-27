// ── Global Configuration ──────────────────────────────────────────
// The central configuration file for the ArthaVest frontend.
// The entire application routes all traffic using this single URL.

const rawUrl = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export const config = {
  // Update this single value to point to your backend.
  // Local development: "http://localhost:8000"
  // Network / mobile testing: "http://192.168.1.15:8000"
  API_BASE_URL: rawUrl.endsWith("/") ? rawUrl.slice(0, -1) : rawUrl,
};
