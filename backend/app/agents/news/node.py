"""
News Agent — Node (F1 Stage 3)
Market-wide headline scan → market_sentiment, hot/avoid sectors, anomaly alerts.

Retry strategy: FLASH → FLASH → FLASH (3 attempts, 3s spacing). No silent
zero-sentiment fallback — a News failure that quietly emits "neutral, no
sectors" would mislead Planner/Decision downstream.
"""

import json
import re
import time
from langchain_core.messages import HumanMessage

from app.agents.state import AnalysisState
from app.agents.news.tools import fetch_market_headlines
from app.agents.news.prompts import NEWS_THEME_PROMPT
from app.core.llm import get_llm, extract_content, log_llm_invocation
from app.core.model_router import get_model, ModelTier
from app.core.config import logger, settings
from app.services.failure_log import log_failure


_MAX_ATTEMPTS = 3
_RETRY_DELAY_SECS = 3


def _is_retryable(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(
        code in msg
        for code in (
            "503",
            "429",
            "unavailable",
            "overloaded",
            "resource_exhausted",
            "high demand",
            "timeout",
            "deadline",
        )
    )


def _parse(raw: str) -> dict:
    cleaned = (raw or "").strip()
    if cleaned.startswith("```"):
        lines = [l for l in cleaned.split("\n") if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)
    candidates = [cleaned]
    first = cleaned.find("{")
    last = cleaned.rfind("}")
    if first != -1 and last != -1 and last > first:
        candidates.append(cleaned[first : last + 1])
    for cand in candidates:
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            try:
                return json.loads(re.sub(r",(\s*[}\]])", r"\1", cand))
            except json.JSONDecodeError:
                continue
    raise ValueError(
        f"News Agent: unparseable LLM JSON (len={len(raw)}): {raw[:200]!r}"
    )


import datetime

_daily_cache = {}


def news_node(state: AnalysisState) -> dict:
    logger.info(
        "[bold cyan]>>> News Agent: Scanning market-wide headlines...[/bold cyan]"
    )
    start_time = time.time()

    today = str(datetime.date.today())
    if today in _daily_cache and not state.get("_debug_mode"):
        logger.info(f"[dim]>>> News Agent: Using cached data for {today}...[/dim]")
        return dict(_daily_cache[today])

    headlines = fetch_market_headlines(limit=20)
    if not headlines:
        logger.warning(
            "[bold yellow]>>> News Agent: No market headlines available. Injecting system fallback headline.[/bold yellow]"
        )
        headlines.append(
            "No significant macro economic or market-wide news available in the last 24 hours."
        )

    prompt = NEWS_THEME_PROMPT.format(
        headline_count=len(headlines),
        headlines_formatted="\n".join(f"- {h}" for h in headlines),
    )

    last_error: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            if attempt > 0:
                logger.warning(
                    f"[yellow]News Agent: attempt {attempt + 1}/{_MAX_ATTEMPTS} "
                    f"(previous: {last_error})[/yellow]"
                )
                time.sleep(_RETRY_DELAY_SECS)

            llm = get_model(
                ModelTier.FLASH,
                custom_key=state.get("_custom_api_key"),
                custom_model=state.get("_custom_model"),
            )
            log_llm_invocation(
                state.get("_custom_model") or settings.LLM_MODEL_NAME,
                "MARKET",
                "News Agent",
            )

            response = llm.invoke([HumanMessage(content=prompt)])
            raw = extract_content(response)
            parsed = _parse(raw)

            sentiment = parsed.get("market_sentiment", 0.0)
            try:
                sentiment = max(-1.0, min(1.0, float(sentiment)))
            except (TypeError, ValueError):
                raise ValueError(
                    f"News Agent: market_sentiment not numeric: {sentiment!r}"
                )

            elapsed = round(time.time() - start_time, 2)
            tier_label = f" (retry #{attempt})" if attempt > 0 else ""
            logger.info(
                f"[bold green]>>> News Agent: sentiment={sentiment:+.2f} in {elapsed}s{tier_label}[/bold green]"
            )

            result = {
                "market_sentiment": sentiment,
                "hot_sectors": parsed.get("hot_sectors", []) or [],
                "avoid_sectors": parsed.get("avoid_sectors", []) or [],
                "anomaly_alerts": parsed.get("anomaly_alerts", []) or [],
                "news_reasoning": parsed.get(
                    "summary", "Market news sentiment is neutral with no major events."
                ),
                "errors": [],
            }
            if state.get("_debug_mode"):
                result["_debug_trace"] = {
                    "prompt_sent_to_llm": prompt,
                    "raw_llm_response": raw,
                }
            if not state.get("_debug_mode"):
                _daily_cache[today] = result
            return result

        except Exception as retry_err:
            last_error = retry_err
            if isinstance(retry_err, (json.JSONDecodeError, ValueError)):
                continue  # LLM may emit better JSON next attempt
            if not _is_retryable(retry_err):
                break  # non-transient API error, no point retrying

    # All retries exhausted — propagate. No neutral-sentiment fallback by design.
    elapsed = round(time.time() - start_time, 2)
    logger.error(
        f"[bold red]>>> News Agent: FAILED in {elapsed}s — {last_error}[/bold red]"
    )
    log_failure(
        "agent.news_node",
        "llm_invoke",
        last_error or RuntimeError("news exhausted retries"),
        run_id=state.get("run_id", ""),
        elapsed_sec=elapsed,
    )
    raise RuntimeError(
        f"News Agent failed after {_MAX_ATTEMPTS} LLM attempts: {last_error}"
    ) from last_error
