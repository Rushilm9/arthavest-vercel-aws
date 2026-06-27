"""
Sentiment Agent — Node function
The toughest LLM workflow: batch 50+ headlines into ONE Gemini call.
Fallback chain: Gemini Flash → FinVADER (offline).
Ref: final-arch.md Agent 4 (The Psychologist)
"""

from app.agents.state import AnalysisState
from app.agents.sentiment.tools import get_all_headlines, finvader_fallback_scoring
from app.core.horizon_params import news_days
from app.agents.sentiment.prompts import SENTIMENT_BATCH_PROMPT
from app.core.llm import get_llm, log_llm_invocation, extract_content
from app.core.model_router import get_model, ModelTier
from app.core.config import logger, settings
from app.services.failure_log import log_failure
from langchain_core.messages import HumanMessage
import json
import time


def sentiment_node(state: AnalysisState) -> dict:
    """
    LangGraph Node: Sentiment Agent.
    Batch-scores all headlines in one LLM call.
    Falls back to FinVADER if Gemini fails.
    """
    symbol = state.get("stock_symbol", "UNKNOWN")
    horizon = state.get("suggested_horizon") or state.get("final_horizon") or "MID"
    logger.info(
        f" [bold cyan]>>> Sentiment Agent: Analyzing {symbol} ({horizon})...[/bold cyan]"
    )
    start_time = time.time()
    errors: list[str] = []

    try:
        # Step 1: Gather all headlines (recency window tuned by horizon)
        headlines = get_all_headlines(symbol, horizon=horizon)

        if not headlines:
            elapsed = round(time.time() - start_time, 2)
            logger.warning(
                f" [bold yellow]⚠ Sentiment Agent: No headlines found for {symbol}. Injecting system fallback headline.[/bold yellow]"
            )
            headlines.append(
                {
                    "text": f"No recent regulatory filings or public news stories found for {symbol} in the last 7 days.",
                    "source": "system_fallback",
                    "anomaly_candidate": False,
                    "auto_trigger_debate": False,
                }
            )

        # Step 2: Format headlines for the batch prompt
        headlines_formatted = "\n".join(
            [f"{i + 1}. [{h['source']}] {h['text']}" for i, h in enumerate(headlines)]
        )

        prompt = SENTIMENT_BATCH_PROMPT.format(
            symbol=symbol,
            headline_count=len(headlines),
            headlines_formatted=headlines_formatted,
        )

        # Step 3: Call Gemini (primary)
        sentiment_result = None
        try:
            llm = get_model(
                ModelTier.FLASH,
                custom_key=state.get("_custom_api_key"),
                custom_model=state.get("_custom_model"),
            )

            # Log invocation
            log_llm_invocation(
                state.get("_custom_model") or settings.LLM_MODEL_NAME,
                symbol,
                "Sentiment Agent",
            )

            response = llm.invoke([HumanMessage(content=prompt)])
            raw = extract_content(response)
            sentiment_result = _parse_llm_response(raw)
            sentiment_result["fallback_used"] = False
        except Exception as llm_error:
            logger.warning(
                f" [bold yellow]⚠ Sentiment Agent: Gemini failed, falling back to FinVADER[/bold yellow] | Error: {llm_error}"
            )
            errors.append(
                f"Sentiment LLM failed, using FinVADER fallback: {str(llm_error)}"
            )

        # Step 4: FinVADER fallback if Gemini failed
        if sentiment_result is None:
            logger.info(
                " [bold yellow]>>> Sentiment Agent: Using FinVADER fallback...[/bold yellow]"
            )
            sentiment_result = finvader_fallback_scoring(headlines)

        # Step 5: Build output
        sentiment_output = {
            "symbol": symbol,
            "signal": sentiment_result.get("signal", "HOLD"),
            "confidence": sentiment_result.get("confidence", 0.5),
            "aggregate_score": sentiment_result.get("aggregate_score", 0.0),
            "narrative": sentiment_result.get("narrative", ""),
            "key_themes": sentiment_result.get("key_themes", []),
            "anomalies": sentiment_result.get("anomalies", []),
            "anomaly_count": sentiment_result.get("anomaly_count", 0),
            "headline_count": len(headlines),
            "fallback_used": sentiment_result.get("fallback_used", False),
            "scores": sentiment_result.get("scores", []),
            "sub_scores": sentiment_result.get("sub_scores", {}) or {},
            # Surface the horizon-tuned inputs so the debugger's "Input Data"
            # tab reflects what actually changed per horizon.
            "raw_data": {
                "horizon": horizon,
                "news_window_days": news_days(horizon),
                "headline_count": len(headlines),
                "headlines": [h.get("text") for h in headlines],
            },
        }

        elapsed = round(time.time() - start_time, 2)

        # Success log
        engine_str = "FinVADER" if sentiment_output["fallback_used"] else "Gemini"
        logger.info(
            f" [bold green]✓ Sentiment Agent Done[/bold green] | "
            f"Symbol: [white]{symbol}[/white] | "
            f"Score: [bold white]{sentiment_output['aggregate_score']:.2f}[/bold white] | "
            f"Engine: {engine_str} | "
            f"Time: {elapsed}s"
        )

        return {
            "sentiment_output": sentiment_output,
            "errors": errors,  # only newly generated errors (may include LLM fallback warning)
        }

    except Exception as e:
        # The Gemini→FinVADER inner fallback already handled the LLM-failure case.
        # Reaching here means BOTH paths failed (e.g. no headlines, FinVADER crash).
        # Re-raise so LangGraph's RetryPolicy retries the node and a true outage
        # propagates instead of feeding fake HOLD/0.5 into the Decision computation.
        elapsed = round(time.time() - start_time, 2)
        logger.error(
            f" [bold red]✗ Sentiment Agent FAILED[/bold red] | Symbol: {symbol} | Error: {e}"
        )
        log_failure(
            "agent.sentiment_node",
            "llm_invoke",
            e,
            run_id=state.get("run_id", ""),
            symbol=symbol,
            elapsed_sec=elapsed,
        )
        raise


def _parse_llm_response(raw: str) -> dict:
    """Parse Gemini's JSON response for sentiment output."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
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

        # Validate aggregate score
        agg = parsed.get("aggregate_score", 0.0)
        try:
            agg = max(-1.0, min(1.0, float(agg)))
        except (ValueError, TypeError):
            agg = 0.0
        parsed["aggregate_score"] = agg

        # Enforce anomaly override: if any anomaly <= -0.8, cap at HOLD
        anomalies = parsed.get("anomalies", [])
        if anomalies and parsed["signal"] == "BUY":
            for a in anomalies:
                if a.get("score", 0) <= -0.8:
                    parsed["signal"] = "HOLD"
                    logger.warning(
                        "[yellow]Sentiment: Anomaly override — signal capped at HOLD[/yellow]"
                    )
                    break

        return parsed

    except json.JSONDecodeError:
        logger.warning("[yellow]Sentiment Agent: Failed to parse LLM JSON[/yellow]")
        # Try to extract signal from raw text
        signal = "HOLD"
        for s in ["BUY", "SELL", "HOLD"]:
            if s in raw.upper():
                signal = s
                break
        return {
            "signal": signal,
            "confidence": 0.5,
            "aggregate_score": 0.0,
            "narrative": raw,
            "key_themes": [],
            "anomalies": [],
            "anomaly_count": 0,
        }
