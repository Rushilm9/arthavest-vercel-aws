"""
News Agent — Tools (MCP-first)

Primary:  news.get_market_news from MCP (9 RSS sources, pre-deduped, weighted)
Fallback: local feedparser Google News scrape
"""

from app.core.config import logger
from app.services.mcp_client import mcp_safe


def fetch_market_headlines(limit: int = 20) -> list[str]:
    """
    Returns a flat list of headline strings for the News Agent's LLM prompt.
    MCP returns rich objects — we extract titles here.
    """
    result = mcp_safe("news.get_market_news", {"count": max(limit, 20)})

    if result and isinstance(result, list):
        headlines = []
        seen: set[str] = set()
        for item in result:
            title = (item.get("title") or "").strip()
            if not title or title.lower() in seen:
                continue
            seen.add(title.lower())
            headlines.append(title)
            if len(headlines) >= limit:
                break
        if headlines:
            logger.info(
                f"[green]News tools: {len(headlines)} headlines from MCP[/green]"
            )
            return headlines

    # ── Fallback ──────────────────────────────────────────────────────────────
    logger.warning(
        "[yellow]News tools: MCP unavailable, falling back to local RSS[/yellow]"
    )
    from app.services.news_service import get_macro_headlines

    raw = get_macro_headlines() or []
    seen_local: set[str] = set()
    cleaned: list[str] = []
    for h in raw:
        h = (h or "").strip()
        if not h or h.lower() in seen_local:
            continue
        seen_local.add(h.lower())
        cleaned.append(h)
        if len(cleaned) >= limit:
            break
    return cleaned


def fetch_stock_news(symbol: str, limit: int = 20) -> list[dict]:
    """
    Returns rich news objects for a specific stock (used by sentiment agent).
    MCP news.get_stock_news returns: title, source, published_at, url,
    weight_final, anomaly_candidate, auto_trigger_debate
    """
    result = mcp_safe("news.get_stock_news", {"symbol": symbol, "days": 7})

    if result and isinstance(result, list):
        logger.info(
            f"[green]News tools: {len(result)} items from MCP for {symbol}[/green]"
        )
        return result[:limit]

    # Fallback — return simple title-only dicts from local RSS
    logger.warning(
        f"[yellow]News tools: MCP stock news failed for {symbol}, using local RSS[/yellow]"
    )
    from app.services.news_service import get_stock_news

    titles = get_stock_news(symbol) or []
    return [
        {
            "title": t,
            "source": "google_news",
            "weight_final": 1.0,
            "anomaly_candidate": False,
            "auto_trigger_debate": False,
        }
        for t in titles[:limit]
    ]
