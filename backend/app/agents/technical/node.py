"""
Technical Agent — Node function
Retrieves 3Y OHLCV + live indicators, computes pivots/S&R, asks Gemini for narrative.
Ref: final-arch.md Agent 2 (The Chart Reader)
"""

from app.agents.state import AnalysisState
from app.agents.technical.tools import get_technical_data
from app.agents.technical.prompts import TECHNICAL_NARRATIVE_PROMPT
from app.core.llm import get_llm, log_llm_invocation, extract_content
from app.core.model_router import get_model, ModelTier
from app.core.config import logger, settings
from app.services.failure_log import log_failure
from langchain_core.messages import HumanMessage
import json
import time


def technical_node(state: AnalysisState) -> dict:
    """
    LangGraph Node: Technical Agent.
    Retrieves all technical data via tools, then asks Gemini for narrative + signal.
    """
    symbol = state.get("stock_symbol", "UNKNOWN")
    horizon = state.get("suggested_horizon") or state.get("final_horizon") or "MID"
    logger.info(
        f" [bold cyan]>>> Technical Agent: Analyzing {symbol} ({horizon})...[/bold cyan]"
    )
    start_time = time.time()
    errors: list[str] = []

    try:
        # Step 1: Gather all technical data (no LLM)
        if state.get("_mock_data"):
            data = state["_mock_data"]
            logger.info(
                f" [bold yellow]Technical Agent: Using injected _mock_data for {symbol}[/bold yellow]"
            )
        else:
            data = get_technical_data(symbol, horizon=horizon)

        if data.get("current_price") is None:
            raise ValueError(f"No price data available for {symbol}")

        # Step 2: Format prompt with pre-computed data
        prompt = TECHNICAL_NARRATIVE_PROMPT.format(
            symbol=symbol,
            current_price=data.get("current_price", "N/A"),
            atr=data.get("atr", "N/A"),
            ema20=data.get("ema20", "N/A"),
            ema50=data.get("ema50", "N/A"),
            ema200=data.get("ema200", "N/A"),
            price_vs_ema20=data.get("price_vs_ema20", "N/A"),
            price_vs_ema50=data.get("price_vs_ema50", "N/A"),
            price_vs_ema200=data.get("price_vs_ema200", "N/A"),
            rsi=data.get("rsi", "N/A"),
            rsi7=data.get("rsi7", "N/A"),
            macd=data.get("macd", "N/A"),
            adx=data.get("adx", "N/A"),
            stoch_k=data.get("stoch_k", "N/A"),
            stoch_d=data.get("stoch_d", "N/A"),
            cci=data.get("cci", "N/A"),
            momentum=data.get("momentum", "N/A"),
            bb_upper=data.get("bb_upper", "N/A"),
            bb_lower=data.get("bb_lower", "N/A"),
            vwap=data.get("vwap", "N/A"),
            resistance_levels=data.get("resistance_levels", []),
            support_levels=data.get("support_levels", []),
            high_52w=data.get("high_52w", "N/A"),
            low_52w=data.get("low_52w", "N/A"),
            dist_from_high=data.get("dist_from_high", "N/A"),
            perf_w=data.get("perf_w", "N/A"),
            perf_1m=data.get("perf_1m", "N/A"),
            perf_3m=data.get("perf_3m", "N/A"),
            perf_6m=data.get("perf_6m", "N/A"),
            perf_y=data.get("perf_y", "N/A"),
            return_window_days=data.get("return_window_days", "N/A"),
            stock_3m_return=data.get("stock_3m_return", "N/A"),
            nifty_3m_return=data.get("nifty_3m_return", "N/A"),
            relative_strength=data.get("relative_strength", "N/A"),
            trading_days=data.get("trading_days", 0),
        )

        # Step 3: Call Gemini for narrative interpretation
        llm = get_model(
            ModelTier.FLASH,
            custom_key=state.get("_custom_api_key"),
            custom_model=state.get("_custom_model"),
        )

        # Log invocation
        log_llm_invocation(
            state.get("_custom_model") or settings.LLM_MODEL_NAME,
            symbol,
            "Technical Agent",
        )

        response = llm.invoke([HumanMessage(content=prompt)])
        raw = extract_content(response)

        # Step 4: Parse JSON response
        parsed = _parse_llm_response(raw)

        technical_output = {
            "symbol": symbol,
            "signal": parsed.get("signal", "HOLD"),
            "confidence": parsed.get("confidence", 0.5),
            "narrative": parsed.get("narrative", ""),
            "key_levels": parsed.get("key_levels", {}),
            "sub_scores": parsed.get("sub_scores", {}) or {},
            "raw_data": data,  # Pass ALL indicators through
        }

        if state.get("_debug_mode"):
            technical_output["_debug_trace"] = {
                "prompt_sent_to_llm": prompt,
                "raw_llm_response": raw,
            }

        elapsed = round(time.time() - start_time, 2)

        # Success log
        logger.info(
            f" [bold green]✓ Technical Agent Done[/bold green] | "
            f"Symbol: [white]{symbol}[/white] | "
            f"Signal: [bold white]{technical_output['signal']}[/bold white] | "
            f"Time: {elapsed}s"
        )

        return {
            "technical_output": technical_output,
            "errors": [],
        }

    except Exception as e:
        elapsed = round(time.time() - start_time, 2)
        logger.error(
            f" [bold red]✗ Technical Agent FAILED[/bold red] | Symbol: {symbol} | Error: {e}"
        )
        log_failure(
            "agent.technical_node",
            "llm_invoke",
            e,
            run_id=state.get("run_id", ""),
            symbol=symbol,
            elapsed_sec=elapsed,
        )
        # Re-raise so LangGraph's RetryPolicy(max_attempts=3) retries the node.
        # On exhausted retries the F2 run hard-fails — no silent HOLD/0.5 fallback that
        # would feed fake signals into the weighted Decision computation.
        raise


def _parse_llm_response(raw: str) -> dict:
    """
    Parse Gemini's JSON response, handling markdown code blocks.
    """
    # Strip markdown code fences if present
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove first and last lines (```json and ```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)

    try:
        parsed = json.loads(cleaned)
        # Validate signal
        signal = parsed.get("signal", "HOLD").upper()
        if signal not in ("BUY", "SELL", "HOLD"):
            parsed["signal"] = "HOLD"
        else:
            parsed["signal"] = signal

        # Validate confidence
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
        logger.warning(
            f"[yellow]Technical Agent: Failed to parse LLM JSON, extracting signal manually[/yellow]"
        )
        # Fallback: try to extract signal from raw text
        signal = "HOLD"
        for s in ["BUY", "SELL", "HOLD"]:
            if s in raw.upper():
                signal = s
                break
        return {
            "signal": signal,
            "confidence": 0.5,
            "narrative": raw,
            "key_levels": {},
        }
