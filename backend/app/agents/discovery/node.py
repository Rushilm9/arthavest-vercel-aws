"""
Discovery Agent — Node (F1 Stages 6-8)
Stage 6: Hard filters (in tools.broad_scan)
Stage 7: 3-signature broad scan (in tools.broad_scan)
Stage 8: LLM classify + rank into SHORT/MID/LONG buckets (here)
"""

import json
import time
import concurrent.futures

from langchain_core.messages import HumanMessage
from app.agents.state import AnalysisState
from app.agents.discovery.tools import scan_market
from app.agents.discovery.prompts import DISCOVERY_CLASSIFY_RANK_PROMPT
from app.core.model_router import get_model, ModelTier
from app.core.llm import extract_content
from app.core.config import logger, settings
from app.services.run_log import log_agent_run


def discovery_node(state: AnalysisState) -> dict:
    logger.info(
        "[bold cyan]>>> Discovery Agent: Broad scan + classify+rank...[/bold cyan]"
    )
    start_time = time.time()
    errors: list[str] = []

    planner_plan = state.get("planner_plan", {})
    active_horizons = planner_plan.get("active_horizons", ["SHORT", "MID", "LONG"])
    # User-level horizon filter from POST /analysis/discover?horizon=SHORT.
    # USER WINS: this is a manual-mode app — the user clicked SHORT on purpose,
    # so we respect that even if the planner deactivated SHORT for the regime.
    # When the intersection is empty we log a clear warning and proceed with
    # the user's choice; the LLM will see the regime context and can still
    # produce conservative picks (or empty buckets if it judges nothing fits).
    user_filter = state.get("_horizon_filter") or None
    if user_filter:
        intersection = [h for h in user_filter if h in active_horizons]
        if intersection:
            active_horizons = intersection
            logger.info(
                f"[cyan]Discovery: user horizon filter applied → {active_horizons}[/cyan]"
            )
        else:
            logger.warning(
                f"[yellow]Discovery: user requested {user_filter} but planner "
                f"deactivated those for regime — running anyway (user wins)[/yellow]"
            )
            active_horizons = user_filter
    regime = state.get("macro_regime", "SIDEWAYS")
    hot_sectors = state.get("hot_sectors", []) or []
    avoid_sectors = state.get("avoid_sectors", []) or []
    economic_regime = state.get("economic_regime", "STABLE")

    # Extract per-horizon risk parameters from planner
    caution_level = planner_plan.get("overall_caution", "NORMAL")
    min_conviction_short = planner_plan.get("SHORT", {}).get("min_conviction", 55)
    min_conviction_mid = planner_plan.get("MID", {}).get("min_conviction", 50)
    min_conviction_long = planner_plan.get("LONG", {}).get("min_conviction", 50)

    # Build human-readable risk guidance string for the LLM
    risk_notes_map = {
        "NORMAL": "Standard market conditions — rank by quality and momentum.",
        "CAUTIOUS": "Mild caution — prefer mean-reversion setups, avoid low-liquidity names.",
        "ELEVATED": "Elevated risk — prioritise high-volume, defensive stocks. Penalise high-PE / speculative names.",
        "CRISIS": "Crisis mode — only fortress-quality stocks. Require strong fundamentals, mega-cap or defensive sector, and clear catalyst.",
    }
    horizon_risk_notes = risk_notes_map.get(caution_level, risk_notes_map["NORMAL"])

    try:
        symbols, stock_data = scan_market(filters=None)

        if not symbols:
            errors.append("Discovery Agent: No stocks matched the filters.")
            logger.warning("[yellow]Discovery Agent: Zero stocks found.[/yellow]")
            return {
                "discovered_symbols": [],
                "discovered_buckets": {"SHORT": [], "MID": [], "LONG": []},
                "errors": errors,
            }

        # ── Stage 8: LLM classify+rank ───────────────────────
        # We chunk the stock_data and run the LLM concurrently so no valid
        # candidate is dropped due to max_output_tokens limits.
        llm_input_count = len(stock_data)
        logger.info(
            f"[cyan]Discovery Stage 8: broad_scan={llm_input_count} stocks → "
            f"processing via concurrent LLM chunks[/cyan]"
        )
        # Build close-by-symbol lookup BEFORE the LLM call so we can sanity-check targets
        close_by_symbol = {
            (r.get("clean_symbol") or "").strip().upper(): _safe_close(r.get("close"))
            for r in stock_data
        }

        buckets = _classify_and_rank(
            stock_data=stock_data,
            regime=regime,
            active_horizons=active_horizons,
            hot_sectors=hot_sectors,
            avoid_sectors=avoid_sectors,
            economic_regime=economic_regime,
            caution_level=caution_level,
            min_conviction_short=min_conviction_short,
            min_conviction_mid=min_conviction_mid,
            min_conviction_long=min_conviction_long,
            horizon_risk_notes=horizon_risk_notes,
            run_id=state.get("run_id", "") or "",
            attempt_label="primary",
        )

        # ── Sanity check & retry for malformed indicative_target ─────
        # Detects the recurring bug where LLM emits a percentage (e.g. 25) instead
        # of an absolute INR price (e.g. 5676.30). Recovers via pct→absolute
        # conversion when the emitted value is plausibly a pct; otherwise drops the
        # row. If >30% of any non-empty bucket needs dropping, retries once.
        buckets, drop_stats = _sanitize_targets(buckets, close_by_symbol)
        if _retry_needed(drop_stats):
            logger.warning(
                f"[yellow]Discovery Stage 8: target sanity failed for "
                f"{drop_stats} — retrying LLM classify+rank once[/yellow]"
            )
            buckets_retry = _classify_and_rank(
                stock_data=stock_data,
                regime=regime,
                active_horizons=active_horizons,
                hot_sectors=hot_sectors,
                avoid_sectors=avoid_sectors,
                economic_regime=economic_regime,
                caution_level=caution_level,
                min_conviction_short=min_conviction_short,
                min_conviction_mid=min_conviction_mid,
                min_conviction_long=min_conviction_long,
                horizon_risk_notes=horizon_risk_notes,
                run_id=state.get("run_id", "") or "",
                attempt_label="retry",
            )
            buckets_retry, drop_stats_retry = _sanitize_targets(
                buckets_retry, close_by_symbol
            )
            # Prefer retry result if it produced more valid rows overall
            retry_total = sum(
                len(buckets_retry.get(h, [])) for h in ("SHORT", "MID", "LONG")
            )
            first_total = sum(len(buckets.get(h, [])) for h in ("SHORT", "MID", "LONG"))
            if retry_total >= first_total:
                buckets = buckets_retry
                logger.info(
                    f"[cyan]Discovery retry kept (rows: {retry_total} vs {first_total})[/cyan]"
                )
            else:
                logger.info(
                    f"[cyan]Discovery retry rejected (rows: {retry_total} vs {first_total})[/cyan]"
                )

        raw_counts = {h: len(buckets.get(h, [])) for h in ("SHORT", "MID", "LONG")}
        logger.info(
            f"[cyan]Discovery Stage 8 LLM output (after sanity, before 30-cap): "
            f"SHORT={raw_counts['SHORT']} MID={raw_counts['MID']} LONG={raw_counts['LONG']}[/cyan]"
        )

        # If all buckets are empty after LLM call, surface a clear error
        total_classified = sum(raw_counts.values())
        if total_classified == 0:
            errors.append(
                "Discovery: LLM returned 0 classified stocks — check prompt/model"
            )
            logger.error(
                "[bold red]Discovery: LLM returned 0 classified stocks.[/bold red]"
            )

        # Build symbol → raw screener row index (upper-cased for case-insensitive lookup)
        raw_by_symbol = {
            (r.get("clean_symbol") or "").strip().upper(): r for r in stock_data
        }

        # Merge raw screener data back onto LLM-classified stocks so persistence
        # can store it in raw_screener JSONB for cache-backed views
        for h in ("SHORT", "MID", "LONG"):
            for stock in buckets.get(h, []):
                sym = (stock.get("symbol") or "").strip().upper()
                raw = raw_by_symbol.get(sym)
                if raw:
                    stock["_raw_screener"] = raw

        # Limit to 30 per horizon
        for h in ("SHORT", "MID", "LONG"):
            buckets[h] = sorted(buckets.get(h, []), key=lambda s: s.get("rank", 999))[
                :30
            ]

        # Flatten for legacy consumers
        flat = []
        for h in active_horizons:
            for entry in buckets.get(h, []):
                flat.append(entry.get("symbol"))

        elapsed = round(time.time() - start_time, 2)
        logger.info(
            f"[bold green]>>> Discovery Agent: Done in {elapsed}s. "
            f"SHORT={len(buckets['SHORT'])} MID={len(buckets['MID'])} LONG={len(buckets['LONG'])}[/bold green]"
        )

        return {
            "discovered_symbols": flat or symbols,
            "discovered_buckets": buckets,
            "errors": errors,
        }

    except Exception as e:
        elapsed = round(time.time() - start_time, 2)
        errors.append(f"Discovery Agent crashed: {e}")
        logger.error(
            f"[bold red]>>> Discovery Agent: FAILED in {elapsed}s — {e}[/bold red]"
        )
        return {
            "discovered_symbols": [],
            "discovered_buckets": {"SHORT": [], "MID": [], "LONG": []},
            "errors": errors,
        }


def _classify_and_rank(
    stock_data: list[dict],
    regime: str,
    active_horizons: list[str],
    hot_sectors: list[str],
    avoid_sectors: list[str],
    economic_regime: str,
    caution_level: str = "NORMAL",
    min_conviction_short: int = 55,
    min_conviction_mid: int = 50,
    min_conviction_long: int = 50,
    horizon_risk_notes: str = "",
    run_id: str = "",
    attempt_label: str = "primary",
) -> dict:
    """Classify + rank all candidates using concurrent LLM calls for chunks to avoid token limits."""
    if not stock_data:
        return {"SHORT": [], "MID": [], "LONG": []}

    chunk_size = 60
    chunks = [
        stock_data[i : i + chunk_size] for i in range(0, len(stock_data), chunk_size)
    ]

    import time as _time

    _t0 = _time.time()

    def process_chunk(chunk_candidates, chunk_index):
        lines = []
        for s in chunk_candidates:
            sym = s.get("clean_symbol") or s.get("ticker", "")
            lines.append(
                f"- {sym}: close={s.get('close')}, RSI={s.get('RSI')}, "
                f"relVol={s.get('relative_volume_10d_calc')}, "
                f"P/E={s.get('price_earnings_ttm')}, ROE={s.get('return_on_equity')}, "
                f"D/E={s.get('debt_to_equity')}, "
                f"perf3m={s.get('Perf.3M')}, mcap={s.get('market_cap_basic')}, "
                f"sector={s.get('sector')}, signature={s.get('_signature', '?')}"
            )

        prompt = DISCOVERY_CLASSIFY_RANK_PROMPT.format(
            regime=regime,
            caution_level=caution_level,
            active_horizons=active_horizons,
            hot_sectors=hot_sectors,
            avoid_sectors=avoid_sectors,
            economic_regime=economic_regime,
            min_conviction_short=min_conviction_short,
            min_conviction_mid=min_conviction_mid,
            min_conviction_long=min_conviction_long,
            horizon_risk_notes=horizon_risk_notes,
            stock_lines="\n".join(lines),
        )

        _model_label = f"gemini (json_mode)"
        try:
            llm = get_model(ModelTier.FLASH, json_mode=True)
            response = llm.invoke([HumanMessage(content=prompt)])
            raw_text = extract_content(response)
            parsed = _parse(raw_text)
            chunk_buckets = parsed.get("buckets") or {}
            for h in ("SHORT", "MID", "LONG"):
                if h not in chunk_buckets or not isinstance(chunk_buckets[h], list):
                    chunk_buckets[h] = []
            return chunk_buckets, raw_text, None, prompt, chunk_index
        except Exception as e:
            return {"SHORT": [], "MID": [], "LONG": []}, "", e, prompt, chunk_index

    merged_buckets = {"SHORT": [], "MID": [], "LONG": []}

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(5, len(chunks))
    ) as executor:
        futures = {
            executor.submit(process_chunk, ch, i): i for i, ch in enumerate(chunks)
        }
        for future in concurrent.futures.as_completed(futures):
            chunk_buckets, raw_text, error, prompt, chunk_index = future.result()

            if error:
                logger.error(
                    f"[bold red]Stage 8 LLM classify failed for chunk {chunk_index}: {error}[/bold red]"
                )
                try:
                    log_agent_run(
                        run_id=run_id,
                        agent_name=f"discovery_llm_{attempt_label}_chunk_{chunk_index}",
                        agent_type="F1_DISCOVERY_LLM",
                        status="FAILED",
                        latency_ms=(_time.time() - _t0) * 1000.0,
                        model_used="gemini (json_mode)",
                        prompt_template=prompt,
                        error=f"{type(error).__name__}: {error}",
                    )
                except Exception:
                    pass
            else:
                for h in ("SHORT", "MID", "LONG"):
                    merged_buckets[h].extend(chunk_buckets.get(h, []))

                try:
                    counts = {
                        h: len(chunk_buckets.get(h, []))
                        for h in ("SHORT", "MID", "LONG")
                    }
                    log_agent_run(
                        run_id=run_id,
                        agent_name=f"discovery_llm_{attempt_label}_chunk_{chunk_index}",
                        agent_type="F1_DISCOVERY_LLM",
                        status="SUCCESS",
                        latency_ms=(_time.time() - _t0) * 1000.0,
                        model_used="gemini (json_mode)",
                        prompt_template=prompt,
                        raw_llm_response=raw_text,
                        output={
                            "bucket_counts": counts,
                            "buckets_preview": {
                                h: [
                                    {
                                        "symbol": s.get("symbol"),
                                        "discovery_score": s.get("discovery_score"),
                                        "rank": s.get("rank"),
                                        "indicative_target": s.get("indicative_target"),
                                    }
                                    for s in (chunk_buckets.get(h, []) or [])[:5]
                                ]
                                for h in ("SHORT", "MID", "LONG")
                            },
                        },
                    )
                except Exception:
                    pass

    return merged_buckets


def _safe_close(v):
    try:
        f = float(v)
        import math

        if math.isnan(f) or math.isinf(f) or f <= 0:
            return None
        return f
    except (TypeError, ValueError):
        return None


def _sanitize_targets(buckets: dict, close_by_symbol: dict) -> tuple[dict, dict]:
    """
    Walk every classified stock and validate `indicative_target` against its `close`.

    - If target is missing/0/negative → try to recover (drop if irrecoverable).
    - If target looks like a percentage (close > 100 and 0 < target ≤ 100, OR target
      is < 50% of close): convert via close * (1 + pct/100) when plausibly a pct,
      else drop the row.
    - If target is > 5× close (clearly bogus): drop.

    Returns (cleaned_buckets, drop_stats) where drop_stats maps horizon → (dropped, total).
    """
    cleaned = {"SHORT": [], "MID": [], "LONG": []}
    drop_stats = {"SHORT": (0, 0), "MID": (0, 0), "LONG": (0, 0)}

    for h in ("SHORT", "MID", "LONG"):
        rows = buckets.get(h, []) or []
        dropped_syms = []
        kept = []
        for stock in rows:
            sym = (stock.get("symbol") or "").strip().upper()
            close = close_by_symbol.get(sym)
            raw_tgt = stock.get("indicative_target")
            try:
                tgt = float(raw_tgt) if raw_tgt is not None else None
            except (TypeError, ValueError):
                tgt = None

            if not close:
                # No close price to validate against — drop conservatively.
                dropped_syms.append(f"{sym}(no-close)")
                continue

            if tgt is None or tgt <= 0:
                dropped_syms.append(f"{sym}(target={raw_tgt})")
                continue

            # Heuristic: looks like a percentage emitted in place of absolute price.
            looks_like_pct = (
                tgt < close * 0.5 and tgt <= 100  # tiny vs close AND plausibly a pct
            )

            if looks_like_pct:
                # Recover by treating it as a pct upside/downside off close.
                # Only recover if the resulting absolute target is in a sane band.
                recovered = round(close * (1 + tgt / 100.0), 2)
                if 0.5 * close <= recovered <= 3.0 * close:
                    logger.warning(
                        f"[yellow]Discovery sanity: {sym} target={tgt} looks like pct — "
                        f"converted to {recovered} (close={close})[/yellow]"
                    )
                    stock["indicative_target"] = recovered
                else:
                    dropped_syms.append(f"{sym}(pct-unrecoverable:{tgt}@close={close})")
                    continue
            elif tgt > 5.0 * close:
                # Wildly above close — bogus, drop.
                dropped_syms.append(f"{sym}(target={tgt}>>close={close})")
                continue

            kept.append(stock)

        if dropped_syms:
            logger.warning(
                f"[yellow]Discovery sanity: dropped {len(dropped_syms)}/{len(rows)} "
                f"from {h} → {', '.join(dropped_syms[:8])}"
                f"{'…' if len(dropped_syms) > 8 else ''}[/yellow]"
            )
        cleaned[h] = kept
        drop_stats[h] = (len(dropped_syms), len(rows))

    return cleaned, drop_stats


def _retry_needed(drop_stats: dict) -> bool:
    """Retry once if any non-empty bucket lost > 30% of its rows."""
    for h in ("SHORT", "MID", "LONG"):
        dropped, total = drop_stats.get(h, (0, 0))
        if total >= 4 and dropped / total > 0.30:
            return True
    return False


def _parse(raw: str) -> dict:
    """
    Robust JSON extractor for Stage 8.
    Handles: bare JSON, ```json fenced blocks, prose-wrapped JSON, trailing commas,
    and `json` language tag alone on a line. Logs a payload preview on failure
    so the actual format issue can be diagnosed.
    """
    if not raw:
        logger.warning("[yellow]Discovery Stage 8: empty LLM response[/yellow]")
        return {}

    text = raw.strip()

    # Strip code fences (```json ... ``` or ``` ... ```)
    if text.startswith("```"):
        lines = text.split("\n")
        # drop opening fence and any closing fence
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    # Try direct parse first
    candidates = [text]

    # Slice from first { to last } as a fallback for prose-wrapped JSON
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last != -1 and last > first:
        candidates.append(text[first : last + 1])

    for cand in candidates:
        try:
            return json.loads(cand)
        except Exception:
            # Try once more after stripping trailing commas (a common Gemini quirk)
            import re

            try:
                cleaned = re.sub(r",(\s*[}\]])", r"\1", cand)
                return json.loads(cleaned)
            except Exception:
                continue

    preview = text[:600].replace("\n", " ")
    logger.warning(
        f"[yellow]Discovery Stage 8: failed to parse LLM JSON (len={len(raw)}). "
        f"Preview: {preview!r}[/yellow]"
    )
    return {}
