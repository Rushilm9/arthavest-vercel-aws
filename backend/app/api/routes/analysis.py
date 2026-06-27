"""
Analysis Routes — F1/F2 final.
- /discover returns horizon-tagged buckets (SHORT/MID/LONG) plus a flat list.
- /discover/{horizon} returns just one horizon bucket.
- /analyze accepts optional suggested_horizon and returns the full F2 schema
  (4 specialists + horizon confirmation + debate + validator).
"""

from fastapi import APIRouter, HTTPException, Query, status, BackgroundTasks
from app.schemas.analysis import (
    DiscoveryRequest,
    DiscoveryResponse,
    DiscoveredStock,
    PriceTargets,
    ScreeningData,
    AnalyzeRequest,
    AnalyzeResponse,
    AgentSignals,
    TechnicalSummary,
    FundamentalSummary,
    SentimentSummary,
    ChartPatternSummary,
    DebateSummary,
    HorizonConfirmation,
    ValidatorIssue,
    MarketContextResponse,
    EconomicContextSchema,
    MarketPulseSchema,
    MacroContextSchema,
    NewsContextSchema,
    PlannerContextSchema,
    HorizonPlanDetails,
)
from app.agents.graph import run_discovery_pipeline, run_analysis_pipeline
from app.core.config import logger, SessionLocal
from app.db.models import Recommendations, Stocks
from app.services import discovery_cache
from app.services.discovery_persist import persist_discovery_run, persist_market_regime
from app.api.routes.alerts import push_alert

router = APIRouter(prefix="/analysis", tags=["Analysis"])

import os
import json
import threading
import pytz
from datetime import datetime, date

# ── Idempotency locks ────────────────────────────────────────────────────────
_analyze_in_flight: dict[tuple[str, str], threading.Lock] = {}
_analyze_guard = threading.Lock()

_dispatch_in_flight: dict[str, bool] = {}
_dispatch_guard = threading.Lock()

_IST = pytz.timezone("Asia/Kolkata")


def _ist_today() -> date:
    """Return today's date in IST (important: server may run UTC)."""
    import datetime as _dt

    return _dt.datetime.now(_IST).date()


def _norm_confidence(c):
    """Normalize a stored Recommendations.confidence to a 0-100 percentage.

    The DB `confidence` column is written on a 0-100 scale by
    `compute_weighted_confidence` (decision/tools.py). Historically the read
    path multiplied it by 100 again, producing values like 4550 for 45.5%.
    This normalizer is self-healing and clamps the result to [0, 100]:
      - None  -> None
      - <= 1  -> legacy 0-1 scale, scale up by 100
      - else  -> already 0-100, used as-is
    """
    if c is None:
        return None
    try:
        c = float(c)
    except (ValueError, TypeError):
        return None
    if c <= 1.0:  # legacy 0-1 scale row
        c *= 100
    return round(max(0.0, min(100.0, c)), 1)


from app.core.verdict import final_verdict as _verdict  # single source of truth
# (kept the `_verdict` name as a local alias so existing call sites are unchanged)


def _save_result_json(result_type: str, data: dict, symbol: str = None) -> str:
    """Save API result to results/ directory as timestamped JSON.

    Gated on SAVE_RESULTS env var (default false) — rushil.md §8 disabled this
    by default because it accumulated noise. Set SAVE_RESULTS=true to re-enable
    for debugging. Returns "" when disabled.
    """
    if os.getenv("SAVE_RESULTS", "false").lower() not in ("true", "1", "t", "yes"):
        return ""
    os.makedirs("results", exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    name = f"{result_type}_{symbol}_{ts}.json" if symbol else f"{result_type}_{ts}.json"
    path = os.path.join("results", name)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    logger.info(f"[green]Result saved: {path}[/green]")
    return name


# ══════════════════════════════════════════════════════════════
# GET /analysis/graph  (Mermaid for both pipelines)
# ══════════════════════════════════════════════════════════════

import base64
from fastapi.responses import PlainTextResponse, HTMLResponse


def _mermaid_live_url(mermaid_src: str) -> str:
    """Encode Mermaid source for the public mermaid.live editor / image renderer."""
    b64 = base64.urlsafe_b64encode(mermaid_src.encode("utf-8")).decode("ascii")
    return f"https://mermaid.ink/img/{b64}"


def _mermaid_html(title: str, mermaid_src: str) -> str:
    """Render a self-contained HTML page that draws the Mermaid diagram."""
    safe = mermaid_src.replace("</", "<\\/")
    return f"""<!doctype html>
<html><head><meta charset='utf-8'><title>{title}</title>
<script src='https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js'></script>
</head><body style='font-family:system-ui;margin:24px'>
<h2>{title}</h2>
<pre class='mermaid'>{safe}</pre>
<script>mermaid.initialize({{startOnLoad:true,securityLevel:'loose'}});</script>
</body></html>"""


_DISCOVERY_MERMAID = """graph TD
    subgraph "Pre-Amble: Market Context"
        START(("🚀 START")) --> economic["📊 Economic Agent\\n⟲ retry: 3"]
        economic --> market_pulse["📈 Market Pulse\\n⟲ retry: 3"]
        market_pulse --> news["📰 News Agent\\n⟲ retry: 3"]
        news --> macro_context["🌍 Macro Context\\n⟲ retry: 3"]
    end
    subgraph "Planning"
        macro_context --> planner["🧠 Planner\\n⟲ retry: 3"]
    end
    subgraph "Discovery: Stages 6-8"
        planner --> discovery["🔎 Discovery Agent\\n⟲ retry: 3\\nFilter → Scan → LLM Classify+Rank"]
    end
    discovery --> END(("✅ END"))

    style economic fill:#dbeafe,stroke:#2563eb
    style market_pulse fill:#dbeafe,stroke:#2563eb
    style news fill:#dbeafe,stroke:#2563eb
    style macro_context fill:#dbeafe,stroke:#2563eb
    style planner fill:#fef3c7,stroke:#f59e0b
    style discovery fill:#dcfce7,stroke:#16a34a"""

_ANALYSIS_MERMAID = """graph TD
    subgraph "Pre-Amble: Market Context"
        START(("🚀 START")) --> economic["📊 Economic Agent\\n⟲ retry: 3"]
        economic --> market_pulse["📈 Market Pulse\\n⟲ retry: 3"]
        market_pulse --> news["📰 News Agent\\n⟲ retry: 3"]
        news --> macro_context["🌍 Macro Context\\n⟲ retry: 3"]
        macro_context --> planner["🧠 Planner\\n⟲ retry: 3"]
    end
    subgraph "Specialists (parallel intent, sequential wiring)"
        planner --> technical["📐 Technical\\n⟲ retry: 3"]
        technical --> fundamental["💰 Fundamental\\n⟲ retry: 3"]
        fundamental --> sentiment["💬 Sentiment\\n⟲ retry: 3"]
        sentiment --> chart_pattern["📊 Chart Pattern\\n⟲ retry: 3"]
    end
    subgraph "Post-Merge"
        chart_pattern --> merge_signals["🔀 Merge Signals\\n⟲ retry: 3"]
        merge_signals --> horizon_confirm["🎯 Horizon Confirm\\n⟲ retry: 3"]
        horizon_confirm --> debate["⚖️ Debate Agent\\n⟲ retry: 3\\nAlways runs"]
        debate --> decision["🏛️ Decision Agent\\n⟲ retry: 3\\nLLM computes prices + narrative"]
    end
    decision --> END(("✅ END"))

    style economic fill:#dbeafe,stroke:#2563eb
    style market_pulse fill:#dbeafe,stroke:#2563eb
    style news fill:#dbeafe,stroke:#2563eb
    style macro_context fill:#dbeafe,stroke:#2563eb
    style planner fill:#fef3c7,stroke:#f59e0b
    style technical fill:#ede9fe,stroke:#7c3aed
    style fundamental fill:#ede9fe,stroke:#7c3aed
    style sentiment fill:#ede9fe,stroke:#7c3aed
    style chart_pattern fill:#ede9fe,stroke:#7c3aed
    style merge_signals fill:#dcfce7,stroke:#16a34a
    style horizon_confirm fill:#dcfce7,stroke:#16a34a
    style debate fill:#dcfce7,stroke:#16a34a
    style decision fill:#dcfce7,stroke:#16a34a"""


@router.get("/graph", summary="Mermaid for BOTH Discovery + Analysis graphs")
def get_graph_both():
    return {
        "discovery": {
            "mermaid": _DISCOVERY_MERMAID,
            "image_url": _mermaid_live_url(_DISCOVERY_MERMAID),
        },
        "analysis": {
            "mermaid": _ANALYSIS_MERMAID,
            "image_url": _mermaid_live_url(_ANALYSIS_MERMAID),
        },
    }


@router.get("/graph/discovery", summary="Mermaid for the F1 Discovery pipeline only")
def get_graph_discovery(format: str = "json"):
    """
    format=json   -> {mermaid, image_url}
    format=text   -> raw Mermaid source (text/plain)
    format=html   -> self-contained HTML that renders the diagram
    format=image  -> 302 redirect to mermaid.ink PNG
    """
    from fastapi.responses import RedirectResponse

    src = _DISCOVERY_MERMAID
    if format == "text":
        return PlainTextResponse(src, media_type="text/plain")
    if format == "html":
        return HTMLResponse(_mermaid_html("Discovery Pipeline (F1)", src))
    if format == "image":
        return RedirectResponse(_mermaid_live_url(src))
    return {
        "pipeline": "discovery",
        "mermaid": src,
        "image_url": _mermaid_live_url(src),
    }


@router.get("/graph/analysis", summary="Mermaid for the F2 Analysis pipeline only")
def get_graph_analysis(format: str = "json"):
    """Same format options as /graph/discovery."""
    from fastapi.responses import RedirectResponse

    src = _ANALYSIS_MERMAID
    if format == "text":
        return PlainTextResponse(src, media_type="text/plain")
    if format == "html":
        return HTMLResponse(_mermaid_html("Analysis Pipeline (F2)", src))
    if format == "image":
        return RedirectResponse(_mermaid_live_url(src))
    return {"pipeline": "analysis", "mermaid": src, "image_url": _mermaid_live_url(src)}


# ══════════════════════════════════════════════════════════════
# GET /analysis/autocomplete
# ══════════════════════════════════════════════════════════════


@router.get("/autocomplete", summary="Fetch stock suggestions from Yahoo Finance")
def autocomplete(q: str):
    try:
        import requests

        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={q}&quotesCount=10&newsCount=0"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/91.0.4472.124"
        }
        resp = requests.get(url, headers=headers, timeout=5)
        if resp.status_code != 200:
            return []
        data = resp.json()
        results = []
        for quote in data.get("quotes", []):
            symbol = quote.get("symbol", "")
            if symbol.endswith(".NS") or symbol.endswith(".BO"):
                results.append(
                    {
                        "symbol": symbol,
                        "name": quote.get("shortname")
                        or quote.get("longname")
                        or symbol,
                        "exch": quote.get("exchange"),
                    }
                )
        return results[:5]
    except Exception as e:
        logger.error(f"[red]Autocomplete failed: {e}[/red]")
        return []


# ══════════════════════════════════════════════════════════════
# Build a DiscoveredStock from a flat scan-data dict
# ══════════════════════════════════════════════════════════════


def _build_stock_from_scan(
    data: dict, macro_regime: str, horizon: str = "MID", skip_live_news: bool = False
) -> DiscoveredStock:
    symbol = data.get("clean_symbol", data.get("ticker", "UNKNOWN"))
    close = _safe_float(data.get("close"))
    atr = _safe_float(data.get("ATR"))
    # Use headlines already stored in the DB entry; skip expensive live HTTP
    # calls to Google News which block the response for 15s × N stocks.
    headlines = data.get("news_headlines") or []
    if not headlines and not skip_live_news:
        try:
            from app.services.news_service import get_stock_news

            headlines = get_stock_news(symbol)[:5]
        except Exception:
            headlines = []

    # Only create PriceTargets if ALL three values are non-null
    buy_price = _safe_float(data.get("buy_price") or data.get("entry_price"))
    target_price = _safe_float(
        data.get("target_price") or data.get("indicative_target")
    )
    stop_loss = _safe_float(data.get("stop_loss"))
    if buy_price is not None and target_price is not None and stop_loss is not None:
        price_targets = PriceTargets(
            buy_price=buy_price,
            target_price=target_price,
            stop_loss=stop_loss,
        )
    else:
        price_targets = None

    stock = DiscoveredStock(
        symbol=symbol,
        close=close,
        change_pct=_safe_float(data.get("change")),
        volume=_safe_int(data.get("volume")),
        relative_volume=_safe_float(data.get("relative_volume_10d_calc")),
        rsi=_safe_float(data.get("RSI")),
        market_cap=_safe_float(data.get("market_cap_basic")),
        pe_ratio=_safe_float(data.get("price_earnings_ttm")),
        roe=_safe_float(data.get("return_on_equity")),
        sector=data.get("sector"),
        industry=data.get("industry"),
        news_headlines=headlines,
        price_targets=price_targets,
        atr=atr,
        ema20=_safe_float(data.get("EMA20")),
        ema50=_safe_float(data.get("EMA50")),
        ema200=_safe_float(data.get("EMA200")),
        perf_week=_safe_float(data.get("Perf.W")),
        perf_1m=_safe_float(data.get("Perf.1M")),
        perf_3m=_safe_float(data.get("Perf.3M")),
        debt_to_equity=_safe_float(data.get("debt_to_equity")),
        net_margin=_safe_float(data.get("after_tax_margin")),
        price_book=_safe_float(data.get("price_book_fq")),
        dividend_yield=_safe_float(data.get("dividend_yield_recent")),
    )

    # Populate screening_data from the raw scan data
    stock.screening_data = ScreeningData(
        rsi=_safe_float(data.get("RSI")),
        pe_ratio=_safe_float(data.get("price_earnings_ttm") or data.get("P/E")),
        roe=_safe_float(data.get("return_on_equity") or data.get("ROE")),
        market_cap=_safe_float(data.get("market_cap_basic") or data.get("market_cap")),
        relative_volume=_safe_float(data.get("relative_volume_10d_calc")),
        ema20=_safe_float(data.get("EMA20")),
        ema50=_safe_float(data.get("EMA50")),
        ema200=_safe_float(data.get("EMA200")),
        atr=_safe_float(data.get("ATR")),
        debt_to_equity=_safe_float(data.get("debt_to_equity")),
        net_margin=_safe_float(data.get("net_margin")),
        perf_week=_safe_float(data.get("Perf.W")),
        perf_1m=_safe_float(data.get("Perf.1M")),
        perf_3m=_safe_float(data.get("Perf.3M")),
    )

    return stock


# ══════════════════════════════════════════════════════════════
# POST /analysis/discover
# ══════════════════════════════════════════════════════════════


@router.post("/discover", response_model=DiscoveryResponse)
def discover(
    request: DiscoveryRequest = DiscoveryRequest(),
    horizon: str | None = Query(
        None,
        description="Restrict Stage 8 to one horizon: SHORT | MID | LONG | ALL (default ALL). "
        "Used by the per-horizon ▶ Run Discovery dropdown.",
    ),
    background_tasks: BackgroundTasks = None,
):
    """
    F1 final discovery — runs Economic → Pulse → News → Macro → Planner → Discovery.
    Persists to DB then returns the result via the DB-backed path (no second TradingView scan).

    Auto-dispatch of F2 was removed (rushil.md §6.1). F2 fan-out happens only via
    explicit POST /analysis/dispatch/{run_id}.

    Per-horizon: pass ?horizon=SHORT (or MID/LONG) to refresh only that bucket;
    the other buckets in DB stay untouched.

    For long-running scenarios prefer the async pattern:
      POST /discover/jobs   -> returns {job_id}
      GET  /discover/jobs/{id} -> poll for {status, result}
      GET  /discover/cached  -> instant: today's DB result (no re-scan)
    """
    logger.info(
        f"[bold cyan]API: /discover endpoint hit (F1) horizon={horizon or 'ALL'}[/bold cyan]"
    )

    # Resolve horizon filter
    horizon_filter: list[str] | None = None
    if horizon and horizon.upper() != "ALL":
        h = horizon.upper()
        if h not in ("SHORT", "MID", "LONG"):
            raise HTTPException(
                status_code=400, detail="horizon must be SHORT, MID, LONG, or ALL"
            )
        horizon_filter = [h]

    import time

    t0 = time.time()
    try:
        result = run_discovery_pipeline(horizon_filter=horizon_filter)
        run_id = result.get("run_id", "")

        # Persist F1 to DB first — DB is the single source of truth
        _persist_discovery_result(result)

        # Build response from DB (same path as /cached — no second TradingView scan)
        from app.services.discovery_persist import fetch_discovery_run_buckets

        buckets = fetch_discovery_run_buckets(run_id) if run_id else {}
        config = result
        response = _build_discovery_response_from_db(
            run_id=run_id,
            macro_regime=config.get("macro_regime", "SIDEWAYS"),
            economic_regime=config.get("economic_regime"),
            economic_score=config.get("economic_score"),
            market_pulse_score=int(config.get("market_pulse_score") or 50),
            buckets=buckets,
            created_at=None,
            horizon_filter=request.horizon,
            per_bucket_limit=request.per_bucket_limit,
        )

        saved_file = _save_result_json("discover", response.model_dump(mode="json"))
        logger.info(
            f"[bold green]API: /discover returned {response.stocks_found} stocks (saved: {saved_file})[/bold green]"
        )

        # Push WebSocket alert for discovery completion
        regime = config.get("macro_regime", "SIDEWAYS")
        push_alert(
            "INFO",
            f"Discovery completed: {response.stocks_found} stocks found. Market regime: {regime}",
        )

        # NOTE: auto-dispatch of F2 was removed (rushil.md §6.1) — manual-only mode.
        # F2 fan-out now happens ONLY via explicit POST /analysis/dispatch/{run_id}.
        return response

    except Exception as e:
        logger.error(f"[bold red]API: /discover failed — {e}[/bold red]")
        push_alert("REVIEW_NEEDED", f"Discovery pipeline failed: {e}")
        raise HTTPException(status_code=500, detail=f"Discovery failed: {e}")


# ── DB-backed cached endpoint ─────────────────────────────────────────────────


def _build_discovery_response_from_db(
    run_id: str,
    macro_regime: str,
    economic_regime: str | None,
    economic_score: int | None,
    market_pulse_score: int,
    buckets: dict,
    created_at: str | None,
    horizon_filter: str | None = None,
    per_bucket_limit: int | None = None,
) -> DiscoveryResponse:
    """
    Build a DiscoveryResponse purely from DB-stored data — no TradingView re-scan.
    buckets is {SHORT: [...], MID: [...], LONG: [...]} from fetch_discovery_run_buckets().
    """
    if per_bucket_limit:
        buckets = {
            h: (buckets.get(h, []) or [])[:per_bucket_limit]
            for h in ("SHORT", "MID", "LONG")
        }

    bucket_models: dict[str, list[DiscoveredStock]] = {
        "SHORT": [],
        "MID": [],
        "LONG": [],
    }
    all_stocks: list[DiscoveredStock] = []
    seen: set[str] = set()

    for h in ("SHORT", "MID", "LONG"):
        for entry in buckets.get(h, []) or []:
            sym = entry.get("symbol")
            if not sym:
                continue

            # Use canonical mapper — entry now includes raw_screener fields (close, RSI, EMA*, ATR, etc.)
            # merged in at fetch time, so live and cached views produce identical DiscoveredStock shapes.
            stock = _build_stock_from_scan(
                entry, macro_regime, horizon=h, skip_live_news=True
            )

            # Overlay DB-authoritative F1 fields that _build_stock_from_scan can't know
            stock.horizon = h
            stock.rank = _safe_int(entry.get("rank"))
            stock.discovery_score = _safe_int(entry.get("discovery_score"))
            stock.confidence = _safe_int(entry.get("probability"))
            stock.catalyst = entry.get("catalyst")
            stock.ai_reasoning = entry.get("reasoning")
            stock.risk_flags = entry.get("risk_flags") or []
            stock.indicative_target = _safe_float(
                entry.get("indicative_target") or entry.get("target_price")
            )

            # Propagate F1 LLM-supplied hold days
            hold_days = entry.get("suggested_hold_days")
            if hold_days is not None:
                stock.suggested_hold_days = _safe_int(hold_days)

            # Pass F2 analysis state if present (None = not analyzed yet,
            # so only normalize when a verdict actually exists)
            stock.recommendation_id = entry.get("recommendation_id")
            stock.recommendation = (
                _verdict(entry["recommendation"])
                if entry.get("recommendation")
                else None
            )
            stock.full_response = entry.get("full_response")

            _set_pick_metadata(stock)
            bucket_models[h].append(stock)
            if sym not in seen:
                seen.add(sym)
                all_stocks.append(stock)

    if horizon_filter and horizon_filter.upper() in ("SHORT", "MID", "LONG"):
        hf = horizon_filter.upper()
        all_stocks = [s for s in all_stocks if s.horizon == hf]

    ai_summary = _generate_overall_summary(all_stocks, macro_regime, market_pulse_score)

    resp = DiscoveryResponse(
        run_id=run_id,
        stocks_found=len(all_stocks),
        stocks=all_stocks,
        buckets={h: bucket_models[h] for h in ("SHORT", "MID", "LONG")},
        macro_regime=macro_regime,
        market_pulse_score=market_pulse_score,
        economic_score=economic_score,
        economic_regime=economic_regime,
        market_sentiment=None,
        hot_sectors=[],
        avoid_sectors=[],
        active_horizons=["SHORT", "MID", "LONG"],
        ai_summary=ai_summary,
        errors=[],
    )
    if created_at:
        resp.timestamp = created_at
    return resp


@router.get(
    "/discover/today",
    response_model=DiscoveryResponse,
    summary="Today's discovery from DB (IST calendar day)",
)
def discover_today(
    horizon: str | None = None,
    per_bucket_limit: int | None = None,
):
    """
    Returns today's discovery run from DB (IST calendar day).
    If no run exists for today, returns 404.
    Never re-scans TradingView.
    """
    from sqlalchemy import desc, func, cast
    from app.db.models import Runs
    from app.services.discovery_persist import fetch_discovery_run_buckets

    today = _ist_today()
    db = SessionLocal()
    try:
        latest_run = (
            db.query(Runs)
            .filter(
                Runs.workflow_name == "discovery_pipeline",
                Runs.status == "COMPLETED",
                func.date(Runs.completed_at) == today,
            )
            .order_by(desc(Runs.completed_at))
            .first()
        )
        if not latest_run:
            raise HTTPException(
                status_code=404,
                detail=f"No discovery run found for today ({today}). Click ▶ Run Discovery to start one.",
            )
        config = latest_run.workflow_config or {}
        run_id = str(latest_run.id)
        buckets = fetch_discovery_run_buckets(run_id)
        if latest_run.completed_at:
            ts = latest_run.completed_at.isoformat()
            if not latest_run.completed_at.tzinfo:
                ts += "Z"
            created_at = ts
        else:
            created_at = None
    finally:
        db.close()

    return _build_discovery_response_from_db(
        run_id=run_id,
        macro_regime=config.get("macro_regime", "SIDEWAYS"),
        economic_regime=config.get("economic_regime"),
        economic_score=config.get("economic_score"),
        market_pulse_score=int(config.get("market_pulse_score", 50)),
        buckets=buckets,
        created_at=created_at,
        horizon_filter=horizon,
        per_bucket_limit=per_bucket_limit,
    )


@router.get(
    "/discover/cached",
    response_model=DiscoveryResponse,
    summary="Latest discovery from DB (any date)",
)
def discover_cached(
    horizon: str | None = None,
    per_bucket_limit: int | None = None,
):
    """
    Returns the most recent completed discovery run from DB.
    Prefers today's run (IST); falls back to the latest run from any date.
    Never re-scans TradingView.
    """
    from sqlalchemy import desc, func
    from app.db.models import Runs
    from app.services.discovery_persist import fetch_discovery_run_buckets

    today = _ist_today()
    db = SessionLocal()
    try:
        # Prefer today's run first (calculated using IST bounds converted to naive UTC)
        import datetime as _dt
        import pytz as _pytz

        ist_start = _dt.datetime.combine(today, _dt.time.min)
        ist_end = _dt.datetime.combine(today, _dt.time.max)
        utc_start = _IST.localize(ist_start).astimezone(_pytz.utc).replace(tzinfo=None)
        utc_end = _IST.localize(ist_end).astimezone(_pytz.utc).replace(tzinfo=None)

        latest_run = (
            db.query(Runs)
            .filter(
                Runs.workflow_name == "discovery_pipeline",
                Runs.status == "COMPLETED",
                Runs.completed_at >= utc_start,
                Runs.completed_at <= utc_end,
            )
            .order_by(desc(Runs.completed_at))
            .first()
        )
        # Fall back to most recent ever
        if not latest_run:
            latest_run = (
                db.query(Runs)
                .filter(
                    Runs.workflow_name == "discovery_pipeline",
                    Runs.status == "COMPLETED",
                )
                .order_by(desc(Runs.completed_at))
                .first()
            )
        if not latest_run:
            raise HTTPException(
                status_code=503,
                detail="No discovery result in DB yet — click ▶ Run Discovery to populate.",
            )
        config = latest_run.workflow_config or {}
        run_id = str(latest_run.id)
        buckets = fetch_discovery_run_buckets(run_id)
        if latest_run.completed_at:
            ts = latest_run.completed_at.isoformat()
            if not latest_run.completed_at.tzinfo:
                ts += "Z"
            created_at = ts
        else:
            created_at = None
    finally:
        db.close()

    return _build_discovery_response_from_db(
        run_id=run_id,
        macro_regime=config.get("macro_regime", "SIDEWAYS"),
        economic_regime=config.get("economic_regime"),
        economic_score=config.get("economic_score"),
        market_pulse_score=int(config.get("market_pulse_score", 50)),
        buckets=buckets,
        created_at=created_at,
        horizon_filter=horizon,
        per_bucket_limit=per_bucket_limit,
    )


# ══════════════════════════════════════════════════════════════
# GET /analysis/context/today  — today's market intelligence cards
# ══════════════════════════════════════════════════════════════


def _derive_breadth(adr: float | None) -> tuple[str | None, str | None]:
    """Derive (breadth_signal, market_health) from the advance-decline ratio.
    Returns (None, None) when the ratio is missing so we don't fabricate."""
    if adr is None:
        return None, None
    if adr >= 1.2:
        return "HEALTHY", "STRONG"
    if adr >= 1.0:
        return "HEALTHY", "MODERATE"
    if adr >= 0.8:
        return "DETERIORATING", "WEAK"
    return "COLLAPSED", "FRAGILE"


@router.get(
    "/context/today",
    response_model=MarketContextResponse,
    summary="Today's macroeconomic context (economic / market pulse / macro from DB)",
)
def get_market_context_today():
    """
    Returns today's market-intelligence context for the dashboard cards.
    Loads and merges the saved JSON context from the last F1 Discovery pipeline run.
    """
    from app.db.models import EconomicSnapshots, MarketRegimes
    from app.services.discovery_persist import load_last_discovery_context

    # Load last discovery context from JSON file
    last_context = load_last_discovery_context()

    today = _ist_today()
    db = SessionLocal()
    try:
        # Today's economic snapshot (IST). Fall back to the most recent if today's
        # row hasn't been written yet.
        econ = (
            db.query(EconomicSnapshots)
            .filter(EconomicSnapshots.snapshot_date == today)
            .first()
        ) or (
            db.query(EconomicSnapshots)
            .order_by(EconomicSnapshots.snapshot_date.desc())
            .first()
        )

        # Latest evaluated market regime (pulse + macro both live on this row in F1).
        regime = (
            db.query(MarketRegimes).order_by(MarketRegimes.evaluated_at.desc()).first()
        )

        if not econ and not regime and not last_context:
            raise HTTPException(
                status_code=404,
                detail=f"No market context for today ({today}). Click ▶ Run Discovery to populate.",
            )

        # ── Economic ────────────────────────────────────────────────
        economic = EconomicContextSchema(
            score=econ.economic_score
            if econ
            else (last_context.get("economic_score") or None),
            regime=econ.economic_regime
            if econ
            else (last_context.get("economic_regime") or "STABLE"),
            positives=last_context.get("economic_positives") or [],
            risks=last_context.get("economic_risks") or [],
            overweight_sectors=last_context.get("overweight_sectors") or [],
            underweight_sectors=last_context.get("underweight_sectors") or [],
            reasoning=econ.llm_analysis
            or last_context.get("economic_reasoning")
            or "Economic regime is stable with no major stresses detected.",
            model_used=last_context.get("economic_model") or "gemini-2.5-flash",
            built_at=econ.created_at.isoformat()
            if (econ and econ.created_at)
            else (last_context.get("built_at") or None),
        )

        # ── Market pulse ──────────────────────────────────
        adr = (
            _safe_float(econ.advance_decline_ratio)
            if econ
            else _safe_float(last_context.get("advance_decline_ratio"))
        )
        breadth_signal, market_health = _derive_breadth(adr)

        # Calculate pulse score
        pulse_score = (
            regime.market_pulse_score
            if regime
            else last_context.get("market_pulse_score")
        )
        if pulse_score is not None:
            pulse_score = int(pulse_score)

        # Determine pulse reasoning
        pulse_reasoning = last_context.get("market_pulse_reasoning")
        if not pulse_reasoning:
            vix_val = (
                _safe_float(econ.india_vix)
                if econ
                else _safe_float(last_context.get("india_vix"))
            )
            pulse_reasoning = f"Market pulse is evaluated at {pulse_score or 50}/100. Advance-decline ratio is {adr or 'N/A'}, showing {breadth_signal or 'neutral'} breadth. India VIX is at {vix_val or 'N/A'}, indicating low-to-moderate volatility."

        market_pulse = MarketPulseSchema(
            score=pulse_score,
            regime=regime.regime
            if regime
            else (last_context.get("macro_regime") or "SIDEWAYS"),
            india_vix=_safe_float(econ.india_vix)
            if econ
            else _safe_float(last_context.get("india_vix")),
            nifty_level=_safe_float(econ.nifty_level)
            if econ
            else _safe_float(last_context.get("nifty_level")),
            advance_decline_ratio=adr,
            sector_strength=last_context.get("sector_strength") or [],
            breadth_signal=breadth_signal,
            market_health=market_health,
            reasoning=pulse_reasoning,
        )

        # ── News ───────────────────────────────────────────────────────────
        news = None
        if last_context.get("market_sentiment") is not None:
            news = NewsContextSchema(
                market_sentiment=_safe_float(last_context.get("market_sentiment")),
                hot_sectors=last_context.get("hot_sectors") or [],
                avoid_sectors=last_context.get("avoid_sectors") or [],
                anomaly_alerts=last_context.get("anomaly_alerts") or [],
                reasoning=last_context.get("news_reasoning")
                or "Market news sentiment is neutral with no major events.",
                model_used=last_context.get("news_model") or "gemini-2.5-flash",
            )

        # ── Macro context ───────────────────────────────────────────
        triggers = {}
        if regime and isinstance(regime.triggers, dict):
            triggers = {str(k): str(v) for k, v in regime.triggers.items()}
        elif last_context.get("macro_triggers"):
            triggers = {
                str(k): str(v) for k, v in last_context.get("macro_triggers").items()
            }

        macro_context = MacroContextSchema(
            regime=regime.regime
            if regime
            else (last_context.get("macro_regime") or "SIDEWAYS"),
            confidence=_safe_float(regime.confidence)
            if regime
            else _safe_float(last_context.get("macro_confidence")),
            triggers=triggers,
            reasoning=last_context.get("macro_reasoning")
            or "Macro context shows stable conditions and triggers are in line with expectation.",
            model_used=last_context.get("macro_model") or "gemini-2.5-pro",
        )

        # ── Planner strategy ───────────────────────────────────────────────
        planner = None
        plan_dict = last_context.get("planner_plan")
        if plan_dict and isinstance(plan_dict, dict):
            horizon_plans = {}
            for hor in ("SHORT", "MID", "LONG"):
                h_block = plan_dict.get(hor) or {}
                if (
                    h_block
                    and isinstance(h_block, dict)
                    and h_block.get("active", False)
                ):
                    weights = h_block.get("agent_weights") or {}
                    norm_weights = {}
                    for k, v in weights.items():
                        val = _safe_float(v)
                        if val is not None:
                            if val <= 1.0:
                                norm_weights[k] = round(val * 100.0, 1)
                            else:
                                norm_weights[k] = round(val, 1)
                        else:
                            norm_weights[k] = 0.0

                    strategy_text = f"Risk: {h_block.get('risk_tolerance', 'NORMAL')}. Caution: {h_block.get('caution_level', 'NORMAL')}. Max positions: {h_block.get('max_positions', 5)}."
                    pref = h_block.get("preferred_sectors")
                    if pref:
                        strategy_text += f" Focus on: {', '.join(pref)}."
                    avoid = h_block.get("avoid_sectors")
                    if avoid:
                        strategy_text += f" Avoid: {', '.join(avoid)}."

                    horizon_plans[hor] = HorizonPlanDetails(
                        agent_weights=norm_weights,
                        min_conviction=int(h_block.get("min_conviction") or 50),
                        strategy=strategy_text,
                    )

            planner = PlannerContextSchema(
                active_horizons=plan_dict.get("active_horizons")
                or ["SHORT", "MID", "LONG"],
                overall_caution=plan_dict.get("overall_caution") or "NORMAL",
                horizon_plans=horizon_plans,
                reasoning=plan_dict.get("reasoning")
                or "Strategy is tailored to current market conditions.",
            )

        return MarketContextResponse(
            date=today.isoformat(),
            source="db",  # flip to "db" since news + planner are fully populated now
            economic=economic,
            market_pulse=market_pulse,
            news=news,
            macro_context=macro_context,
            planner=planner,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[red]/context/today failed: {e}[/red]")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.post("/discover/jobs", summary="Queue an F1 run, return job_id")
def discover_jobs_create(
    horizon: str | None = Query(
        None,
        description="Restrict discovery to one horizon: SHORT | MID | LONG | ALL (default ALL). "
        "Reduces LLM calls and cost.",
    ),
):
    """Fire-and-poll: returns immediately with a job_id. Worker runs in background."""
    horizon_filter: list[str] | None = None
    if horizon and horizon.upper() != "ALL":
        h = horizon.upper()
        if h not in ("SHORT", "MID", "LONG"):
            raise HTTPException(
                status_code=400, detail="horizon must be SHORT, MID, LONG, or ALL"
            )
        horizon_filter = [h]
    job_id = discovery_cache.submit_job(horizon_filter=horizon_filter)
    return {
        "job_id": job_id,
        "status": "queued",
        "horizon": horizon or "ALL",
        "poll_url": f"/analysis/discover/jobs/{job_id}",
    }


@router.get("/discover/jobs", summary="List recent F1 jobs")
def discover_jobs_list(limit: int = 20):
    return {"jobs": [_job_summary(j) for j in discovery_cache.list_jobs(limit=limit)]}


@router.get("/discover/jobs/{job_id}", summary="Poll an F1 job's status / result")
def discover_jobs_get(
    job_id: str,
    horizon: str | None = None,
    per_bucket_limit: int | None = None,
):
    job = discovery_cache.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")
    out = _job_summary(job)
    if job["status"] == "done" and job.get("result"):
        raw = job["result"]
        run_id = raw.get("run_id", "")
        try:
            from app.services.discovery_persist import fetch_discovery_run_buckets

            buckets = fetch_discovery_run_buckets(run_id) if run_id else {}
            config = {
                "macro_regime": raw.get("macro_regime", "SIDEWAYS"),
                "economic_regime": raw.get("economic_regime"),
                "economic_score": raw.get("economic_score"),
                "market_pulse_score": raw.get("market_pulse_score", 50),
            }
            resp = _build_discovery_response_from_db(
                run_id=run_id,
                macro_regime=config["macro_regime"],
                economic_regime=config["economic_regime"],
                economic_score=config["economic_score"],
                market_pulse_score=int(config["market_pulse_score"] or 50),
                buckets=buckets,
                created_at=None,
                horizon_filter=horizon,
                per_bucket_limit=per_bucket_limit,
            )
            out["response"] = resp.model_dump()
        except Exception as e:
            out["response_build_error"] = str(e)
    return out


def _job_summary(job: dict) -> dict:
    return {
        "job_id": job.get("job_id"),
        "status": job.get("status"),
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
        "elapsed_sec": job.get("elapsed_sec"),
        "error": job.get("error"),
    }


@router.get("/discover/{horizon}", response_model=DiscoveryResponse)
def discover_by_horizon(horizon: str):
    """Convenience: return latest cached discovery filtered to a single horizon."""
    h = horizon.upper()
    if h not in ("SHORT", "MID", "LONG"):
        raise HTTPException(
            status_code=400, detail="horizon must be SHORT, MID, or LONG"
        )
    return discover_cached(horizon=h)


# ══════════════════════════════════════════════════════════════
# POST /analysis/analyze
# ══════════════════════════════════════════════════════════════


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest):
    symbol = request.symbol.upper().strip()
    suggested_horizon = (request.suggested_horizon or "MID").upper()
    if suggested_horizon not in ("SHORT", "MID", "LONG"):
        suggested_horizon = "MID"

    # Idempotency: prevent duplicate concurrent analyses for the same symbol+horizon
    key = (symbol, suggested_horizon)
    with _analyze_guard:
        if key not in _analyze_in_flight:
            _analyze_in_flight[key] = threading.Lock()
        lock = _analyze_in_flight[key]

    if not lock.acquire(blocking=False):
        raise HTTPException(
            status_code=409,
            detail=f"Analysis already in progress for {symbol} ({suggested_horizon}). Please wait for it to complete.",
        )

    logger.info(
        f"[bold cyan]API: /analyze {symbol} (horizon={suggested_horizon})[/bold cyan]"
    )

    try:
        try:
            result = run_analysis_pipeline(symbol, suggested_horizon=suggested_horizon)

            final_rec = result.get("final_recommendation", {}) or {}
            tech_output = result.get("technical_output", {}) or {}
            fund_output = result.get("fundamental_output", {}) or {}
            sent_output = result.get("sentiment_output", {}) or {}
            chart_output = result.get("chart_pattern_output", {}) or {}
            debate_output = result.get("debate_output")

            tech_summary = TechnicalSummary(
                signal=tech_output.get("signal", "HOLD"),
                confidence=tech_output.get("confidence", 0.0),
                narrative=tech_output.get("narrative", ""),
                key_levels=tech_output.get("key_levels"),
                current_price=tech_output.get("raw_data", {}).get("current_price"),
                atr=tech_output.get("raw_data", {}).get("atr"),
                rsi=tech_output.get("raw_data", {}).get("rsi"),
                raw_data=tech_output.get("raw_data"),
                sub_scores=tech_output.get("sub_scores"),
            )

            fund_summary = FundamentalSummary(
                signal=fund_output.get("signal", "HOLD"),
                confidence=fund_output.get("confidence", 0.0),
                weighted_score=fund_output.get("weighted_score", 0.0),
                narrative=fund_output.get("narrative", ""),
                strengths=fund_output.get("strengths", []) or [],
                weaknesses=fund_output.get("weaknesses", []) or [],
                sub_scores=fund_output.get("sub_scores"),
            )

            sent_headlines = []
            for h in (sent_output.get("scores", []) or [])[:20]:
                sent_headlines.append(
                    {
                        "text": h.get("headline", ""),
                        "score": round(float(h.get("score", 0)), 2),
                    }
                )
            sent_summary = SentimentSummary(
                signal=sent_output.get("signal", "HOLD"),
                confidence=sent_output.get("confidence", 0.0),
                aggregate_score=sent_output.get("aggregate_score", 0.0),
                narrative=sent_output.get("narrative", ""),
                key_themes=sent_output.get("key_themes", []) or [],
                anomaly_count=sent_output.get("anomaly_count", 0),
                headline_count=sent_output.get("headline_count", 0),
                fallback_used=sent_output.get("fallback_used", False),
                headlines=sent_headlines,
                sub_scores=sent_output.get("sub_scores"),
            )

            chart_summary = ChartPatternSummary(
                signal=chart_output.get("signal", "HOLD"),
                confidence=chart_output.get("confidence", 0.0),
                narrative=chart_output.get("narrative", ""),
                patterns_detected=chart_output.get("patterns_detected", []) or [],
                sub_scores=chart_output.get("sub_scores"),
            )

            debate_summary = DebateSummary(
                triggered=bool(result.get("debate_triggered", True)),
                bull_case=(debate_output or {}).get("bull_case"),
                bear_case=(debate_output or {}).get("bear_case"),
                missed_risks=(debate_output or {}).get("missed_risks", []) or [],
                independent_signal=(debate_output or {}).get("independent_signal"),
                independent_confidence=(debate_output or {}).get(
                    "independent_confidence"
                ),
                agrees_with_consensus=(debate_output or {}).get(
                    "agrees_with_consensus"
                ),
                synthesis=(debate_output or {}).get("synthesis"),
                evidence_citations=(debate_output or {}).get("evidence_citations", [])
                or [],
            )

            horizon_conf = HorizonConfirmation(
                suggested_horizon=result.get("suggested_horizon"),
                final_horizon=result.get("final_horizon"),
                override_reason=result.get("horizon_override_reason"),
                horizon_scores={},  # POC: validator stage doesn't currently expose raw scores
            )

            validator_issues = [
                ValidatorIssue(**i) if not isinstance(i, ValidatorIssue) else i
                for i in (result.get("validator_issues") or [])
                if isinstance(i, dict)
                and "layer" in i
                and "field" in i
                and "action" in i
            ]

            agent_signals = AgentSignals(
                technical=final_rec.get("agent_signals", {}).get("technical", "HOLD"),
                fundamental=final_rec.get("agent_signals", {}).get(
                    "fundamental", "HOLD"
                ),
                sentiment=final_rec.get("agent_signals", {}).get("sentiment", "HOLD"),
                chart_pattern=final_rec.get("agent_signals", {}).get(
                    "chart_pattern", "HOLD"
                ),
            )

            company_name = None
            try:
                import yfinance as yf

                info = yf.Ticker(symbol).info
                company_name = info.get("longName") or info.get("shortName")
            except Exception:
                pass

            response = AnalyzeResponse(
                run_id=result.get("run_id", "unknown"),
                symbol=symbol,
                company_name=company_name,
                recommendation=_verdict(final_rec.get("recommendation")),
                confidence=final_rec.get("confidence", 0.0),
                entry_price=final_rec.get("entry_price"),
                target_price=final_rec.get("target_price"),
                stop_loss=final_rec.get("stop_loss"),
                risk_reward=final_rec.get("risk_reward"),
                upside_pct=final_rec.get("upside_pct"),
                risk_pct=final_rec.get("risk_pct"),
                profit_pct=final_rec.get("profit_pct"),
                timeframe=final_rec.get("timeframe"),
                position_size_pct=final_rec.get("position_size_pct"),
                narrative=final_rec.get("narrative", ""),
                key_risks=final_rec.get("key_risks", []) or [],
                key_catalysts=final_rec.get("key_catalysts", []) or [],
                agent_signals=agent_signals,
                technical_summary=tech_summary,
                fundamental_summary=fund_summary,
                sentiment_summary=sent_summary,
                chart_pattern_summary=chart_summary,
                debate_summary=debate_summary,
                horizon_confirmation=horizon_conf,
                validator_issues=validator_issues,
                validator_status=result.get("validator_status", "accepted"),
                macro_regime=result.get("macro_regime", "SIDEWAYS"),
                market_pulse_score=result.get("market_pulse_score", 50),
                economic_score=result.get("economic_score"),
                economic_regime=result.get("economic_regime"),
                horizon=final_rec.get("horizon"),
                recommendation_id=final_rec.get("recommendation_id"),
                cost_per_analysis=final_rec.get("cost_per_analysis"),
                cost_per_analysis_inr=final_rec.get("cost_per_analysis_inr"),
                errors=result.get("errors", []) or [],
                created_at=datetime.now().isoformat() + "Z",
            )
            saved_file = _save_result_json(
                "analyze", response.model_dump(mode="json"), symbol=symbol
            )
            logger.info(
                f"[bold green]API: /analyze done — {symbol}: "
                f"{final_rec.get('recommendation', 'N/A')} @ {final_rec.get('confidence', 0)}% (saved: {saved_file})[/bold green]"
            )

            # Push WebSocket alert for analysis completion
            rec = _verdict(final_rec.get("recommendation"))
            conf = final_rec.get("confidence", 0)
            alert_type = (
                "TARGET_HIT"
                if rec == "BUY"
                else ("STOP_LOSS" if rec == "SELL" else "INFO")
            )
            push_alert(alert_type, f"{symbol}: {rec} signal @ {conf}% confidence")

            return response

        except Exception as e:
            logger.error(f"[bold red]API: /analyze {symbol} failed — {e}[/bold red]")
            push_alert("REVIEW_NEEDED", f"Analysis failed for {symbol}: {e}")
            raise HTTPException(
                status_code=500, detail=f"Analysis failed for {symbol}: {e}"
            )
    finally:
        lock.release()


# ══════════════════════════════════════════════════════════════
# Helpers (unchanged math)
# ══════════════════════════════════════════════════════════════

# Duration strings tiered by horizon (fallback when F1 LLM doesn't supply suggested_hold_days)
_DURATION_BY_HORIZON: dict[str, dict[str, str]] = {
    "SHORT": {
        "crisis": "1-3 Days (High Risk)",
        "high": "3-7 Days (Volatile)",
        "med": "1-2 Weeks (Swing)",
        "low": "2-3 Weeks (Stable)",
    },
    "MID": {
        "crisis": "2-4 Weeks (High Risk)",
        "high": "4-6 Weeks (Volatile)",
        "med": "1-2 Months (Swing)",
        "low": "2-3 Months (Position)",
    },
    "LONG": {
        "crisis": "1-3 Months (High Risk)",
        "high": "3-6 Months (Volatile)",
        "med": "6-12 Months (Position)",
        "low": "12-24 Months (Compounder)",
    },
}


def _set_pick_metadata(stock: DiscoveredStock) -> None:
    has_tech = (
        stock.rsi is not None
        and stock.relative_volume is not None
        and stock.ema20 is not None
    )
    has_fund = stock.pe_ratio is not None and stock.roe is not None
    if has_tech and has_fund:
        stock.pick_type = "Both"
    elif has_fund:
        stock.pick_type = "Fundamental"
    else:
        stock.pick_type = "Technical"

    # Use LLM-supplied hold days if available, else fall back to horizon-tier defaults
    if stock.suggested_hold_days:
        h = (stock.horizon or "MID").upper()
        days = stock.suggested_hold_days
        if h == "SHORT":
            lo, hi = max(1, round(days * 0.8)), round(days * 1.2)
            stock.holding_period = f"{lo}–{hi} days"
        elif h == "MID":
            weeks = max(1, round(days / 7))
            lo, hi = max(1, weeks - 1), weeks + 1
            stock.holding_period = f"{lo}–{hi} weeks"
        else:  # LONG
            months = max(1, round(days / 30))
            lo, hi = max(1, months - 1), months + 1
            stock.holding_period = f"{lo}–{hi} months"
    else:
        h = (stock.horizon or "MID").upper()
        dur_map = _DURATION_BY_HORIZON.get(h, _DURATION_BY_HORIZON["MID"])
        stock.holding_period = dur_map["med"]

    if stock.indicative_target and stock.close and stock.close > 0:
        stock.expected_return_pct = round(
            ((stock.indicative_target - stock.close) / stock.close) * 100, 2
        )


def _persist_discovery_result(result: dict):
    """Persist F1 pipeline output to DB. Runs inline but catches all exceptions."""
    try:
        run_id = result.get("run_id", "")
        buckets = result.get("discovered_buckets", {}) or {}
        persist_discovery_run(run_id, result, buckets)
    except Exception as e:
        logger.error(f"[red]Discovery DB persist error: {e}[/red]")

    # economic_snapshot is already persisted by economic_node during F1 run
    # Update it with market_pulse fields that are fetched later
    try:
        from app.db.models import EconomicSnapshots

        today = _ist_today()
        db = SessionLocal()
        try:
            snap = (
                db.query(EconomicSnapshots)
                .filter(EconomicSnapshots.snapshot_date == today)
                .first()
            )
            if snap:
                if result.get("india_vix") is not None:
                    snap.india_vix = result["india_vix"]
                if result.get("nifty_level") is not None:
                    snap.nifty_level = result["nifty_level"]
                if result.get("advance_decline_ratio") is not None:
                    snap.advance_decline_ratio = result["advance_decline_ratio"]
                db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()
    except Exception as e:
        logger.error(f"[red]Economic pulse update error: {e}[/red]")

    # market_regime is persisted here since no single node owns it
    try:
        macro = result.get("macro_regime", "SIDEWAYS")
        confidence = result.get("macro_confidence", 0.0)
        triggers = result.get("macro_triggers") or {}
        pulse = result.get("market_pulse_score", 50)
        persist_market_regime(macro, confidence, triggers, pulse)
    except Exception as e:
        logger.error(f"[red]Market regime persist error: {e}[/red]")


def _generate_overall_summary(
    stocks: list[DiscoveredStock], macro_regime: str, pulse: int
) -> str | None:
    if not stocks:
        return None
    return (
        f"Market scan completed in {macro_regime} regime (pulse: {pulse}/100). "
        f"Found {len(stocks)} stocks distributed across active horizons."
    )


def _safe_float(val):
    if val is None:
        return None
    try:
        f = float(val)
        import math

        return None if math.isnan(f) or math.isinf(f) else round(f, 4)
    except (ValueError, TypeError):
        return None


def _safe_int(val):
    if val is None:
        return None
    try:
        f = float(val)
        import math

        return None if math.isnan(f) else int(f)
    except (ValueError, TypeError):
        return None


# ══════════════════════════════════════════════════════════════
# POST /analysis/dispatch/{run_id}  — "Analyse All" button
# GET  /analysis/status/{run_id}    — per-symbol progress
# ══════════════════════════════════════════════════════════════


@router.post(
    "/dispatch/{run_id}", summary="Trigger F2 on all stocks from a discovery run"
)
def dispatch_analysis(
    run_id: str,
    background_tasks: BackgroundTasks,
    force_refresh: bool = True,
    horizon: str | None = Query(
        None,
        description="Restrict dispatch to one horizon: SHORT | MID | LONG | ALL (default ALL). "
        "Use SHORT/MID/LONG to keep free-tier quota under control (rushil.md §4).",
    ),
):
    """
    Kick off F2 analysis for all stocks from a discovery run.
    force_refresh=true  — re-analyze even if today's result exists (default for manual mode).
    force_refresh=false — reuse today's DB result for each stock (skips LLM calls).
    horizon            — SHORT/MID/LONG to dispatch only one bucket, ALL for everything.

    Returns immediately — poll GET /analysis/status/{run_id} for progress.
    """
    from app.services.analysis_dispatcher import dispatch_analysis as _dispatch
    from app.services.discovery_persist import fetch_discovery_run_buckets

    # Idempotency: prevent duplicate concurrent dispatches for the same run_id
    with _dispatch_guard:
        if _dispatch_in_flight.get(run_id):
            raise HTTPException(
                status_code=409,
                detail=f"Dispatch already running for run {run_id}. Check GET /analysis/status/{run_id} for progress.",
            )
        _dispatch_in_flight[run_id] = True

    buckets = fetch_discovery_run_buckets(run_id)
    if not buckets or sum(len(v) for v in buckets.values()) == 0:
        with _dispatch_guard:
            _dispatch_in_flight.pop(run_id, None)
        raise HTTPException(
            status_code=404,
            detail="No discovery result found in DB for this run_id. Run POST /analysis/discover first.",
        )

    # Per-horizon filter
    if horizon and horizon.upper() != "ALL":
        h = horizon.upper()
        if h not in ("SHORT", "MID", "LONG"):
            with _dispatch_guard:
                _dispatch_in_flight.pop(run_id, None)
            raise HTTPException(
                status_code=400, detail="horizon must be SHORT, MID, LONG, or ALL"
            )
        buckets = {h: buckets.get(h, [])}
        if not buckets[h]:
            with _dispatch_guard:
                _dispatch_in_flight.pop(run_id, None)
            raise HTTPException(
                status_code=404,
                detail=f"No stocks in {h} bucket for this run_id. Run discovery for that horizon first.",
            )

    total = sum(len(v) for v in buckets.values())

    def _clear_dispatch_flag():
        with _dispatch_guard:
            _dispatch_in_flight.pop(run_id, None)

    try:
        background_tasks.add_task(
            _dispatch,
            run_id,
            buckets,
            84.0,
            force_refresh,
            on_complete=_clear_dispatch_flag,
        )
    except Exception:
        with _dispatch_guard:
            _dispatch_in_flight.pop(run_id, None)
        raise

    logger.info(
        f"[bold cyan]API: /dispatch/{run_id} — queuing {total} stocks "
        f"(horizon={horizon or 'ALL'}, force_refresh={force_refresh})[/bold cyan]"
    )
    return {
        "run_id": run_id,
        "horizon": horizon or "ALL",
        "queued": total,
        "force_refresh": force_refresh,
        "message": f"F2 analysis started for {total} stocks ({horizon or 'ALL'}). Poll /analysis/status/{run_id}",
    }


@router.get("/status/{run_id}", summary="Per-symbol F2 analysis progress")
def get_analysis_status(run_id: str):
    """
    Returns progress for each stock dispatched under this run_id.
    {
      "run_id": "...",
      "total": 30,
      "done": 12,
      "running": 3,
      "queued": 15,
      "errors": 0,
      "complete": false,
      "stocks": {
        "RELIANCE": {"status": "done", "recommendation": "BUY", "confidence": 72, "cost_inr": 3.61},
        "TCS":      {"status": "running", ...},
        ...
      }
    }
    """
    from app.services.analysis_dispatcher import get_status

    return get_status(run_id)


@router.post("/cancel/{run_id}", summary="Cancel an active F2 analysis dispatch run")
def cancel_analysis(run_id: str):
    """Cancel any remaining queued stock analyses in a dispatch run."""
    from app.services.analysis_dispatcher import cancel_dispatch

    cancel_dispatch(run_id)
    with _dispatch_guard:
        _dispatch_in_flight.pop(run_id, None)
    return {
        "run_id": run_id,
        "status": "cancelled",
        "message": "Analysis run cancellation requested.",
    }


# ══════════════════════════════════════════════════════════════
# GET /analysis/results  — list + retrieve saved JSON result files
# ══════════════════════════════════════════════════════════════


@router.get("/results", summary="List all saved result JSON files")
def list_results():
    """Returns metadata for every file in the results/ directory."""
    results_dir = "results"
    if not os.path.isdir(results_dir):
        return {"files": []}
    files = []
    for fname in sorted(os.listdir(results_dir), reverse=True):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(results_dir, fname)
        stat = os.stat(fpath)
        files.append(
            {
                "filename": fname,
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            }
        )
    return {"files": files}


@router.get("/results/{filename}", summary="Return content of a saved result JSON file")
def get_result(filename: str):
    """Fetch the JSON content of a specific saved result file."""
    # Guard against path traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="Only .json files are accessible")
    fpath = os.path.join("results", filename)
    if not os.path.isfile(fpath):
        raise HTTPException(status_code=404, detail="File not found")
    with open(fpath, "r") as f:
        return json.load(f)


# ══════════════════════════════════════════════════════════════
# GET /analysis/history
# ══════════════════════════════════════════════════════════════


@router.get("/history", summary="Get past recommendations from DB")
def get_history(
    symbol: str | None = None,
    signal: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 20,
    page: int = 1,
):
    from app.core.config import SessionLocal
    from app.db.models import Recommendations, Stocks
    import datetime

    db = SessionLocal()
    try:
        q = (
            db.query(Recommendations, Stocks.symbol.label("stock_symbol"))
            .join(Stocks, Recommendations.stock_id == Stocks.id)
            .order_by(Recommendations.created_at.desc())
        )
        if symbol:
            q = q.filter(Stocks.symbol.ilike(f"%{symbol.upper()}%"))
        if signal:
            sig = signal.upper()
            if sig == "WAIT":
                # Legacy rows were saved as HOLD before the labels were merged
                q = q.filter(Recommendations.recommendation.in_(("WAIT", "HOLD")))
            else:
                q = q.filter(Recommendations.recommendation == sig)
        if date_from:
            try:
                dt = datetime.datetime.strptime(date_from, "%Y-%m-%d")
                q = q.filter(Recommendations.created_at >= dt)
            except ValueError:
                pass
        if date_to:
            try:
                dt = datetime.datetime.strptime(
                    date_to, "%Y-%m-%d"
                ) + datetime.timedelta(days=1)
                q = q.filter(Recommendations.created_at < dt)
            except ValueError:
                pass

        total = q.count()
        if page < 1:
            page = 1
        if limit < 1:
            limit = 20
        total_pages = max(1, -(-total // limit))  # ceil division
        offset = (page - 1) * limit
        rows = q.offset(offset).limit(limit).all()
        results = []
        for rec, sym in rows:

            def _safe(v):
                if v is None:
                    return None
                try:
                    import math

                    f = float(v)
                    return None if math.isnan(f) or math.isinf(f) else round(f, 2)
                except (ValueError, TypeError):
                    return None

            results.append(
                {
                    "id": str(rec.id),
                    "symbol": sym,
                    "recommendation": _verdict(rec.recommendation),
                    "confidence": _norm_confidence(_safe(rec.confidence)),
                    "entry_price": _safe(rec.entry_price),
                    "target_price": _safe(rec.target_price),
                    "stop_loss": _safe(rec.stop_loss),
                    "timeframe": rec.timeframe,
                    "status": rec.status,
                    "created_at": rec.created_at.isoformat()
                    if rec.created_at
                    else None,
                    "narrative": rec.reasoning.get("narrative", "")
                    if rec.reasoning
                    else "",
                    "key_risks": rec.reasoning.get("key_risks", [])
                    if rec.reasoning
                    else [],
                    "key_catalysts": rec.reasoning.get("key_catalysts", [])
                    if rec.reasoning
                    else [],
                    "macro_regime": rec.reasoning.get("macro_regime", "")
                    if rec.reasoning
                    else "",
                    "horizon": getattr(rec, "horizon", None),
                }
            )
        return {
            "count": total,
            "page": page,
            "total_pages": total_pages,
            "recommendations": results,
        }

    except Exception as e:
        logger.error(f"[red]History endpoint failed: {e}[/red]")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════
# GET /analysis/history/{rec_id}  — single recommendation detail
# ══════════════════════════════════════════════════════════════


@router.get("/history/{rec_id}", summary="Full detail of a single saved recommendation")
def get_history_detail(rec_id: str):
    """Reconstruct a full analysis view from a saved recommendation row.
    Returns an AnalyzeResponse-shaped dict so the frontend can render it
    identically to a live /analyze result."""
    from app.core.config import SessionLocal
    from app.db.models import Recommendations, Stocks
    import math

    db = SessionLocal()
    try:
        row = (
            db.query(Recommendations, Stocks.symbol.label("stock_symbol"))
            .join(Stocks, Recommendations.stock_id == Stocks.id)
            .filter(Recommendations.id == rec_id)
            .first()
        )
        if not row:
            raise HTTPException(
                status_code=404, detail=f"Recommendation {rec_id} not found"
            )
        rec, sym = row

        # Fast path: return the full stored snapshot if available
        if rec.full_response:
            payload = dict(rec.full_response)
            payload["recommendation"] = _verdict(payload.get("recommendation"))
            payload["_source"] = "db"
            payload["_saved_at"] = (
                rec.created_at.isoformat() if rec.created_at else None
            )
            payload["created_at"] = (
                rec.created_at.isoformat() if rec.created_at else None
            )
            payload["recommendation_id"] = str(rec.id)
            payload.setdefault("symbol", sym)
            payload.setdefault("timeframe", rec.timeframe)
            return payload

        def _safe(v):
            if v is None:
                return None
            try:
                f = float(v)
                return None if math.isnan(f) or math.isinf(f) else round(f, 4)
            except (ValueError, TypeError):
                return None

        reasoning = rec.reasoning or {}

        # Fallback: reconstruct per-agent summaries from the recommendation columns
        result = {
            "_source": "db",
            "_saved_at": rec.created_at.isoformat() if rec.created_at else None,
            "created_at": rec.created_at.isoformat() if rec.created_at else None,
            "run_id": str(rec.run_id) if rec.run_id else None,
            "symbol": sym,
            "recommendation": _verdict(rec.recommendation),
            "confidence": _norm_confidence(_safe(rec.confidence)),
            "entry_price": _safe(rec.entry_price),
            "target_price": _safe(rec.target_price),
            "stop_loss": _safe(rec.stop_loss),
            "risk_reward": _safe(rec.risk_reward),
            "position_size_pct": _safe(rec.position_size_pct),
            "timeframe": rec.timeframe,
            "horizon": rec.horizon,
            "narrative": rec.final_narrative or reasoning.get("narrative", ""),
            "key_risks": rec.key_risks or reasoning.get("key_risks", []),
            "key_catalysts": rec.key_catalysts or reasoning.get("key_catalysts", []),
            "validator_status": rec.validator_status,
            "validator_issues": rec.validator_issues or [],
            "macro_regime": reasoning.get("macro_regime", ""),
            "market_pulse_score": reasoning.get("market_pulse_score"),
            "economic_score": reasoning.get("economic_score"),
            "economic_regime": reasoning.get("economic_regime"),
            "cost_per_analysis": _safe(rec.cost_per_analysis),
            "cost_per_analysis_inr": _safe(rec.cost_per_analysis_inr),
            "agent_signals": {
                "technical": rec.technical_signal or "HOLD",
                "fundamental": rec.fundamental_signal or "HOLD",
                "sentiment": rec.sentiment_signal or "HOLD",
                "chart_pattern": rec.chart_signal or "HOLD",
            },
            "technical_summary": {
                "signal": rec.technical_signal or "HOLD",
                "confidence": _safe(rec.technical_confidence),
                "narrative": rec.technical_narrative or "",
            },
            "fundamental_summary": {
                "signal": rec.fundamental_signal or "HOLD",
                "confidence": _safe(rec.fundamental_confidence),
                "narrative": rec.fundamental_narrative or "",
            },
            "sentiment_summary": {
                "signal": rec.sentiment_signal or "HOLD",
                "confidence": _safe(rec.sentiment_confidence),
                "narrative": rec.sentiment_narrative or "",
            },
            "chart_pattern_summary": {
                "signal": rec.chart_signal or "HOLD",
                "confidence": _safe(rec.chart_confidence),
                "narrative": rec.chart_narrative or "",
            },
            "debate_summary": {
                "triggered": True,
                "bull_case": rec.debate_bull_case,
                "bear_case": rec.debate_bear_case,
                "agrees_with_consensus": rec.debate_agrees,
                "synthesis": rec.debate_synthesis,
                "missed_risks": rec.debate_missed_risks or [],
                "independent_signal": rec.debate_signal,
                "independent_confidence": _safe(rec.debate_confidence),
            },
            "horizon_confirmation": {
                "suggested_horizon": rec.f1_horizon,
                "final_horizon": rec.horizon,
                "override_reason": rec.horizon_override_reason,
            },
            "f1_catalyst": rec.f1_catalyst,
            "f1_reasoning": rec.f1_reasoning,
            "errors": [],
        }
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[red]History detail failed: {e}[/red]")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════
# GET /analysis/symbols/search?q=  -- typeahead symbol+name search
# ══════════════════════════════════════════════════════════════


@router.get("/symbols/search", summary="Typeahead search for stock symbols and names")
def search_symbols(q: str = "", limit: int = 15):
    """Return up to `limit` stocks whose symbol or name contains `q`.
    Uses yfinance Search for real company names (NSE/BSE preferred).
    Falls back to DB Stocks table if yfinance is unavailable."""
    if not q or len(q.strip()) < 1:
        return []

    query = q.strip()
    seen: set = set()
    indian: list = []
    global_fallback: list = []

    try:
        import yfinance as yf

        def _collect(quotes):
            for item in quotes:
                sym = item.get("symbol", "")
                ex = item.get("exchange", "")
                qt = item.get("quoteType", "EQUITY")
                if qt not in ("EQUITY", ""):
                    continue
                is_indian = (
                    ex in ("NSI", "BSE", "BOM")
                    or sym.endswith(".NS")
                    or sym.endswith(".BO")
                )
                clean = (
                    sym[:-3] if (sym.endswith(".NS") or sym.endswith(".BO")) else sym
                )
                if not clean or clean in seen:
                    continue
                seen.add(clean)
                name = item.get("longname") or item.get("shortname") or clean
                entry = {"symbol": clean, "name": name}
                if is_indian:
                    indian.append(entry)
                else:
                    global_fallback.append(entry)

        # 1) Treat query as NSE ticker: append .NS for direct symbol lookup
        try:
            _collect(yf.Search(query + ".NS", max_results=min(limit, 20)).quotes)
        except Exception:
            pass

        # 2) Treat query as company name / partial name
        try:
            _collect(yf.Search(query, max_results=min(limit * 2, 30)).quotes)
        except Exception:
            pass

    except Exception as e:
        logger.warning(f"[yellow]symbols/search yfinance error: {e}[/yellow]")

    # Indian stocks first; include global fallback only if no Indian results found
    results = indian if indian else global_fallback
    results = results[:limit]

    # Final fallback: DB Stocks table (when yfinance returned nothing at all)
    if not results and SessionLocal:
        db = SessionLocal()
        try:
            term = f"%{query.upper()}%"
            rows = (
                db.query(Stocks.symbol, Stocks.name)
                .filter((Stocks.symbol.ilike(term)) | (Stocks.name.ilike(f"%{query}%")))
                .order_by(Stocks.symbol)
                .limit(limit)
                .all()
            )
            results = [{"symbol": r.symbol, "name": r.name or r.symbol} for r in rows]
        except Exception:
            pass
        finally:
            db.close()

    return results


# ══════════════════════════════════════════════════════════════
# GET /analysis/latest/{symbol}  -- latest DB recommendation for a symbol
# ══════════════════════════════════════════════════════════════


@router.get("/latest/{symbol}", summary="Latest saved recommendation for a symbol")
def get_latest_for_symbol(symbol: str, horizon: str = None):
    """Return the most recent recommendation for a symbol from the DB.
    Used as a fallback when the in-memory dispatcher cache is lost (server restart)."""
    from app.core.config import SessionLocal
    from app.db.models import Recommendations, Stocks
    import math

    db = SessionLocal()
    try:
        q = (
            db.query(Recommendations, Stocks.symbol.label("stock_symbol"))
            .join(Stocks, Recommendations.stock_id == Stocks.id)
            .filter(Stocks.symbol == symbol.upper())
        )
        if horizon:
            q = q.filter(Recommendations.horizon == horizon.upper())
        row = q.order_by(Recommendations.created_at.desc()).first()

        if not row:
            raise HTTPException(
                status_code=404, detail=f"No recommendation found for {symbol}"
            )
        rec, sym = row

        if rec.full_response:
            payload = dict(rec.full_response)
            payload["recommendation"] = _verdict(payload.get("recommendation"))
            payload["_source"] = "db"
            payload["_saved_at"] = (
                rec.created_at.isoformat() if rec.created_at else None
            )
            payload["recommendation_id"] = str(rec.id)
            payload.setdefault("symbol", sym)
            payload.setdefault("timeframe", rec.timeframe)
            return payload

        # Minimal fallback for old records without full_response
        def _safe(v):
            if v is None:
                return None
            try:
                f = float(v)
                return None if math.isnan(f) or math.isinf(f) else round(f, 4)
            except (ValueError, TypeError):
                return None

        reasoning = rec.reasoning or {}
        return {
            "_source": "db",
            "_saved_at": rec.created_at.isoformat() if rec.created_at else None,
            "recommendation_id": str(rec.id),
            "run_id": str(rec.run_id) if rec.run_id else None,
            "symbol": sym,
            "recommendation": _verdict(rec.recommendation),
            "confidence": _norm_confidence(_safe(rec.confidence)),
            "entry_price": _safe(rec.entry_price),
            "target_price": _safe(rec.target_price),
            "stop_loss": _safe(rec.stop_loss),
            "risk_reward": _safe(rec.risk_reward),
            "position_size_pct": _safe(rec.position_size_pct),
            "timeframe": rec.timeframe,
            "horizon": rec.horizon,
            "narrative": rec.final_narrative or reasoning.get("narrative", ""),
            "key_risks": rec.key_risks or reasoning.get("key_risks", []),
            "key_catalysts": rec.key_catalysts or reasoning.get("key_catalysts", []),
            "validator_status": rec.validator_status,
            "validator_issues": rec.validator_issues or [],
            "macro_regime": reasoning.get("macro_regime", ""),
            "market_pulse_score": reasoning.get("market_pulse_score"),
            "cost_per_analysis_inr": _safe(rec.cost_per_analysis_inr),
            "agent_signals": {
                "technical": rec.technical_signal or "HOLD",
                "fundamental": rec.fundamental_signal or "HOLD",
                "sentiment": rec.sentiment_signal or "HOLD",
                "chart_pattern": rec.chart_signal or "HOLD",
            },
            "technical_summary": {
                "signal": rec.technical_signal or "HOLD",
                "confidence": _safe(rec.technical_confidence),
                "narrative": rec.technical_narrative or "",
            },
            "fundamental_summary": {
                "signal": rec.fundamental_signal or "HOLD",
                "confidence": _safe(rec.fundamental_confidence),
                "narrative": rec.fundamental_narrative or "",
            },
            "sentiment_summary": {
                "signal": rec.sentiment_signal or "HOLD",
                "confidence": _safe(rec.sentiment_confidence),
                "narrative": rec.sentiment_narrative or "",
            },
            "chart_pattern_summary": {
                "signal": rec.chart_signal or "HOLD",
                "confidence": _safe(rec.chart_confidence),
                "narrative": rec.chart_narrative or "",
            },
            "debate_summary": {
                "triggered": True,
                "bull_case": rec.debate_bull_case,
                "bear_case": rec.debate_bear_case,
                "agrees_with_consensus": rec.debate_agrees,
                "synthesis": rec.debate_synthesis,
                "missed_risks": rec.debate_missed_risks or [],
                "independent_signal": rec.debate_signal,
                "independent_confidence": _safe(rec.debate_confidence),
            },
            "horizon_confirmation": {
                "suggested_horizon": rec.f1_horizon,
                "final_horizon": rec.horizon,
                "override_reason": rec.horizon_override_reason,
            },
            "errors": [],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[red]Latest symbol lookup failed: {e}[/red]")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════
# POST /analysis/analyze_batch  -- parallel multi-stock analysis
# ══════════════════════════════════════════════════════════════

import time as _time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pydantic import BaseModel, Field as _Field
from typing import Optional as _Optional


class BatchItem(BaseModel):
    symbol: str
    suggested_horizon: _Optional[str] = None


class BatchAnalyzeRequest(BaseModel):
    """
    Two ways to specify what to analyze:
      1) `items`: explicit list of {symbol, suggested_horizon} pairs
      2) `from_discovery`: re-run /discover and analyze the top-N of a horizon
    """

    items: _Optional[list[BatchItem]] = None
    from_discovery: _Optional[bool] = _Field(
        False, description="If true, ignore `items` and pull from latest /discover"
    )
    horizon: _Optional[str] = _Field(
        None,
        description="When from_discovery=True, which bucket: SHORT/MID/LONG (default: all)",
    )
    top_n_per_horizon: _Optional[int] = _Field(
        5, ge=1, le=30, description="Per-horizon cap when from_discovery=True"
    )
    max_workers: _Optional[int] = _Field(
        4, ge=1, le=10, description="Parallel worker count (1-10)"
    )


def _analyze_one(symbol: str, horizon: str | None) -> dict:
    """Worker: run F2 for one stock, returning a flat summary dict (no exceptions raised)."""
    t0 = _time.time()
    try:
        result = run_analysis_pipeline(symbol, suggested_horizon=horizon)
        rec = result.get("final_recommendation", {}) or {}
        elapsed = round(_time.time() - t0, 2)
        return {
            "symbol": symbol,
            "ok": True,
            "elapsed_sec": elapsed,
            "recommendation": _verdict(rec.get("recommendation")),
            "confidence": rec.get("confidence", 0.0),
            "horizon": rec.get("horizon") or (result.get("final_horizon")) or horizon,
            "entry_price": rec.get("entry_price"),
            "target_price": rec.get("target_price"),
            "stop_loss": rec.get("stop_loss"),
            "risk_reward": rec.get("risk_reward"),
            "upside_pct": rec.get("upside_pct"),
            "risk_pct": rec.get("risk_pct"),
            "profit_pct": rec.get("profit_pct"),
            "position_size_pct": rec.get("position_size_pct"),
            "validator_status": result.get("validator_status"),
            "narrative": rec.get("narrative", ""),
        }
    except Exception as e:
        elapsed = round(_time.time() - t0, 2)
        logger.error(f"[red]Batch analyze failed for {symbol}: {e}[/red]")
        return {
            "symbol": symbol,
            "ok": False,
            "elapsed_sec": elapsed,
            "error": str(e),
            "horizon": horizon,
        }


@router.post("/analyze_batch", summary="Run F2 analysis on many stocks in parallel")
def analyze_batch(request: BatchAnalyzeRequest):
    """
    Run the F2 analysis pipeline on multiple stocks concurrently.
    Returns a list of compact result dicts ordered by completion time.
    Total wall-clock ≈ ceil(N / max_workers) * (per-stock latency).
    """
    # Build target list
    targets: list[tuple[str, str | None]] = []

    if request.from_discovery:
        logger.info(
            "[bold cyan]API: /analyze_batch — pulling targets from cached discovery[/bold cyan]"
        )
        disc_resp = discover_cached()
        buckets = disc_resp.buckets or {}
        horizons = (
            [request.horizon.upper()] if request.horizon else ["SHORT", "MID", "LONG"]
        )
        for h in horizons:
            for stock in (buckets.get(h) or [])[: request.top_n_per_horizon]:
                targets.append((stock.symbol, h))
    elif request.items:
        for it in request.items:
            h = (it.suggested_horizon or "MID").upper()
            if h not in ("SHORT", "MID", "LONG"):
                h = "MID"
            targets.append((it.symbol.upper().strip(), h))
    else:
        raise HTTPException(
            status_code=400, detail="Provide either `items` or `from_discovery: true`"
        )

    if not targets:
        return {"count": 0, "results": [], "message": "No targets to analyze"}

    # Cap to a sane parallelism
    workers = min(request.max_workers or 4, max(1, len(targets)))
    logger.info(
        f"[bold cyan]API: /analyze_batch running {len(targets)} stocks across {workers} workers[/bold cyan]"
    )

    t_start = _time.time()
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {pool.submit(_analyze_one, sym, h): sym for sym, h in targets}
        for fut in as_completed(future_map):
            results.append(fut.result())

    total_elapsed = round(_time.time() - t_start, 2)

    # Summary stats
    n_ok = sum(1 for r in results if r.get("ok"))
    n_buy = sum(1 for r in results if r.get("recommendation") == "BUY")
    n_sell = sum(1 for r in results if r.get("recommendation") == "SELL")
    n_wait = sum(1 for r in results if r.get("recommendation") == "WAIT")

    logger.info(
        f"[bold green]API: /analyze_batch DONE — {n_ok}/{len(results)} ok in {total_elapsed}s "
        f"(BUY={n_buy} SELL={n_sell} WAIT={n_wait})[/bold green]"
    )

    return {
        "count": len(results),
        "ok_count": n_ok,
        "elapsed_sec": total_elapsed,
        "workers": workers,
        "summary": {"BUY": n_buy, "SELL": n_sell, "WAIT": n_wait},
        "results": results,
    }


# ══════════════════════════════════════════════════════════════
# POST /analysis/test-agent  -- Isolated single agent testing
# ══════════════════════════════════════════════════════════════


class TestAgentRequest(BaseModel):
    symbol: str
    agent: str
    horizon: str = "MID"
    mock_data: _Optional[dict] = None
    custom_api_key: _Optional[str] = None
    custom_model: _Optional[str] = None


@router.post(
    "/test-agent",
    summary="Test a single LangGraph agent in isolation with optional mock data",
)
def test_single_agent(req: TestAgentRequest):
    """
    Test a single LangGraph node (e.g., 'technical', 'chart_pattern') in complete isolation.
    Bypasses all other nodes, debate, and validation.
    """
    from app.agents.graph import _get_default_state

    # Import the node functions
    from app.agents.technical.node import technical_node
    from app.agents.fundamental.node import fundamental_node
    from app.agents.sentiment.node import sentiment_node
    from app.agents.chart_pattern.node import chart_pattern_node
    from app.agents.economic.node import economic_node
    from app.agents.market_pulse.node import market_pulse_node
    from app.agents.news.node import news_node
    from app.agents.macro_context.node import macro_context_node

    symbol = req.symbol.upper().strip()
    horizon = req.horizon.upper().strip()
    agent = req.agent.lower().strip()

    # Create an isolated mock state
    state = _get_default_state("analyze", symbol, horizon)

    # Enable debug tracing and inject mock data if provided
    state["_debug_mode"] = True
    if req.mock_data:
        state["_mock_data"] = req.mock_data
    if req.custom_api_key:
        if req.custom_api_key == "GOOGLE_KEY_1":
            state["_custom_api_key"] = getattr(settings, "LLM_API_KEY_1", None)
        elif req.custom_api_key == "GOOGLE_KEY_2":
            state["_custom_api_key"] = getattr(settings, "LLM_API_KEY_2", None)
        elif req.custom_api_key == "GOOGLE_KEY_3":
            state["_custom_api_key"] = getattr(settings, "LLM_API_KEY_3", None)
        else:
            state["_custom_api_key"] = req.custom_api_key
    if req.custom_model:
        state["_custom_model"] = req.custom_model

    # Map the requested agent string to its function
    agent_map = {
        "technical": technical_node,
        "fundamental": fundamental_node,
        "sentiment": sentiment_node,
        "chart_pattern": chart_pattern_node,
        "economic": economic_node,
        "market_pulse": market_pulse_node,
        "news": news_node,
        "macro_context": macro_context_node,
    }

    if agent not in agent_map:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown agent: '{agent}'. Available agents: {list(agent_map.keys())}",
        )

    try:
        node_func = agent_map[agent]
        logger.info(
            f"[bold cyan]API: /test-agent running '{agent}' for {symbol}[/bold cyan]"
        )

        import time

        start_time = time.time()
        result_state = node_func(state)
        elapsed = round(time.time() - start_time, 2)

        # The node function returns a dict that updates the state
        # For specialists it's typically {agent}_output, for F1 nodes it's various keys.
        output_key = f"{agent}_output"
        if output_key in result_state:
            output_data = result_state[output_key]
        else:
            # If it's an F1 node like market_pulse, it just returns the state delta
            output_data = result_state

        logger.info(
            f"[bold green]API: /test-agent '{agent}' done in {elapsed}s[/bold green]"
        )

        from app.core.config import settings

        return {
            "symbol": symbol,
            "agent": agent,
            "horizon": horizon,
            "elapsed_sec": elapsed,
            "model_used": req.custom_model or settings.LLM_MODEL_NAME,
            "output": output_data,
        }
    except Exception as e:
        # Capture the message first; the Rich logger can itself throw a
        # UnicodeEncodeError on the Windows console when the error string carries
        # emoji/markup, which would otherwise escape as a bare 500 and skip the
        # salvage below. So logging is best-effort and must not mask the error.
        err_msg = str(e)
        try:
            logger.error(f"Test agent '{agent}' failed for {symbol}: {err_msg!r}")
        except Exception:
            pass
        # Debugger UX: the specialist nodes re-raise on LLM failure (e.g. a denied
        # API key → 403) AFTER the no-LLM tool layer has already computed raw_data.
        # Since the whole point of this endpoint is inspecting the per-horizon Input
        # Data, salvage raw_data from the tool layer so the "Input Data" tab still
        # updates instead of going stale. The narrative/signal are reported as failed.
        from app.core.config import settings as _settings

        salvaged_raw = _salvage_raw_data(agent, symbol, horizon)
        if salvaged_raw is not None:
            return {
                "symbol": symbol,
                "agent": agent,
                "horizon": horizon,
                "elapsed_sec": 0.0,
                "model_used": req.custom_model or _settings.LLM_MODEL_NAME,
                "llm_error": err_msg,
                "output": {
                    "symbol": symbol,
                    "signal": "ERROR",
                    "confidence": 0.0,
                    "narrative": f"<p style='color:#f87171'>LLM step failed: {err_msg[:300]}</p>"
                    f"<p>Input Data below was still fetched (horizon={horizon}).</p>",
                    "raw_data": salvaged_raw,
                },
            }
        raise HTTPException(status_code=500, detail=err_msg)


def _salvage_raw_data(agent: str, symbol: str, horizon: str):
    """Best-effort: re-run ONLY the no-LLM tool layer so the debugger can still
    show per-horizon Input Data when the node's LLM call failed. Returns None if
    the agent has no tool-layer raw_data or the fetch itself fails."""
    try:
        if agent == "technical":
            from app.agents.technical.tools import get_technical_data

            return get_technical_data(symbol, horizon=horizon)
        if agent == "chart_pattern":
            from app.agents.chart_pattern.tools import get_chart_pattern_data

            return get_chart_pattern_data(symbol, horizon=horizon)
        if agent == "fundamental":
            from app.agents.fundamental.tools import (
                get_fundamental_data,
                compute_fundamental_score,
            )
            from app.core.horizon_params import fundamental_weights

            data = get_fundamental_data(symbol)
            score = compute_fundamental_score(data, horizon=horizon)
            return {
                "horizon": horizon,
                "horizon_weighted_score": score,
                "scoring_weights": fundamental_weights(horizon),
                **{
                    k: data.get(k)
                    for k in (
                        "pe_ratio",
                        "roe",
                        "roce",
                        "debt_to_equity",
                        "revenue_growth",
                        "earnings_growth",
                        "net_margin",
                        "promoter_holding",
                        "market_cap_cr",
                        "sector",
                    )
                },
            }
        if agent == "sentiment":
            from app.agents.sentiment.tools import get_all_headlines
            from app.core.horizon_params import news_days

            hl = get_all_headlines(symbol, horizon=horizon)
            return {
                "horizon": horizon,
                "news_window_days": news_days(horizon),
                "headline_count": len(hl),
                "headlines": [h.get("text") for h in hl],
            }
    except Exception as salvage_err:
        logger.warning(
            f"[yellow]Test agent salvage failed for {agent}/{symbol}: {salvage_err}[/yellow]"
        )
    return None


# ══════════════════════════════════════════════════════════════
# DELETE /analysis/reset  — wipe all analysis data from DB
# ══════════════════════════════════════════════════════════════


@router.delete("/reset", summary="Delete ALL analysis data from the database")
def reset_all_data(confirm: str = ""):
    """
    Permanently deletes all rows from every analysis table.
    Requires ?confirm=YES_DELETE_ALL to execute.

    Deletion order respects foreign-key constraints:
      trade_monitor_logs → paper_trades → recommendation_updates
      → agent_logs → discovery_results → recommendations → runs → stocks
      + market_regimes, economic_snapshots, agent_performance_stats, performance_analysis
    """
    if confirm != "YES_DELETE_ALL":
        raise HTTPException(
            status_code=400,
            detail="Pass ?confirm=YES_DELETE_ALL to confirm. This action is irreversible.",
        )

    from app.core.config import SessionLocal
    from app.db.models import (
        TradeMonitorLogs,
        PaperTrades,
        RecommendationUpdates,
        AgentLogs,
        DiscoveryResults,
        Recommendations,
        Runs,
        Stocks,
        MarketRegimes,
        EconomicSnapshots,
        AgentPerformanceStats,
        PerformanceAnalysis,
    )
    from sqlalchemy import text as _text

    if not SessionLocal:
        raise HTTPException(status_code=503, detail="Database not available")

    db = SessionLocal()
    counts = {}
    try:
        # Delete in FK-safe order (children before parents)
        for model in [
            TradeMonitorLogs,
            PaperTrades,
            RecommendationUpdates,
            AgentLogs,
            DiscoveryResults,
            Recommendations,
            Runs,
            Stocks,
            MarketRegimes,
            EconomicSnapshots,
            AgentPerformanceStats,
            PerformanceAnalysis,
        ]:
            n = db.query(model).delete(synchronize_session=False)
            counts[model.__tablename__] = n

        db.commit()
        logger.warning("[bold red]RESET: all analysis data deleted from DB[/bold red]")
        return {
            "status": "deleted",
            "deleted_rows": counts,
            "total": sum(counts.values()),
        }

    except Exception as e:
        db.rollback()
        logger.error(f"[red]RESET failed: {e}[/red]")
        raise HTTPException(status_code=500, detail=f"Reset failed: {e}")
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════
# GET /analysis/cost-estimate
# ══════════════════════════════════════════════════════════════


@router.get("/cost-estimate", summary="Estimated cost per stock analysis")
def get_cost_estimate():
    """Returns estimated INR cost per stock for F2 analysis based on model tiers."""
    from app.core.model_router import (
        compute_cost,
        cost_usd_to_inr,
        get_model_id,
        ModelTier,
    )

    shared_cost = (
        compute_cost(get_model_id(ModelTier.FLASH_LITE), 2000, 500)
        + compute_cost(get_model_id(ModelTier.FLASH), 2500, 500)
        + compute_cost(get_model_id(ModelTier.PRO), 3500, 400)
        + compute_cost(get_model_id(ModelTier.PRO), 2500, 800)
    )
    specialist_cost = 4 * compute_cost(get_model_id(ModelTier.FLASH), 3000, 600)
    debate_cost = compute_cost(get_model_id(ModelTier.PRO_THINK), 6000, 1500)
    decision_cost = compute_cost(get_model_id(ModelTier.PRO), 5000, 1200)

    total_usd = shared_cost + specialist_cost + debate_cost + decision_cost
    total_inr = cost_usd_to_inr(total_usd, 84.0)

    return {
        "per_stock_usd": round(total_usd, 4),
        "per_stock_inr": round(total_inr, 2),
        "usd_inr_rate": 84.0,
        "breakdown": {
            "shared_preamble_inr": round(cost_usd_to_inr(shared_cost, 84.0), 2),
            "specialists_4x_inr": round(cost_usd_to_inr(specialist_cost, 84.0), 2),
            "debate_pro_think_inr": round(cost_usd_to_inr(debate_cost, 84.0), 2),
            "decision_pro_inr": round(cost_usd_to_inr(decision_cost, 84.0), 2),
        },
        "note": "Estimates based on average token usage. Actual cost varies by stock complexity.",
    }
