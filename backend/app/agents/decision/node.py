"""
Decision Agent — Node (F2 Stage 4 + 4b)

Stage 4: Weighted confidence (4 specialists + debate@0.30) + ATR price targets.
Stage 4b: 3-layer validator clamps geometry, ATR bounds, and confidence policy.
"""

import json
import math
import time
from langchain_core.messages import HumanMessage

from app.agents.state import AnalysisState
from app.agents.decision.tools import (
    compute_weighted_confidence,
    determine_recommendation,
    compute_price_targets,
    persist_recommendation,
)
from app.agents.decision.validator import validate, compute_position_size_pct
from app.agents.decision.prompts import DECISION_NARRATIVE_PROMPT
from app.core.verdict import final_verdict, narrative_contradicts_verdict
from app.core.model_router import (
    get_model,
    ModelTier,
    compute_cost,
    cost_usd_to_inr,
    get_model_id,
)
from app.core.llm import extract_content
from app.core.config import logger
from app.services.failure_log import log_failure

# OpenTelemetry — capture the active span ID for eval annotation (Phase 3b)
try:
    from opentelemetry import trace as _otel_trace
except ImportError:
    _otel_trace = None


_SENTINEL = object()


def _holding_period_str(horizon: str, horizon_days: int) -> str:
    """Convert horizon + days into a human-readable holding period like '2-3 Weeks'."""
    h = (horizon or "MID").upper()
    if h == "SHORT":
        if horizon_days <= 3:
            return "1-3 Days"
        elif horizon_days <= 7:
            return "3-7 Days"
        elif horizon_days <= 10:
            return "1-2 Weeks"
        else:
            return "2-3 Weeks"
    elif h == "MID":
        if horizon_days <= 30:
            return "2-4 Weeks"
        elif horizon_days <= 45:
            return "4-6 Weeks"
        elif horizon_days <= 60:
            return "1-2 Months"
        else:
            return "2-3 Months"
    else:  # LONG
        if horizon_days <= 90:
            return "1-3 Months"
        elif horizon_days <= 180:
            return "3-6 Months"
        elif horizon_days <= 365:
            return "6-12 Months"
        else:
            return "12-24 Months"


def _f(v, default=_SENTINEL):
    """Safe float extractor that handles NaN, currency symbols, and commas. Returns None if default=None and v is invalid."""
    _default = 0.0 if default is _SENTINEL else default
    if v is None:
        return _default
    if isinstance(v, (int, float)):
        return float(v)
    try:
        if isinstance(v, str):
            cleaned = v.replace("₹", "").replace("$", "").replace(",", "").strip()
            # Try to match the first number pattern in the cleaned string
            import re

            match = re.search(r"[-+]?\d*\.\d+|\d+", cleaned)
            if match:
                cleaned = match.group(0)
            f = float(cleaned)
        else:
            f = float(v)
        if math.isnan(f) or math.isinf(f):
            return _default
        return f
    except (TypeError, ValueError):
        return _default


def decision_node(state: AnalysisState) -> dict:
    symbol = state.get("stock_symbol", "UNKNOWN")
    run_id = state.get("run_id", "unknown")
    logger.info(f"[bold cyan]>>> Decision Agent: Verdict for {symbol}...[/bold cyan]")
    start_time = time.time()
    errors: list[str] = []

    # ── Capture OTel span ID for eval annotation (Phase 3b) ────
    decision_span_id = None
    if _otel_trace is not None:
        try:
            span = _otel_trace.get_current_span()
            ctx = span.get_span_context()
            if ctx and ctx.span_id:
                decision_span_id = format(ctx.span_id, "016x")
        except Exception:
            pass

    tech = state.get("technical_output", {}) or {}
    fund = state.get("fundamental_output", {}) or {}
    sent = state.get("sentiment_output", {}) or {}
    chart = state.get("chart_pattern_output", {}) or {}
    debate_output = state.get("debate_output")
    debate_triggered = state.get("debate_triggered", False)
    planner_plan = state.get("planner_plan", {}) or {}
    final_horizon = (
        state.get("final_horizon") or state.get("suggested_horizon") or "MID"
    )
    final_horizon = (final_horizon or "MID").upper()

    # ── Per-horizon weights (F1/F2 Planner output) ─────────────
    horizon_block = planner_plan.get(final_horizon, {})
    weights = horizon_block.get("agent_weights") or {}
    tech_weight = float(
        weights.get("technical", planner_plan.get("technical_weight", 0.33))
    )
    fund_weight = float(
        weights.get("fundamental", planner_plan.get("fundamental_weight", 0.34))
    )
    sent_weight = float(
        weights.get("sentiment", planner_plan.get("sentiment_weight", 0.33))
    )
    chart_weight = float(
        weights.get("chart_pattern", planner_plan.get("chart_pattern_weight", 0.0))
    )

    try:
        tech_signal = (tech.get("signal") or "HOLD").upper()
        fund_signal = (fund.get("signal") or "HOLD").upper()
        sent_signal = (sent.get("signal") or "HOLD").upper()
        chart_signal = (chart.get("signal") or "HOLD").upper()

        # ── Step 1: Confidence ─────────────────────────────────
        confidence = compute_weighted_confidence(
            tech_confidence=tech.get("confidence", 0.0),
            fund_confidence=fund.get("confidence", 0.0),
            sent_confidence=sent.get("confidence", 0.0),
            chart_confidence=chart.get("confidence", 0.0),
            tech_weight=tech_weight,
            fund_weight=fund_weight,
            sent_weight=sent_weight,
            chart_weight=chart_weight,
            debate_output=debate_output,
        )

        # ── Step 2: Recommendation ─────────────────────────────
        recommendation = determine_recommendation(
            tech_signal=tech_signal,
            fund_signal=fund_signal,
            sent_signal=sent_signal,
            chart_signal=chart_signal,
            tech_weight=tech_weight,
            fund_weight=fund_weight,
            sent_weight=sent_weight,
            chart_weight=chart_weight,
            debate_output=debate_output,
        )

        # Final verdict label space is BUY/SELL/WAIT only — any neutral/unknown
        # outcome (e.g. legacy HOLD) is a no-trade and must surface as WAIT.
        recommendation = final_verdict(recommendation)

        if confidence < 60:
            recommendation = "WAIT"
            logger.info(f"[yellow]Decision: confidence {confidence}% → WAIT[/yellow]")

        # ── Step 3: Price targets ──────────────────────────────
        raw = tech.get("raw_data", {}) or {}
        current_price = _f(raw.get("current_price"))
        atr = _f(raw.get("atr"))
        support_levels = raw.get("support_levels")
        resistance_levels = raw.get("resistance_levels")
        key_levels = raw.get("key_levels", [])

        # ATR fallback — used only when LLM fails to return valid prices
        atr_fallback = compute_price_targets(
            current_price=current_price,
            atr=atr,
            recommendation=recommendation,
            support_levels=support_levels,
            resistance_levels=resistance_levels,
        )

        # ── Step 4: LLM computes prices + narrative ────────────
        max_decision_confidence = float(state.get("max_decision_confidence", 1.0))
        debate_disagreement = bool(state.get("debate_disagreement", False))

        debate_section = "Debate ran (F2 always-on)."
        if debate_output:
            debate_section = (
                f"Bull: {debate_output.get('bull_case', 'N/A')}\n"
                f"Bear: {debate_output.get('bear_case', 'N/A')}\n"
                f"Independent: {debate_output.get('independent_signal', 'N/A')} "
                f"(agrees={debate_output.get('agrees_with_consensus', True)})\n"
                f"Synthesis: {debate_output.get('synthesis', 'N/A')}"
            )

        narrative_data = _get_narrative_from_llm(
            symbol=symbol,
            recommendation=recommendation,
            confidence=confidence,
            current_price=current_price,
            atr=atr,
            support_levels=support_levels,
            resistance_levels=resistance_levels,
            key_levels=key_levels,
            tech_output=tech,
            fund_output=fund,
            sent_output=sent,
            chart_output=chart,
            horizon=final_horizon,
            debate_section=debate_section,
            macro_regime=state.get("macro_regime", "SIDEWAYS"),
            market_pulse_score=state.get("market_pulse_score", 50),
            tech_weight=tech_weight,
            fund_weight=fund_weight,
            sent_weight=sent_weight,
            chart_weight=chart_weight,
            max_confidence=max_decision_confidence,
        )

        # WAIT — system rejected the trade, no levels should be implied
        if recommendation == "WAIT":
            price_targets = {
                "entry_price": round(current_price, 2),
                "target_price": 0.0,
                "stop_loss": 0.0,
                "risk_reward": 0.0,
                "upside_pct": 0.0,
                "risk_pct": 0.0,
                "profit_pct": 0.0,
            }
        elif current_price <= 0:
            # No market data for this ticker (yfinance failure, bad symbol, etc.)
            # Skip the LLM price call entirely — go straight to ATR fallback.
            errors.append(
                f"Decision: no market price for {symbol} — skipping LLM price call, using ATR fallback"
            )
            logger.warning(
                f"[yellow]Decision: current_price=0 for {symbol} — ATR fallback[/yellow]"
            )
            price_targets = atr_fallback
        else:
            # BUY / SELL — use LLM prices as primary; fall back to ATR-based if LLM failed.
            llm_entry = _f(narrative_data.get("entry_price"), default=None)
            llm_target = _f(narrative_data.get("target_price"), default=None)
            llm_sl = _f(narrative_data.get("stop_loss"), default=None)
            llm_prices_valid = (
                llm_entry
                and llm_entry > 0
                and llm_target
                and llm_target > 0
                and llm_sl
                and llm_sl > 0
            )

            if llm_prices_valid:
                price_targets = {
                    "entry_price": round(llm_entry, 2),
                    "target_price": round(llm_target, 2),
                    "stop_loss": round(llm_sl, 2),
                    "risk_reward": _f(narrative_data.get("risk_reward"), 0.0),
                    "upside_pct": 0.0,
                    "risk_pct": 0.0,
                    "profit_pct": 0.0,
                }
            else:
                errors.append(
                    f"Decision: LLM did not return valid prices for {symbol} — using ATR fallback"
                )
                logger.warning(
                    f"[yellow]Decision: LLM prices invalid — using ATR fallback for {symbol}[/yellow]"
                )
                price_targets = atr_fallback

        # ── Step 4b: 3-Layer Validator ─────────────────────────
        validated = validate(
            recommendation=recommendation,
            entry=price_targets["entry_price"],
            target=price_targets["target_price"],
            sl=price_targets["stop_loss"],
            atr=atr,
            confidence_pct=confidence,
            max_decision_confidence=max_decision_confidence,
            debate_disagreement=debate_disagreement,
        )
        recommendation = validated["recommendation"]
        price_targets["entry_price"] = validated["entry_price"]
        price_targets["target_price"] = validated["target_price"]
        price_targets["stop_loss"] = validated["stop_loss"]
        confidence = validated["confidence"]

        # Re-normalize after the validator — same BUY/SELL/WAIT guarantee.
        recommendation = final_verdict(recommendation)

        # Recompute R:R / upside / risk / profit % after validator clamps.
        if (
            recommendation in ("BUY", "SELL")
            and price_targets["target_price"] > 0
            and price_targets["stop_loss"] > 0
        ):
            entry_p = price_targets["entry_price"]
            target_p = price_targets["target_price"]
            sl_p = price_targets["stop_loss"]
            reward = abs(target_p - entry_p)
            risk = abs(entry_p - sl_p)
            price_targets["risk_reward"] = round(reward / max(risk, 0.01), 2)
            price_targets["upside_pct"] = round(
                ((target_p - entry_p) / max(entry_p, 0.01)) * 100, 2
            )
            price_targets["risk_pct"] = round((risk / max(entry_p, 0.01)) * 100, 2)
            # profit_pct: signed expected return on target hit (positive for BUY upside, positive for SELL downside)
            if recommendation == "SELL":
                price_targets["profit_pct"] = round(
                    ((entry_p - target_p) / max(entry_p, 0.01)) * 100, 2
                )
            else:
                price_targets["profit_pct"] = round(
                    ((target_p - entry_p) / max(entry_p, 0.01)) * 100, 2
                )
        else:
            price_targets.setdefault("profit_pct", 0.0)

        # Validator may force_wait from BUY/SELL while leaving non-zero target/SL
        # behind from the last ATR-rebuild attempt. WAIT must not imply any trade levels.
        if recommendation == "WAIT":
            price_targets["target_price"] = 0.0
            price_targets["stop_loss"] = 0.0
            price_targets["risk_reward"] = 0.0
            price_targets["upside_pct"] = 0.0
            price_targets["risk_pct"] = 0.0
            price_targets["profit_pct"] = 0.0

        # ── Narrative ↔ verdict reconciliation ─────────────────
        # The narrative LLM runs BEFORE the validator, so it sees the pre-validator
        # state. It occasionally declares a *different* decision than the final one —
        # e.g. final verdict BUY but the prose says "the final decision is to WAIT,
        # overriding the initial BUY" because it mistook the 70% confidence cap for a
        # rejection. The user then sees BUY on the badge and WAIT in the detail.
        # Final verdict is authoritative: if the prose contradicts it, prepend a
        # corrected decision sentence so the detail can never disagree with the badge.
        _narr = narrative_data.get("narrative", "") or ""
        if narrative_contradicts_verdict(_narr, recommendation):
            logger.warning(
                f"[yellow]Decision: narrative declared a different verdict than "
                f"final {recommendation} for {symbol} — correcting prose[/yellow]"
            )
            errors.append(
                f"Decision: narrative/verdict mismatch auto-corrected to {recommendation}"
            )
            if recommendation == "WAIT":
                _fix = (
                    f"<li>The final decision is to <b>WAIT</b> on {symbol} with a "
                    f"confidence of <strong>{confidence}%</strong> — no trade is "
                    f"taken at this time.</li>"
                )
            else:
                _article = "an" if recommendation[0] in "AEIOU" else "a"
                _fix = (
                    f"<li>The final decision is {_article} <b>{recommendation}</b> "
                    f"for {symbol} with a confidence of <strong>{confidence}%</strong>.</li>"
                )
            # Insert the corrected decision as the first bullet; keep the supporting
            # reasoning bullets that follow (they remain valid context).
            if "<ul>" in _narr:
                _narr = _narr.replace("<ul>", "<ul>" + _fix, 1)
            else:
                _narr = f"<ul>{_fix}</ul>" + _narr
            narrative_data["narrative"] = _narr

        # ── Position sizing ────────────────────────────────────
        position_size_pct = (
            compute_position_size_pct(
                confidence_pct=confidence,
                risk_reward=price_targets["risk_reward"],
                horizon=final_horizon,
            )
            if recommendation in ("BUY", "SELL")
            else 0.0
        )

        final_recommendation = {
            "symbol": symbol,
            "horizon": final_horizon,
            "horizon_override_reason": state.get("horizon_override_reason"),
            "recommendation": recommendation,
            "confidence": confidence,
            "entry_price": price_targets["entry_price"],
            "target_price": price_targets["target_price"],
            "stop_loss": price_targets["stop_loss"],
            "risk_reward": price_targets["risk_reward"],
            "upside_pct": price_targets["upside_pct"],
            "risk_pct": price_targets["risk_pct"],
            "profit_pct": price_targets.get("profit_pct", 0.0),
            "position_size_pct": position_size_pct,
            "timeframe": narrative_data.get(
                "timeframe", _default_timeframe(final_horizon)
            ),
            "narrative": narrative_data.get("narrative", ""),
            "key_risks": narrative_data.get("key_risks", []),
            "key_catalysts": narrative_data.get("key_catalysts", []),
            "debate_triggered": debate_triggered,
            "debate_summary": (debate_output or {}).get("synthesis", ""),
            "macro_regime": state.get("macro_regime", "SIDEWAYS"),
            "market_pulse_score": state.get("market_pulse_score", 50),
            "agent_signals": {
                "technical": tech_signal,
                "fundamental": fund_signal,
                "sentiment": sent_signal,
                "chart_pattern": chart_signal,
            },
            "validator_issues": validated["issues"],
            "validator_status": validated["status"],
            # Cost tracking (USD + INR) — populated after persist call below
            "cost_per_analysis": None,
            "cost_per_analysis_inr": None,
        }

        # ── Step 6: Persist ────────────────────────────────────
        reasoning_json = {
            "narrative": final_recommendation["narrative"],
            "key_risks": final_recommendation["key_risks"],
            "key_catalysts": final_recommendation["key_catalysts"],
            "agent_signals": final_recommendation["agent_signals"],
            "debate_triggered": debate_triggered,
            "debate_summary": final_recommendation["debate_summary"],
            "macro_regime": final_recommendation["macro_regime"],
            "market_pulse_score": final_recommendation["market_pulse_score"],
            "horizon": final_horizon,
            "horizon_override_reason": final_recommendation["horizon_override_reason"],
            "validator_issues": validated["issues"],
            "validator_status": validated["status"],
            "f1_discovery_score": state.get("_f1_discovery_score"),
            "confidence_breakdown": {
                "technical": {
                    "signal": tech_signal,
                    "confidence": tech.get("confidence", 0),
                    "weight": tech_weight,
                },
                "fundamental": {
                    "signal": fund_signal,
                    "confidence": fund.get("confidence", 0),
                    "weight": fund_weight,
                },
                "sentiment": {
                    "signal": sent_signal,
                    "confidence": sent.get("confidence", 0),
                    "weight": sent_weight,
                },
                "chart_pattern": {
                    "signal": chart_signal,
                    "confidence": chart.get("confidence", 0),
                    "weight": chart_weight,
                },
            },
        }

        # ── Cost estimate for this analysis run ───────────────
        # Approximate token counts (recalibrated 2026-05-16 — full pre-amble + F2 path):
        #   Pre-amble (re-runs on every F2 analysis):
        #     1 FLASH_LITE economic:    ~2000 in / 500 out
        #     1 FLASH news:             ~2500 in / 500 out
        #     1 PRO macro_context:      ~3500 in / 400 out
        #     1 PRO planner:            ~2500 in / 800 out
        #   F2 specialists + debate + decision:
        #     4 FLASH specialists:      ~3000 in / 600 out each
        #     1 PRO_THINK debate:       ~6000 in / 1500 out
        #     1 PRO decision narrative: ~5000 in / 1200 out
        # Recalibrate if prompts change significantly.
        flash_lite_model = get_model_id(ModelTier.FLASH_LITE)
        flash_model = get_model_id(ModelTier.FLASH)
        pro_model = get_model_id(ModelTier.PRO)
        pro_think_model = get_model_id(ModelTier.PRO_THINK)
        cost_usd_approx = (
            compute_cost(flash_lite_model, 2000, 500)  # economic
            + compute_cost(flash_model, 2500, 500)  # news
            + compute_cost(pro_model, 3500, 400)  # macro_context
            + compute_cost(pro_model, 2500, 800)  # planner
            + 4 * compute_cost(flash_model, 3000, 600)  # 4 specialists
            + compute_cost(pro_think_model, 6000, 1500)  # debate
            + compute_cost(pro_model, 5000, 1200)  # decision narrative
        )
        usd_inr_rate = float(state.get("usd_inr", 84.0) or 84.0)
        cost_inr = cost_usd_to_inr(cost_usd_approx, usd_inr_rate)

        _horizon_days_map = {"SHORT": 15, "MID": 60, "LONG": 365}

        # Build a full serialized response for lossless DB history retrieval
        def _safe_f(v):
            if v is None:
                return None
            try:
                f = float(v)
                return None if (math.isnan(f) or math.isinf(f)) else f
            except (TypeError, ValueError):
                return None

        _debate = debate_output or {}
        full_response_snapshot = {
            "symbol": symbol,
            "run_id": str(run_id),
            "recommendation": recommendation,
            "confidence": _safe_f(confidence),
            "entry_price": _safe_f(price_targets["entry_price"]),
            "target_price": _safe_f(price_targets["target_price"]),
            "stop_loss": _safe_f(price_targets["stop_loss"]),
            "risk_reward": _safe_f(price_targets["risk_reward"]),
            "upside_pct": _safe_f(price_targets.get("upside_pct")),
            "risk_pct": _safe_f(price_targets.get("risk_pct")),
            "profit_pct": _safe_f(price_targets.get("profit_pct")),
            "position_size_pct": _safe_f(position_size_pct),
            "horizon": final_horizon,
            "horizon_days": _horizon_days_map.get(final_horizon, 60),
            "holding_period": _holding_period_str(
                final_horizon, _horizon_days_map.get(final_horizon, 60)
            ),
            "timeframe": final_recommendation["timeframe"],
            "narrative": narrative_data.get("narrative", ""),
            "key_risks": narrative_data.get("key_risks", []),
            "key_catalysts": narrative_data.get("key_catalysts", []),
            "validator_status": validated["status"],
            "validator_issues": validated["issues"],
            "macro_regime": state.get("macro_regime", "SIDEWAYS"),
            "market_pulse_score": state.get("market_pulse_score", 50),
            "economic_score": state.get("economic_score"),
            "economic_regime": state.get("economic_regime"),
            "cost_per_analysis": round(cost_usd_approx, 6),
            "cost_per_analysis_inr": round(cost_inr, 2),
            "errors": errors,
            "agent_signals": {
                "technical": tech_signal,
                "fundamental": fund_signal,
                "sentiment": sent_signal,
                "chart_pattern": chart_signal,
            },
            "technical_summary": {
                "signal": tech_signal,
                "confidence": _safe_f(tech.get("confidence")),
                "narrative": tech.get("narrative") or tech.get("summary", ""),
                "key_levels": tech.get("key_levels"),
                "raw_data": tech.get("raw_data"),
                "sub_scores": tech.get("sub_scores"),
            },
            "fundamental_summary": {
                "signal": fund_signal,
                "confidence": _safe_f(fund.get("confidence")),
                "weighted_score": _safe_f(fund.get("weighted_score")),
                "narrative": fund.get("narrative") or fund.get("summary", ""),
                "strengths": fund.get("strengths") or [],
                "weaknesses": fund.get("weaknesses") or [],
                "sub_scores": fund.get("sub_scores"),
            },
            "sentiment_summary": {
                "signal": sent_signal,
                "confidence": _safe_f(sent.get("confidence")),
                "aggregate_score": _safe_f(sent.get("aggregate_score")),
                "narrative": sent.get("narrative") or sent.get("summary", ""),
                "key_themes": sent.get("key_themes") or [],
                "anomaly_count": sent.get("anomaly_count", 0),
                "headline_count": sent.get("headline_count", 0),
                "fallback_used": bool(sent.get("fallback_used", False)),
                "headlines": [
                    {
                        "text": h.get("headline", ""),
                        "score": round(float(h.get("score", 0)), 2),
                    }
                    for h in (sent.get("scores") or [])[:20]
                ],
                "sub_scores": sent.get("sub_scores"),
            },
            "chart_pattern_summary": {
                "signal": chart_signal,
                "confidence": _safe_f(chart.get("confidence")),
                "narrative": chart.get("narrative") or chart.get("summary", ""),
                "patterns_detected": chart.get("patterns_detected") or [],
                "sub_scores": chart.get("sub_scores"),
            },
            "debate_summary": {
                "triggered": True,
                "bull_case": _debate.get("bull_case"),
                "bear_case": _debate.get("bear_case"),
                "missed_risks": _debate.get("missed_risks") or [],
                "independent_signal": _debate.get("independent_signal"),
                "independent_confidence": _safe_f(
                    _debate.get("independent_confidence")
                ),
                "agrees_with_consensus": _debate.get("agrees_with_consensus"),
                "synthesis": _debate.get("synthesis"),
                "evidence_citations": _debate.get("evidence_citations") or [],
            },
            "horizon_confirmation": {
                "suggested_horizon": state.get("suggested_horizon"),
                "final_horizon": final_horizon,
                "override_reason": state.get("horizon_override_reason"),
            },
            "economic_context": {
                "score": state.get("economic_score"),
                "regime": state.get("economic_regime"),
                "positives": state.get("economic_positives") or [],
                "risks": state.get("economic_risks") or [],
                "overweight_sectors": state.get("overweight_sectors") or [],
                "underweight_sectors": state.get("underweight_sectors") or [],
            },
            "market_pulse_context": {
                "score": state.get("market_pulse_score"),
                "india_vix": state.get("india_vix"),
                "nifty_level": state.get("nifty_level"),
                "advance_decline_ratio": state.get("advance_decline_ratio"),
                "breadth_signal": state.get("breadth_signal"),
                "market_health": state.get("market_health"),
            },
            "news_context": {
                "market_sentiment": state.get("market_sentiment"),
                "hot_sectors": state.get("hot_sectors") or [],
                "avoid_sectors": state.get("avoid_sectors") or [],
                "anomaly_alerts": state.get("anomaly_alerts") or [],
            },
            "planner_context": {
                "regime": state.get("macro_regime"),
                "active_horizons": (state.get("planner_plan") or {}).get(
                    "active_horizons", []
                ),
                "overall_caution": (state.get("planner_plan") or {}).get(
                    "overall_caution"
                ),
                "horizon_strategy": (state.get("planner_plan") or {}).get(
                    final_horizon, {}
                ),
            },
        }

        rec_id = persist_recommendation(
            symbol=symbol,
            run_id=run_id,
            recommendation=recommendation,
            confidence=confidence,
            entry_price=price_targets["entry_price"],
            target_price=price_targets["target_price"],
            stop_loss=price_targets["stop_loss"],
            timeframe=final_recommendation["timeframe"],
            reasoning=reasoning_json,
            horizon=final_horizon,
            horizon_override_reason=final_recommendation["horizon_override_reason"],
            f1_horizon=state.get("_f1_horizon"),
            f1_catalyst=state.get("_f1_catalyst"),
            f1_reasoning=state.get("_f1_reasoning"),
            # Specialists (agents return 0-1 scale — do NOT divide by 100)
            technical_signal=tech_signal,
            technical_confidence=_f(tech.get("confidence", 0)),
            technical_narrative=tech.get("narrative") or tech.get("summary"),
            fundamental_signal=fund_signal,
            fundamental_confidence=_f(fund.get("confidence", 0)),
            fundamental_narrative=fund.get("narrative") or fund.get("summary"),
            sentiment_signal=sent_signal,
            sentiment_confidence=_f(sent.get("confidence", 0)),
            sentiment_narrative=sent.get("narrative") or sent.get("summary"),
            chart_signal=chart_signal,
            chart_confidence=_f(chart.get("confidence", 0)),
            chart_narrative=chart.get("narrative") or chart.get("summary"),
            # Debate
            debate_bull_case=_debate.get("bull_case"),
            debate_bear_case=_debate.get("bear_case"),
            debate_agrees=_debate.get("agrees_with_consensus"),
            debate_synthesis=_debate.get("synthesis"),
            debate_missed_risks=_debate.get("missed_risks", []),
            debate_signal=_debate.get("independent_signal"),
            debate_confidence=_f(_debate.get("independent_confidence", 0)) or None,
            # Decision (confidence is already 0-100 from compute_weighted_confidence)
            final_signal=recommendation,
            final_confidence=confidence / 100,
            key_risks=narrative_data.get("key_risks", []),
            key_catalysts=narrative_data.get("key_catalysts", []),
            agent_breakdown=reasoning_json.get("confidence_breakdown", {}),
            final_narrative=narrative_data.get("narrative", ""),
            # Validator
            validator_issues=validated["issues"],
            validator_status=validated["status"],
            # Sizing
            position_size_pct=position_size_pct,
            risk_reward=price_targets["risk_reward"],
            # Cost
            cost_per_analysis=round(cost_usd_approx, 6),
            cost_per_analysis_inr=round(cost_inr, 2),
            full_response=full_response_snapshot,
        )

        # Populate cost fields back into final_recommendation for API response
        final_recommendation["cost_per_analysis"] = round(cost_usd_approx, 6)
        final_recommendation["cost_per_analysis_inr"] = round(cost_inr, 2)

        if rec_id:
            final_recommendation["recommendation_id"] = rec_id
        else:
            errors.append("Decision: Failed to persist recommendation to DB")

        elapsed = round(time.time() - start_time, 2)
        logger.info(
            f"[bold green]>>> Decision Agent: {recommendation} @ {confidence}% "
            f"(horizon={final_horizon}, R:R={price_targets['risk_reward']}, "
            f"size={position_size_pct}%) in {elapsed}s[/bold green]"
        )

        return {
            "final_recommendation": final_recommendation,
            "validator_issues": validated["issues"],
            "validator_status": validated["status"],
            "decision_span_id": decision_span_id,
            "errors": errors,  # only new errors from this node
        }

    except Exception as e:
        elapsed = round(time.time() - start_time, 2)
        logger.error(
            f"[bold red]>>> Decision Agent: FAILED in {elapsed}s — {e}[/bold red]"
        )
        log_failure(
            "agent.decision_node",
            "verdict",
            e,
            run_id=run_id,
            symbol=symbol,
            elapsed_sec=elapsed,
        )
        # Re-raise so LangGraph's RetryPolicy retries the node and a true outage
        # propagates instead of persisting a fake HOLD/0% recommendation to the DB.
        raise


def _default_timeframe(horizon: str) -> str:
    return {
        "SHORT": "1-15 days",
        "MID": "1-3 months",
        "LONG": "6-24 months",
    }.get((horizon or "MID").upper(), "2-4 weeks")


def _get_narrative_from_llm(
    symbol: str,
    recommendation: str,
    confidence: float,
    current_price: float,
    atr: float,
    support_levels,
    resistance_levels,
    key_levels,
    tech_output: dict,
    fund_output: dict,
    sent_output: dict,
    chart_output: dict,
    horizon: str,
    debate_section: str,
    macro_regime: str,
    market_pulse_score: int,
    tech_weight: float,
    fund_weight: float,
    sent_weight: float,
    chart_weight: float,
    max_confidence: float,
) -> dict:
    try:
        prompt = DECISION_NARRATIVE_PROMPT.format(
            symbol=symbol,
            horizon=horizon,
            recommendation=recommendation,
            confidence=confidence,
            max_confidence=int(max_confidence * 100),
            current_price=round(current_price, 2),
            atr=round(atr, 2),
            support_levels=support_levels or [],
            resistance_levels=resistance_levels or [],
            key_levels=key_levels or [],
            macro_regime=macro_regime,
            market_pulse_score=market_pulse_score,
            tech_weight=round(tech_weight * 100),
            fund_weight=round(fund_weight * 100),
            sent_weight=round(sent_weight * 100),
            chart_weight=round(chart_weight * 100),
            tech_signal=tech_output.get("signal", "N/A"),
            tech_confidence=tech_output.get("confidence", 0),
            fund_signal=fund_output.get("signal", "N/A"),
            fund_score=fund_output.get("weighted_score", 0),
            fund_confidence=fund_output.get("confidence", 0),
            sent_signal=sent_output.get("signal", "N/A"),
            sent_score=sent_output.get("aggregate_score", 0),
            sent_confidence=sent_output.get("confidence", 0),
            chart_signal=chart_output.get("signal", "N/A"),
            chart_confidence=chart_output.get("confidence", 0),
            chart_patterns=chart_output.get("patterns_detected", []),
            debate_section=debate_section,
        )

        llm = get_model(ModelTier.PRO)
        response = llm.invoke([HumanMessage(content=prompt)])
        return _parse_llm_response(extract_content(response))

    except Exception as e:
        logger.warning(f"[yellow]Decision narrative LLM failed: {e}[/yellow]")
        return {
            "entry_price": None,
            "target_price": None,
            "stop_loss": None,
            "risk_reward": None,
            "narrative": f"Final recommendation for {symbol}: {recommendation} with {confidence}% confidence (horizon: {horizon}).",
            "timeframe": _default_timeframe(horizon),
            "key_risks": ["LLM narrative unavailable"],
            "key_catalysts": [],
        }


def _parse_llm_response(raw: str) -> dict:
    import re

    text = (raw or "").strip()

    # Strip code fences
    if text.startswith("```"):
        lines = [l for l in text.split("\n") if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    candidates = [text]
    # Slice from first { to last } as fallback for prose-wrapped JSON
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last != -1 and last > first:
        candidates.append(text[first : last + 1])

    for cand in candidates:
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            try:
                cleaned = re.sub(r",(\s*[}\]])", r"\1", cand)
                return json.loads(cleaned)
            except json.JSONDecodeError:
                continue

    logger.warning(
        f"[yellow]Decision Agent: failed to parse narrative JSON (len={len(raw)})[/yellow]"
    )
    return {
        "narrative": raw,
        "timeframe": "2-4 weeks",
        "key_risks": [],
        "key_catalysts": [],
    }
