"""
Decision Agent — 3-Layer Validator (F2 Stage 4b)

Layer 1 (Hard) — Geometric correctness
  BUY:  SL < entry < target;        SELL: target < entry < SL
  Two retries to fix; otherwise FORCE WAIT.

Layer 2 (Soft) — ATR bounds + R:R floor
  Clamp SL/Target to ATR multiples; require R:R ≥ 1.3 or FORCE WAIT.

Layer 3 (Sanity) — Confidence policy
  - Dampen confidence > 0.90 down to 0.85 (overconfidence guard).
  - Apply max_decision_confidence cap (e.g., 0.70 if debate disagrees).
"""

from typing import Optional


# ── Layer 2 ATR multiples per recommendation type ─────────────────
ATR_TARGET_MULT = 4.0  # max distance to target = 4 * ATR
ATR_STOP_MULT = 2.0  # max distance to stop  = 2 * ATR
MIN_RR = 1.3


def _is_geometric_ok(rec: str, entry: float, target: float, sl: float) -> bool:
    if entry <= 0:
        return False
    if rec == "BUY":
        return sl < entry < target
    if rec == "SELL":
        return target < entry < sl
    return True  # WAIT — geometry doesn't matter


def layer1_hard(
    rec: str, entry: float, target: float, sl: float, atr: float
) -> tuple[str, float, float, float, list]:
    """
    Returns (recommendation, entry, target, sl, issues).
    Geometric correctness — up to 2 fix attempts; otherwise force WAIT.
    """
    issues: list = []
    if rec not in ("BUY", "SELL"):
        return rec, entry, target, sl, issues

    if _is_geometric_ok(rec, entry, target, sl):
        return rec, entry, target, sl, issues

    if atr <= 0:
        atr = max(entry * 0.02, 0.01)

    # Attempt 1: rebuild from ATR
    if rec == "BUY":
        new_target = round(entry + 2.5 * atr, 2)
        new_sl = round(entry - 1.5 * atr, 2)
    else:
        new_target = round(entry - 2.5 * atr, 2)
        new_sl = round(entry + 1.5 * atr, 2)

    issues.append(
        {
            "layer": 1,
            "field": "geometry",
            "action": "rebuild_from_atr",
            "before": {"entry": entry, "target": target, "sl": sl},
            "after": {"entry": entry, "target": new_target, "sl": new_sl},
            "note": "Layer 1 attempt 1 — rebuilt from ATR.",
        }
    )
    target, sl = new_target, new_sl
    if _is_geometric_ok(rec, entry, target, sl):
        return rec, entry, target, sl, issues

    # Attempt 2: nudge entry slightly off ATR
    if rec == "BUY":
        new_target = round(entry + 3.0 * atr, 2)
        new_sl = round(entry - 1.0 * atr, 2)
    else:
        new_target = round(entry - 3.0 * atr, 2)
        new_sl = round(entry + 1.0 * atr, 2)
    issues.append(
        {
            "layer": 1,
            "field": "geometry",
            "action": "rebuild_from_atr_v2",
            "before": {"entry": entry, "target": target, "sl": sl},
            "after": {"entry": entry, "target": new_target, "sl": new_sl},
            "note": "Layer 1 attempt 2.",
        }
    )
    target, sl = new_target, new_sl
    if _is_geometric_ok(rec, entry, target, sl):
        return rec, entry, target, sl, issues

    # Force WAIT
    issues.append(
        {
            "layer": 1,
            "field": "recommendation",
            "action": "force_wait",
            "before": rec,
            "after": "WAIT",
            "note": "Geometry unfixable after 2 attempts.",
        }
    )
    return "WAIT", entry, target, sl, issues


def layer2_soft(
    rec: str, entry: float, target: float, sl: float, atr: float
) -> tuple[str, float, float, float, list]:
    """ATR bound clamps + R:R floor."""
    issues: list = []
    if rec not in ("BUY", "SELL") or entry <= 0:
        return rec, entry, target, sl, issues

    if atr <= 0:
        atr = max(entry * 0.02, 0.01)

    max_target_dist = ATR_TARGET_MULT * atr
    max_stop_dist = ATR_STOP_MULT * atr

    if rec == "BUY":
        if (target - entry) > max_target_dist:
            new_target = round(entry + max_target_dist, 2)
            issues.append(
                {
                    "layer": 2,
                    "field": "target",
                    "action": "clamp_atr",
                    "before": target,
                    "after": new_target,
                    "note": f"Target > {ATR_TARGET_MULT}×ATR.",
                }
            )
            target = new_target
        if (entry - sl) > max_stop_dist:
            new_sl = round(entry - max_stop_dist, 2)
            issues.append(
                {
                    "layer": 2,
                    "field": "stop_loss",
                    "action": "clamp_atr",
                    "before": sl,
                    "after": new_sl,
                    "note": f"SL > {ATR_STOP_MULT}×ATR.",
                }
            )
            sl = new_sl
    else:  # SELL
        if (entry - target) > max_target_dist:
            new_target = round(entry - max_target_dist, 2)
            issues.append(
                {
                    "layer": 2,
                    "field": "target",
                    "action": "clamp_atr",
                    "before": target,
                    "after": new_target,
                    "note": f"Target > {ATR_TARGET_MULT}×ATR.",
                }
            )
            target = new_target
        if (sl - entry) > max_stop_dist:
            new_sl = round(entry + max_stop_dist, 2)
            issues.append(
                {
                    "layer": 2,
                    "field": "stop_loss",
                    "action": "clamp_atr",
                    "before": sl,
                    "after": new_sl,
                    "note": f"SL > {ATR_STOP_MULT}×ATR.",
                }
            )
            sl = new_sl

    # R:R floor
    reward = abs(target - entry)
    risk = abs(entry - sl)
    rr = reward / max(risk, 0.01)
    if rr < MIN_RR:
        # Repair before rejecting: the dominant failure mode is LLM geometry
        # (stop at a far support + target at a near resistance), not a bad
        # trade thesis. Rebuild from ATR (2.5x target / 1.5x stop -> R:R 1.67)
        # and only force WAIT if even that can't clear the floor.
        if rec == "BUY":
            new_target = round(entry + 2.5 * atr, 2)
            new_sl = round(entry - 1.5 * atr, 2)
        else:
            new_target = round(entry - 2.5 * atr, 2)
            new_sl = round(entry + 1.5 * atr, 2)
        new_rr = abs(new_target - entry) / max(abs(entry - new_sl), 0.01)
        if new_rr >= MIN_RR and _is_geometric_ok(rec, entry, new_target, new_sl):
            issues.append(
                {
                    "layer": 2,
                    "field": "risk_reward",
                    "action": "repair_from_atr",
                    "before": rr,
                    "after": round(new_rr, 2),
                    "rec_before": rec,
                    "note": f"R:R {rr:.2f} below floor {MIN_RR} — geometry rebuilt from ATR.",
                }
            )
            return rec, entry, new_target, new_sl, issues

        issues.append(
            {
                "layer": 2,
                "field": "risk_reward",
                "action": "force_wait",
                "before": rr,
                "after": None,
                "rec_before": rec,
                "note": f"R:R {rr:.2f} below floor {MIN_RR}.",
            }
        )
        return "WAIT", entry, target, sl, issues

    return rec, entry, target, sl, issues


def layer3_sanity(
    confidence_pct: float,
    max_decision_confidence: float = 1.0,
    debate_disagreement: bool = False,
) -> tuple[float, list]:
    """
    Dampen overconfidence and apply max_decision_confidence cap.
    Returns (confidence_pct, issues).
    """
    issues: list = []
    out = float(confidence_pct)
    cap_pct = float(max_decision_confidence) * 100.0

    # Overconfidence dampen — anything > 90 → 85 (per F2_final §11)
    if out > 90:
        issues.append(
            {
                "layer": 3,
                "field": "confidence",
                "action": "dampen",
                "before": out,
                "after": 85.0,
                "note": "Overconfidence > 90% dampened to 85%.",
            }
        )
        out = 85.0

    if debate_disagreement and out > cap_pct:
        issues.append(
            {
                "layer": 3,
                "field": "confidence",
                "action": "cap",
                "before": out,
                "after": cap_pct,
                "note": f"Debate disagreed → cap at {cap_pct:.0f}%.",
            }
        )
        out = cap_pct

    return round(out, 1), issues


def validate(
    recommendation: str,
    entry: float,
    target: float,
    sl: float,
    atr: float,
    confidence_pct: float,
    max_decision_confidence: float = 1.0,
    debate_disagreement: bool = False,
) -> dict:
    """
    Run all 3 layers in order. Returns a dict with the (possibly mutated)
    recommendation, prices, confidence, and the ordered list of issues.
    """
    issues: list = []
    rec = recommendation.upper()

    # Layer 1
    rec, entry, target, sl, l1 = layer1_hard(rec, entry, target, sl, atr)
    issues.extend(l1)

    # Layer 2 (only if still BUY/SELL after L1)
    if rec in ("BUY", "SELL"):
        rec, entry, target, sl, l2 = layer2_soft(rec, entry, target, sl, atr)
        issues.extend(l2)

    # Layer 3 — confidence policy applies regardless of recommendation
    confidence_pct, l3 = layer3_sanity(
        confidence_pct,
        max_decision_confidence=max_decision_confidence,
        debate_disagreement=debate_disagreement,
    )
    issues.extend(l3)

    status = (
        "rejected_forced_wait"
        if any(i.get("action") == "force_wait" for i in issues)
        else "accepted"
    )

    return {
        "recommendation": rec,
        "entry_price": round(entry, 2),
        "target_price": round(target, 2),
        "stop_loss": round(sl, 2),
        "confidence": confidence_pct,
        "issues": issues,
        "status": status,
    }


def compute_position_size_pct(
    confidence_pct: float,
    risk_reward: float,
    horizon: Optional[str] = "MID",
    max_pct: float = 5.0,
) -> float:
    """
    Simple POC position sizer:
        size = clamp( base * conf_factor * rr_factor, 0.5%, max_pct% )

    horizon influences the base allocation.
    """
    base = {"SHORT": 1.5, "MID": 3.0, "LONG": 4.0}.get((horizon or "MID").upper(), 3.0)
    conf_factor = max(0.0, min(1.0, float(confidence_pct) / 100.0))
    rr = max(0.5, min(3.0, float(risk_reward or 1.0)))
    rr_factor = rr / 1.5
    size = base * conf_factor * rr_factor
    return round(max(0.5, min(max_pct, size)), 2)
