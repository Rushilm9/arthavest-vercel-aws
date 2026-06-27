"""
Decision Agent — Tools (F2 Stage 4)
Pure Python math for weighted confidence + price targets.
Now includes Chart Pattern + Debate weights (per F2_final).
"""

import uuid
import datetime
from typing import Optional
from app.core.config import logger, SessionLocal
from app.db.models import Recommendations, Runs, Stocks


# Debate weight is fixed by F2_final (§10) at 0.30 — confidence blend only.
DEBATE_WEIGHT = 0.30
# The debate's VOTE on the verdict is weighted lower. At 0.30 a single
# contrarian debate signal outvoted a 2-of-4 specialist majority, which
# skewed final verdicts to ~66% WAIT. The debate's veto lives in the
# strong-dissent confidence cap (70%), not in the verdict vote.
DEBATE_VOTE_WEIGHT = 0.15


def compute_weighted_confidence(
    tech_confidence: float,
    fund_confidence: float,
    sent_confidence: float,
    chart_confidence: float,
    tech_weight: float,
    fund_weight: float,
    sent_weight: float,
    chart_weight: float,
    debate_output: Optional[dict] = None,
) -> float:
    """
    Weighted confidence (0-100) blending all 4 specialists + debate (fixed 0.30).
    """

    def _norm(c: float) -> float:
        c = float(c)
        return c / 100 if c >= 10 else min(c, 1.0)

    tech_c = _norm(tech_confidence)
    fund_c = _norm(fund_confidence)
    sent_c = _norm(sent_confidence)
    chart_c = _norm(chart_confidence)

    # Renormalize weights (they should already sum to ~1.0, but be defensive)
    total_w = max(tech_weight + fund_weight + sent_weight + chart_weight, 1e-6)
    tw = tech_weight / total_w
    fw = fund_weight / total_w
    sw = sent_weight / total_w
    cw = chart_weight / total_w

    weighted = tech_c * tw + fund_c * fw + sent_c * sw + chart_c * cw

    if debate_output:
        debate_conf = debate_output.get(
            "independent_confidence", debate_output.get("dominant_confidence", 0.5)
        )
        debate_conf = _norm(debate_conf)
        # Blend: (1 - DEBATE_WEIGHT) * specialists + DEBATE_WEIGHT * debate
        weighted = weighted * (1 - DEBATE_WEIGHT) + debate_conf * DEBATE_WEIGHT

    return max(0.0, min(100.0, round(weighted * 100, 1)))


def determine_recommendation(
    tech_signal: str,
    fund_signal: str,
    sent_signal: str,
    chart_signal: str,
    tech_weight: float,
    fund_weight: float,
    sent_weight: float,
    chart_weight: float,
    debate_output: Optional[dict] = None,
) -> str:
    """
    Final BUY/SELL/WAIT recommendation.
    Debate's independent_signal gets DEBATE_VOTE_WEIGHT of the vote.
    Specialist HOLD (their neutral stance) counts toward WAIT — the final
    verdict label space is BUY/SELL/WAIT only.
    """
    votes = {"BUY": 0.0, "SELL": 0.0, "WAIT": 0.0}

    def _vote(sig: str, w: float):
        sig = (sig or "WAIT").upper()
        if sig not in votes:
            sig = "WAIT"  # HOLD / unknown → neutral → WAIT
        votes[sig] += w

    # Specialists at (1 - DEBATE_VOTE_WEIGHT)
    spec_total = max(tech_weight + fund_weight + sent_weight + chart_weight, 1e-6)
    scale = 1 - DEBATE_VOTE_WEIGHT
    _vote(tech_signal, scale * tech_weight / spec_total)
    _vote(fund_signal, scale * fund_weight / spec_total)
    _vote(sent_signal, scale * sent_weight / spec_total)
    _vote(chart_signal, scale * chart_weight / spec_total)

    # Debate
    if debate_output:
        ind = debate_output.get(
            "independent_signal", debate_output.get("dominant_signal", "WAIT")
        )
        _vote(ind, DEBATE_VOTE_WEIGHT)

    return max(votes, key=votes.get)


def compute_price_targets(
    current_price: float,
    atr: float,
    recommendation: str,
    support_levels: list[float] | None = None,
    resistance_levels: list[float] | None = None,
) -> dict:
    """
    ATR-based price targets. Used only when LLM fails to return valid prices.
    Primary prices are computed by the Decision LLM in node.py.
    """
    import math

    if current_price is None or (
        isinstance(current_price, float)
        and (math.isnan(current_price) or math.isinf(current_price))
    ):
        current_price = 0
    if atr is None or (isinstance(atr, float) and (math.isnan(atr) or math.isinf(atr))):
        atr = 0

    if not current_price or current_price <= 0:
        return {
            "entry_price": 0,
            "target_price": 0,
            "stop_loss": 0,
            "risk_reward": 0,
            "upside_pct": 0,
            "risk_pct": 0,
            "profit_pct": 0,
        }

    if not atr or atr <= 0:
        atr = current_price * 0.02

    supports = sorted(
        [float(s) for s in (support_levels or []) if s and float(s) > 0], reverse=True
    )
    resistances = sorted(
        [float(r) for r in (resistance_levels or []) if r and float(r) > 0]
    )

    entry = current_price
    # Bound how far a chosen support/resistance may sit from price. Using the raw
    # nearest level unbounded produced absurd geometry (e.g. a stock at 14.97 with
    # nearest support at 8.65 → 42% stop → R:R 0.04). If the nearest real level is
    # farther than this ATR band, fall back to an ATR-based level instead.
    _MAX_STOP_DIST = 2.0 * atr  # mirrors validator ATR_STOP_MULT
    _MAX_TGT_DIST = 4.0 * atr  # mirrors validator ATR_TARGET_MULT

    if recommendation == "BUY":
        target = next(
            (
                round(r, 2)
                for r in resistances
                if current_price * 1.01 < r <= current_price + _MAX_TGT_DIST
            ),
            None,
        )
        if not target:
            target = round(entry + 2.5 * atr, 2)
        stop_loss = next(
            (
                round(s, 2)
                for s in supports
                if current_price * 0.99 > s >= current_price - _MAX_STOP_DIST
            ),
            None,
        )
        if not stop_loss:
            stop_loss = round(entry - 1.5 * atr, 2)
    elif recommendation == "SELL":
        target = next(
            (
                round(s, 2)
                for s in supports
                if current_price * 0.99 > s >= current_price - _MAX_TGT_DIST
            ),
            None,
        )
        if not target:
            target = round(entry - 2.5 * atr, 2)
        stop_loss = next(
            (
                round(r, 2)
                for r in resistances
                if current_price * 1.01 < r <= current_price + _MAX_STOP_DIST
            ),
            None,
        )
        if not stop_loss:
            stop_loss = round(entry + 1.5 * atr, 2)
    else:
        # WAIT or unknown — no levels.
        return {
            "entry_price": round(entry, 2),
            "target_price": 0.0,
            "stop_loss": 0.0,
            "risk_reward": 0.0,
            "upside_pct": 0.0,
            "risk_pct": 0.0,
            "profit_pct": 0.0,
        }

    reward = abs(target - entry)
    risk = abs(entry - stop_loss)
    risk_reward = round(reward / max(risk, 0.01), 2)
    upside_pct = round(((target - entry) / max(entry, 0.01)) * 100, 2)
    risk_pct = round((risk / max(entry, 0.01)) * 100, 2)
    profit_pct = (
        round(((target - entry) / max(entry, 0.01)) * 100, 2)
        if recommendation == "BUY"
        else round(((entry - target) / max(entry, 0.01)) * 100, 2)
    )

    return {
        "entry_price": round(entry, 2),
        "target_price": target,
        "stop_loss": max(stop_loss, 0.01),
        "risk_reward": risk_reward,
        "upside_pct": upside_pct,
        "risk_pct": risk_pct,
        "profit_pct": profit_pct,
    }


def persist_recommendation(
    symbol: str,
    run_id: str,
    recommendation: str,
    confidence: float,
    entry_price: float,
    target_price: float,
    stop_loss: float,
    timeframe: str,
    reasoning: dict,
    horizon: Optional[str] = None,
    horizon_override_reason: Optional[str] = None,
    # F1 pass-through
    f1_horizon: Optional[str] = None,
    f1_catalyst: Optional[str] = None,
    f1_reasoning: Optional[str] = None,
    # Specialist agent signals
    technical_signal: Optional[str] = None,
    technical_confidence: Optional[float] = None,
    technical_narrative: Optional[str] = None,
    fundamental_signal: Optional[str] = None,
    fundamental_confidence: Optional[float] = None,
    fundamental_narrative: Optional[str] = None,
    sentiment_signal: Optional[str] = None,
    sentiment_confidence: Optional[float] = None,
    sentiment_narrative: Optional[str] = None,
    chart_signal: Optional[str] = None,
    chart_confidence: Optional[float] = None,
    chart_narrative: Optional[str] = None,
    # Debate
    debate_bull_case: Optional[str] = None,
    debate_bear_case: Optional[str] = None,
    debate_agrees: Optional[bool] = None,
    debate_synthesis: Optional[str] = None,
    debate_missed_risks: Optional[list] = None,
    debate_signal: Optional[str] = None,
    debate_confidence: Optional[float] = None,
    # Decision / final
    final_signal: Optional[str] = None,
    final_confidence: Optional[float] = None,
    key_risks: Optional[list] = None,
    key_catalysts: Optional[list] = None,
    agent_breakdown: Optional[dict] = None,
    final_narrative: Optional[str] = None,
    horizon_days: Optional[int] = None,
    # Validator
    validator_issues: Optional[list] = None,
    validator_status: Optional[str] = None,
    # Sizing
    position_size_pct: Optional[float] = None,
    risk_reward: Optional[float] = None,
    # Cost
    cost_per_analysis: Optional[float] = None,
    cost_per_analysis_inr: Optional[float] = None,
    usd_inr: float = 84.0,
    # Full serialized response for lossless history retrieval
    full_response: Optional[dict] = None,
) -> Optional[str]:
    """Persist final recommendation with all F2 columns."""
    db = SessionLocal()
    try:
        stock = db.query(Stocks).filter(Stocks.symbol == symbol.upper()).first()
        if not stock:
            stock = Stocks(
                id=uuid.uuid4(),
                symbol=symbol.upper(),
                name=symbol.upper(),
                exchange="NSE",
            )
            db.add(stock)
            db.flush()

        # graph.py::run_analysis_pipeline writes a STARTED Runs row at pipeline start.
        # Reuse it if present (so Debug page sees one row per run, not two); otherwise
        # insert one here for the legacy code path that calls persist_recommendation
        # without the graph wrapper.
        rid = uuid.UUID(run_id) if isinstance(run_id, str) else run_id
        run = db.query(Runs).filter(Runs.id == rid).first()
        if run is None:
            run = Runs(
                id=rid,
                stock_id=stock.id,
                workflow_name="analysis_pipeline",
                workflow_config={"task": "analyze", "symbol": symbol},
                status="COMPLETED",
                started_at=datetime.datetime.utcnow(),
                completed_at=datetime.datetime.utcnow(),
            )
            db.add(run)
            db.flush()
        else:
            # Attach the stock_id (only known at decision-time) and mark completed.
            run.stock_id = stock.id
            run.status = "COMPLETED"
            run.completed_at = datetime.datetime.utcnow()
            db.flush()

        _horizon_days_map = {"SHORT": 15, "MID": 60, "LONG": 365}
        computed_horizon_days = horizon_days or _horizon_days_map.get(
            (horizon or "MID").upper(), 60
        )

        rec = Recommendations(
            id=uuid.uuid4(),
            run_id=run.id,
            stock_id=stock.id,
            recommendation=recommendation,
            confidence=confidence,
            entry_price=entry_price,
            target_price=target_price,
            stop_loss=stop_loss,
            timeframe=timeframe,
            status="ACTIVE",
            reasoning=reasoning,
            expires_at=datetime.datetime.utcnow()
            + datetime.timedelta(days=computed_horizon_days),
            created_at=datetime.datetime.utcnow(),
            # Horizon
            horizon=horizon,
            horizon_override_reason=horizon_override_reason,
            horizon_days=computed_horizon_days,
            # F1 pass-through
            f1_horizon=f1_horizon,
            f1_catalyst=f1_catalyst,
            f1_reasoning=f1_reasoning,
            # Specialists
            technical_signal=technical_signal,
            technical_confidence=technical_confidence,
            technical_narrative=technical_narrative,
            fundamental_signal=fundamental_signal,
            fundamental_confidence=fundamental_confidence,
            fundamental_narrative=fundamental_narrative,
            sentiment_signal=sentiment_signal,
            sentiment_confidence=sentiment_confidence,
            sentiment_narrative=sentiment_narrative,
            chart_signal=chart_signal,
            chart_confidence=chart_confidence,
            chart_narrative=chart_narrative,
            # Debate
            debate_bull_case=debate_bull_case,
            debate_bear_case=debate_bear_case,
            debate_agrees=debate_agrees,
            debate_synthesis=debate_synthesis,
            debate_missed_risks=debate_missed_risks or [],
            debate_signal=debate_signal,
            debate_confidence=debate_confidence,
            # Decision
            final_signal=final_signal or recommendation,
            final_confidence=final_confidence or confidence,
            key_risks=key_risks or [],
            key_catalysts=key_catalysts or [],
            agent_breakdown=agent_breakdown or {},
            final_narrative=final_narrative,
            # Validator
            validator_issues=validator_issues or [],
            validator_status=validator_status,
            # Sizing
            position_size_pct=position_size_pct,
            risk_reward=risk_reward,
            # Cost
            cost_per_analysis=cost_per_analysis,
            cost_per_analysis_inr=cost_per_analysis_inr,
            # Full response snapshot
            full_response=full_response,
        )
        db.add(rec)
        db.commit()
        logger.info(
            f"[bold green]Decision: Persisted {rec.id} ({recommendation}) for {symbol}[/bold green]"
        )
        return str(rec.id)

    except Exception as e:
        db.rollback()
        logger.error(f"[bold red]Decision: DB persistence failed — {e}[/bold red]")
        return None
    finally:
        db.close()
