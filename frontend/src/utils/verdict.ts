import type { Signal } from "../types";

/**
 * Single source of truth for the user-facing verdict on the frontend.
 *
 * The final verdict label space is exactly BUY / SELL / WAIT. Anything neutral,
 * unknown, or legacy (HOLD) collapses to WAIT — a no-trade. Mirrors the backend
 * `app/core/verdict.py::final_verdict`.
 *
 * Do NOT use this for specialist signals (technical/fundamental/sentiment/chart)
 * or the debate's independent signal — those are sub-signals, not the verdict,
 * and a HOLD there is a meaningful neutral stance.
 */
export function toVerdict(label: unknown): Signal {
  const s = String(label ?? "").trim().toUpperCase();
  return s === "BUY" || s === "SELL" ? (s as Signal) : "WAIT";
}
