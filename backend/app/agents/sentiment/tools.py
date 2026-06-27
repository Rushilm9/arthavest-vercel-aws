"""
Sentiment Agent — Tools (MCP-first)
Data-fetching for headlines from MCP news.get_stock_news (9 RSS sources)
+ Reddit r/IndianStreetBets. No LLM here — just data collection.
"""

from app.services.mcp_client import mcp_safe
from app.services.news_service import get_stock_news as _local_get_stock_news
from app.services.sentiment_service import score_headline
from app.core.horizon_params import news_days
from app.core.config import logger
from typing import Optional
import os


def get_all_headlines(symbol: str, horizon: str | None = None) -> list[dict]:
    """
    Fetches headlines from all available sources.
    Returns a list of dicts: [{"text": "...", "source": "...",
                                "anomaly_candidate": bool,
                                "auto_trigger_debate": bool}, ...]

    `horizon` (SHORT/MID/LONG) controls the news recency window: a SHORT
    horizon looks at the last 7 days, MID 14, LONG 30.
    """
    headlines = []
    days = news_days(horizon)

    # ── Source 1: MCP news.get_stock_news (9 RSS feeds, weighted, anomaly-flagged)
    mcp_items = mcp_safe("news.get_stock_news", {"symbol": symbol, "days": days})
    if mcp_items and isinstance(mcp_items, list):
        for item in mcp_items:
            title = (item.get("title") or "").strip()
            if title:
                headlines.append(
                    {
                        "text": title,
                        "source": item.get("source", "mcp_news"),
                        "anomaly_candidate": bool(item.get("anomaly_candidate", False)),
                        "auto_trigger_debate": bool(
                            item.get("auto_trigger_debate", False)
                        ),
                    }
                )
        logger.info(
            f"[green]Sentiment: {len(mcp_items)} headlines from MCP for {symbol}[/green]"
        )
    else:
        # Fallback — single Google News RSS scrape
        logger.warning(
            f"[yellow]Sentiment: MCP news failed for {symbol}, using local RSS[/yellow]"
        )
        for h in _local_get_stock_news(symbol) or []:
            headlines.append(
                {
                    "text": h,
                    "source": "google_news",
                    "anomaly_candidate": False,
                    "auto_trigger_debate": False,
                }
            )

    # ── Source 2: Reddit r/IndianStreetBets (optional) ─────────────────────
    reddit_headlines = _fetch_reddit_posts(symbol)
    for h in reddit_headlines:
        headlines.append(
            {
                "text": h,
                "source": "reddit",
                "anomaly_candidate": False,
                "auto_trigger_debate": False,
            }
        )

    if reddit_headlines:
        logger.info(
            f"[green]Sentiment: {len(reddit_headlines)} Reddit posts for {symbol}[/green]"
        )

    if not headlines:
        logger.warning(
            f"[yellow]Sentiment: No headlines found from any source for {symbol}. Injecting system fallback headline.[/yellow]"
        )
        headlines.append(
            {
                "text": f"No recent regulatory filings or public news stories found for {symbol} in the last 7 days.",
                "source": "system_fallback",
                "anomaly_candidate": False,
                "auto_trigger_debate": False,
            }
        )

    logger.info(
        f"[green]Sentiment: Total {len(headlines)} headlines for {symbol}[/green]"
    )
    return headlines


def finvader_fallback_scoring(headlines: list[dict]) -> dict:
    """
    Fallback: Score headlines using FinVADER when Gemini is unavailable.
    Returns a dict matching the expected sentiment output format.
    """
    scores = []
    anomalies = []

    for item in headlines:
        text = item["text"]
        score = score_headline(text)
        scores.append({"headline": text, "score": score})
        if score <= -0.8:
            anomalies.append(
                {
                    "headline": text,
                    "score": score,
                    "reason": "FinVADER detected strongly negative sentiment",
                }
            )

    if scores:
        avg_score = sum(s["score"] for s in scores) / len(scores)
    else:
        avg_score = 0.0

    # Determine signal
    if anomalies:
        signal = "HOLD"  # Cap at HOLD if anomalies exist
    elif avg_score > 0.2:
        signal = "BUY"
    elif avg_score < -0.2:
        signal = "SELL"
    else:
        signal = "HOLD"

    return {
        "scores": scores,
        "aggregate_score": round(avg_score, 4),
        "signal": signal,
        "confidence": 0.4,  # Low confidence for FinVADER (60% accuracy)
        "key_themes": ["FinVADER fallback — themes not available"],
        "anomalies": anomalies,
        "anomaly_count": len(anomalies),
        "narrative": f"Sentiment scored via FinVADER offline fallback (60% accuracy). "
        f"Average score: {avg_score:.2f} across {len(scores)} headlines.",
        "fallback_used": True,
    }


def _fetch_reddit_posts(symbol: str, limit: int = 20) -> list[str]:
    """
    Fetch top posts from r/IndianStreetBets mentioning the stock.
    Gracefully returns empty list if PRAW credentials are missing.
    """
    # Check for Reddit credentials
    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    user_agent = os.getenv("REDDIT_USER_AGENT", "ArthaVest/1.0")

    if not client_id or not client_secret:
        logger.info(
            "[dim]Sentiment: Reddit credentials not configured, skipping.[/dim]"
        )
        return []

    try:
        import praw

        reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
        )

        subreddit = reddit.subreddit("IndianStreetBets")
        posts = []

        # Search for the stock symbol in the subreddit
        for post in subreddit.search(
            symbol, sort="new", time_filter="month", limit=limit
        ):
            posts.append(post.title)

        return posts

    except ImportError:
        logger.warning("[yellow]praw not installed, skipping Reddit[/yellow]")
        return []
    except Exception as e:
        logger.warning(f"[yellow]Reddit fetch failed for {symbol}: {e}[/yellow]")
        return []
