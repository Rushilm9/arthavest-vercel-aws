"""
Economic Agent — Node (F1 Stage 1)
Pulls a macro indicator basket and asks Gemini to classify regime + sector tilts.
"""

import json
import time
from langchain_core.messages import HumanMessage

from app.agents.state import AnalysisState
from app.agents.economic.tools import fetch_economic_indicators
from app.agents.economic.prompts import ECONOMIC_REGIME_PROMPT
from app.core.model_router import get_model, ModelTier
from app.core.llm import extract_content
from app.core.config import logger
from app.services.failure_log import log_failure
from app.services.discovery_persist import persist_economic_snapshot


import datetime

_daily_cache = {}


def economic_node(state: AnalysisState) -> dict:
    logger.info(
        "[bold cyan]>>> Economic Agent: Pulling macro indicators...[/bold cyan]"
    )
    start_time = time.time()
    errors: list[str] = []

    today = str(datetime.date.today())
    if today in _daily_cache:
        logger.info(f"[dim]>>> Economic Agent: Using cached data for {today}...[/dim]")
        return dict(_daily_cache[today])

    fallback = {
        "economic_score": 50,
        "economic_regime": "STABLE",
        "overweight_sectors": [],
        "underweight_sectors": [],
        "economic_positives": [],
        "economic_risks": [],
    }

    try:
        indicators = fetch_economic_indicators()
        prompt = ECONOMIC_REGIME_PROMPT.format(**indicators)
        llm = get_model(ModelTier.FLASH_LITE)
        response = llm.invoke([HumanMessage(content=prompt)])
        parsed = _parse(extract_content(response))

        regime = parsed.get("economic_regime", "STABLE").upper()
        if regime not in ("EXPANSION", "STABLE", "SLOWING", "CONTRACTION"):
            regime = "STABLE"

        score = int(parsed.get("economic_score", 50))
        score = max(0, min(100, score))

        elapsed = round(time.time() - start_time, 2)
        logger.info(
            f"[bold green]>>> Economic Agent: {regime} (score {score}) in {elapsed}s[/bold green]"
        )

        # Only persist in discovery mode (F1); F2 runs re-use the same indicators
        if state.get("task") == "discover":
            try:
                persist_economic_snapshot(indicators, score, regime)
            except Exception as _pe:
                logger.warning(
                    f"[yellow]Economic Agent: snapshot persist failed — {_pe}[/yellow]"
                )

        result = {
            "economic_score": score,
            "economic_regime": regime,
            "overweight_sectors": parsed.get("overweight_sectors", []) or [],
            "underweight_sectors": parsed.get("underweight_sectors", []) or [],
            "economic_positives": parsed.get("positives", []) or [],
            "economic_risks": parsed.get("risks", []) or [],
            "economic_reasoning": parsed.get(
                "reasoning",
                "Economic regime is stable with no major stresses detected.",
            ),
            "_economic_indicators": indicators,
            "errors": [],
        }
        _daily_cache[today] = result
        return result

    except Exception as e:
        elapsed = round(time.time() - start_time, 2)
        errors.append(f"Economic Agent failed: {e}")
        logger.error(
            f"[bold red]>>> Economic Agent: FAILED in {elapsed}s — {e}[/bold red]"
        )
        log_failure(
            "agent.economic_node",
            "llm_invoke",
            e,
            run_id=state.get("run_id", ""),
            elapsed_sec=elapsed,
        )
        return {**fallback, "_economic_indicators": None, "errors": errors}


def _parse(raw: str) -> dict:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = [l for l in cleaned.split("\n") if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)
    try:
        return json.loads(cleaned)
    except Exception:
        logger.warning("[yellow]Economic Agent: could not parse LLM JSON[/yellow]")
        return {}
