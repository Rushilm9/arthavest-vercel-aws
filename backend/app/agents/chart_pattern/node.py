"""
Chart Pattern Agent — Node (F2 Stage 1, 4th specialist)
Horizon-tuned pattern detection. Uses Gemini for the final interpretation;
the structural extraction is done in pure Python.
"""

import json
import time
from langchain_core.messages import HumanMessage

from app.agents.state import AnalysisState
from app.agents.chart_pattern.tools import get_chart_pattern_data
from app.agents.chart_pattern.prompts import CHART_PATTERN_PROMPT
from app.core.llm import get_llm, log_llm_invocation, extract_content
from app.core.model_router import get_model, ModelTier
from app.core.config import logger, settings
from app.services.failure_log import log_failure


def chart_pattern_node(state: AnalysisState) -> dict:
    symbol = state.get("stock_symbol", "UNKNOWN")
    horizon = state.get("suggested_horizon") or state.get("final_horizon") or "MID"
    logger.info(
        f"[bold cyan]>>> Chart Pattern Agent: {symbol} ({horizon})...[/bold cyan]"
    )
    start_time = time.time()
    errors: list[str] = []

    try:
        if state.get("_mock_data"):
            data = state["_mock_data"]
            logger.info(
                f" [bold yellow]Chart Pattern Agent: Using injected _mock_data for {symbol}[/bold yellow]"
            )
        else:
            data = get_chart_pattern_data(symbol, horizon=horizon)
        prompt = CHART_PATTERN_PROMPT.format(**data)

        llm = get_model(
            ModelTier.FLASH,
            custom_key=state.get("_custom_api_key"),
            custom_model=state.get("_custom_model"),
        )
        log_llm_invocation(
            state.get("_custom_model") or settings.LLM_MODEL_NAME,
            symbol,
            "Chart Pattern Agent",
        )
        response = llm.invoke([HumanMessage(content=prompt)])
        parsed = _parse(extract_content(response))

        signal = parsed.get("signal", "HOLD").upper()
        if signal not in ("BUY", "SELL", "HOLD"):
            signal = "HOLD"

        try:
            conf = float(parsed.get("confidence", 0.5))
            if conf > 1.0:
                conf = conf / 100.0
            conf = max(0.0, min(1.0, conf))
        except (TypeError, ValueError):
            conf = 0.5

        chart_output = {
            "symbol": symbol,
            "signal": signal,
            "confidence": conf,
            "narrative": parsed.get("narrative", ""),
            "patterns_detected": parsed.get("patterns_detected", []) or [],
            "sub_scores": parsed.get("sub_scores", {}) or {},
            "raw_data": data,
        }

        if state.get("_debug_mode"):
            chart_output["_debug_trace"] = {
                "prompt_sent_to_llm": prompt,
                "raw_llm_response": extract_content(response),
            }

        elapsed = round(time.time() - start_time, 2)
        logger.info(
            f"[bold green]✓ Chart Pattern Done[/bold green] | {symbol} | "
            f"Signal: {signal} | Patterns: {chart_output['patterns_detected']} | {elapsed}s"
        )
        return {"chart_pattern_output": chart_output, "errors": []}

    except Exception as e:
        elapsed = round(time.time() - start_time, 2)
        logger.error(f"[bold red]✗ Chart Pattern FAILED[/bold red] | {symbol} | {e}")
        log_failure(
            "agent.chart_pattern_node",
            "llm_invoke",
            e,
            run_id=state.get("run_id", ""),
            symbol=symbol,
            elapsed_sec=elapsed,
        )
        # Re-raise so LangGraph's RetryPolicy retries; no silent HOLD/0.0 fallback.
        raise


def _parse(raw: str) -> dict:
    cleaned = (raw or "").strip()
    if cleaned.startswith("```"):
        lines = [l for l in cleaned.split("\n") if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)
    try:
        return json.loads(cleaned)
    except Exception:
        logger.warning("[yellow]Chart Pattern: failed to parse LLM JSON[/yellow]")
        return {}
