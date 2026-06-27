"""
Fundamental Agent — Node function
Retrieves fundamental metrics, computes weighted score, asks Gemini for narrative.
Ref: final-arch.md Agent 3 (The Accountant)
"""

from app.agents.state import AnalysisState
from app.agents.fundamental.tools import (
    get_fundamental_data,
    compute_fundamental_score,
    score_to_signal,
)
from app.agents.fundamental.prompts import FUNDAMENTAL_NARRATIVE_PROMPT
from app.core.horizon_params import fundamental_weights
from app.core.llm import get_llm, log_llm_invocation, extract_content
from app.core.model_router import get_model, ModelTier
from app.core.config import logger, settings
from app.services.failure_log import log_failure
from langchain_core.messages import HumanMessage
import json
import time


def fundamental_node(state: AnalysisState) -> dict:
    """
    LangGraph Node: Fundamental Agent.
    Gathers fundamental data, computes weighted score, asks Gemini for narrative.
    """
    symbol = state.get("stock_symbol", "UNKNOWN")
    horizon = state.get("suggested_horizon") or state.get("final_horizon") or "MID"
    logger.info(
        f" [bold cyan]>>> Fundamental Agent: Analyzing {symbol} ({horizon})...[/bold cyan]"
    )
    start_time = time.time()
    errors: list[str] = []

    try:
        # Step 1: Gather all fundamental data (no LLM)
        data = get_fundamental_data(symbol)

        # Trigger LangGraph RetryPolicy if data fetch failed completely (MCP & fallbacks down)
        if not any(
            v is not None for k, v in data.items() if k not in ["symbol", "sector"]
        ):
            raise ValueError(
                f"Fundamental data is completely missing for {symbol} (MCP & fallbacks failed)"
            )

        # Step 2: Compute weighted score (no LLM). The raw metrics are
        # horizon-independent facts, but the WEIGHTING is horizon-aware:
        # LONG leans on quality/growth/solvency, SHORT de-emphasises them.
        weighted_score = compute_fundamental_score(data, horizon=horizon)
        base_signal = score_to_signal(weighted_score)

        # Horizon-specific framing for the narrative prompt
        _HORIZON_FOCUS = {
            "SHORT": "Focus on a SHORT-TERM (days-weeks) view: fundamentals are a "
            "secondary backstop here — flag only severe balance-sheet red flags; "
            "do not over-weight slow-moving quality/growth metrics.",
            "MID": "Focus on a MEDIUM-TERM (1-3 months) view: balance valuation, "
            "profitability, growth and balance-sheet health.",
            "LONG": "Focus on a LONG-TERM (3+ months / multi-year) view: emphasise "
            "durable quality, compounding (ROE/ROCE), growth runway, moat and "
            "balance-sheet strength; near-term valuation matters less.",
        }
        _HORIZON_WEIGHT_NOTE = {
            "SHORT": "- Solvency (Debt/Equity, Interest Coverage) and valuation (P/E) carry "
            "most weight; growth and quality are de-emphasised.",
            "MID": "- 3x: Debt/Equity, Interest Coverage  - 2x: ROE, Revenue Growth  - 1x: all others.",
            "LONG": "- 3x: Debt/Equity, Interest Coverage, ROE, Revenue Growth  "
            "- 2-2.5x: ROCE, Net Margin, Earnings Growth, Promoter Holding  - lower: P/E.",
        }

        # Step 3: Format prompt with pre-computed data
        prompt = FUNDAMENTAL_NARRATIVE_PROMPT.format(
            symbol=symbol,
            horizon=horizon,
            horizon_focus=_HORIZON_FOCUS.get(horizon, _HORIZON_FOCUS["MID"]),
            horizon_weighting_note=_HORIZON_WEIGHT_NOTE.get(
                horizon, _HORIZON_WEIGHT_NOTE["MID"]
            ),
            sector=data.get("sector", "Unknown"),
            pe_ratio=data.get("pe_ratio", "N/A"),
            price_to_book=data.get("price_to_book", "N/A"),
            ev_ebitda=data.get("ev_ebitda", "N/A"),
            roe=data.get("roe", "N/A"),
            roce=data.get("roce", "N/A"),
            roa=data.get("roa", "N/A"),
            net_margin=data.get("net_margin", "N/A"),
            operating_margin=data.get("operating_margin", "N/A"),
            revenue_growth=data.get("revenue_growth", "N/A"),
            earnings_growth=data.get("earnings_growth", "N/A"),
            debt_to_equity=data.get("debt_to_equity", "N/A"),
            current_ratio=data.get("current_ratio", "N/A"),
            interest_coverage=data.get("interest_coverage", "N/A"),
            promoter_holding=data.get("promoter_holding", "N/A"),
            institutional_holding=data.get("institutional_holding", "N/A"),
            dividend_yield=data.get("dividend_yield", "N/A"),
            market_cap_cr=data.get("market_cap_cr", "N/A"),
            weighted_score=weighted_score,
        )

        # Step 4: Call Gemini for narrative interpretation
        llm = get_model(
            ModelTier.FLASH,
            custom_key=state.get("_custom_api_key"),
            custom_model=state.get("_custom_model"),
        )

        # Log invocation
        log_llm_invocation(
            state.get("_custom_model") or settings.LLM_MODEL_NAME,
            symbol,
            "Fundamental Agent",
        )

        response = llm.invoke([HumanMessage(content=prompt)])
        raw = extract_content(response)

        # Step 5: Parse JSON response
        parsed = _parse_llm_response(raw)

        fundamental_output = {
            "symbol": symbol,
            "signal": parsed.get("signal", base_signal),
            "confidence": parsed.get("confidence", 0.5),
            "weighted_score": weighted_score,
            "narrative": parsed.get("narrative", ""),
            "strengths": parsed.get("strengths", []),
            "weaknesses": parsed.get("weaknesses", []),
            "sub_scores": parsed.get("sub_scores", {}) or {},
            "raw_data": {
                "horizon": horizon,
                "horizon_weighted_score": weighted_score,
                "scoring_weights": fundamental_weights(horizon),
                "pe_ratio": data.get("pe_ratio"),
                "roe": data.get("roe"),
                "roce": data.get("roce"),
                "debt_to_equity": data.get("debt_to_equity"),
                "revenue_growth": data.get("revenue_growth"),
                "earnings_growth": data.get("earnings_growth"),
                "net_margin": data.get("net_margin"),
                "promoter_holding": data.get("promoter_holding"),
                "market_cap_cr": data.get("market_cap_cr"),
                "sector": data.get("sector"),
            },
        }

        elapsed = round(time.time() - start_time, 2)

        # Success log
        logger.info(
            f" [bold green]✓ Fundamental Agent Done[/bold green] | "
            f"Symbol: [white]{symbol}[/white] | "
            f"Score: [bold white]{weighted_score}/40[/bold white] | "
            f"Time: {elapsed}s"
        )

        return {
            "fundamental_output": fundamental_output,
            "errors": [],
        }

    except Exception as e:
        elapsed = round(time.time() - start_time, 2)
        logger.error(
            f" [bold red]✗ Fundamental Agent FAILED[/bold red] | Symbol: {symbol} | Error: {e}"
        )
        log_failure(
            "agent.fundamental_node",
            "llm_invoke",
            e,
            run_id=state.get("run_id", ""),
            symbol=symbol,
            elapsed_sec=elapsed,
        )
        # Re-raise so LangGraph's RetryPolicy retries; no silent HOLD/0.5 fallback.
        raise


def _parse_llm_response(raw: str) -> dict:
    """Parse Gemini's JSON response, handling markdown code blocks."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)

    try:
        parsed = json.loads(cleaned)
        signal = parsed.get("signal", "HOLD").upper()
        if signal not in ("BUY", "SELL", "HOLD"):
            parsed["signal"] = "HOLD"
        else:
            parsed["signal"] = signal

        conf = parsed.get("confidence", 0.5)
        try:
            conf = float(conf)
            if conf > 1.0:
                conf = conf / 100.0  # LLM returned 65 meaning 65%, convert to 0.65
            conf = max(0.0, min(1.0, conf))
        except (ValueError, TypeError):
            conf = 0.5
        parsed["confidence"] = conf

        return parsed
    except json.JSONDecodeError:
        logger.warning("[yellow]Fundamental Agent: Failed to parse LLM JSON[/yellow]")
        signal = "HOLD"
        for s in ["BUY", "SELL", "HOLD"]:
            if s in raw.upper():
                signal = s
                break
        return {
            "signal": signal,
            "confidence": 0.5,
            "narrative": raw,
            "strengths": [],
            "weaknesses": [],
        }
