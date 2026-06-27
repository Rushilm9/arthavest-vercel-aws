"""
News Service — Wraps feedparser to fetch Google News RSS headlines.
"""

try:
    import feedparser

    _FEEDPARSER_AVAILABLE = True
except ImportError:
    feedparser = None
    _FEEDPARSER_AVAILABLE = False
import requests
from app.core.config import logger
from urllib.parse import quote

_NEWS_TIMEOUT = (
    15  # seconds per fetch; increased from 5s to prevent timeouts on Cloud Run
)
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
_COOKIES = {"CONSENT": "YES+cb.20210418-17-p0.en+FX+414"}


def _fetch_feed(url: str):
    """Fetch RSS via requests (with timeout) then parse content — feedparser.parse(url) has no timeout."""
    if feedparser is None:
        logger.warning(
            "[yellow]feedparser is not installed; skipping RSS feed fetch[/yellow]"
        )

        class StubFeed:
            def __init__(self):
                self.entries = []

        return StubFeed()
    resp = requests.get(url, timeout=_NEWS_TIMEOUT, headers=_HEADERS, cookies=_COOKIES)
    resp.raise_for_status()

    feed = feedparser.parse(resp.content)
    if not feed.entries:
        logger.warning(
            f"[yellow]Google News returned 0 entries for URL: {url}. It may be rate-limiting Cloud Run IPs or requesting CAPTCHA.[/yellow]"
        )
    return feed


def get_stock_news(symbol: str) -> list[str]:
    """
    Fetches the latest news headlines for a specific stock using Google News RSS.
    Retrieves up to 50 headlines.
    """
    try:
        # Yahoo Finance RSS for stock tickers
        # Add .NS for Indian stocks if symbol doesn't have it
        symbol_query = symbol if "." in symbol else f"{symbol}.NS"
        url = f"https://finance.yahoo.com/rss/headline?s={symbol_query}"
        feed = _fetch_feed(url)
        # Format with date: "[09 Jun 2026] Headline text"
        from email.utils import parsedate_to_datetime

        headlines = []
        for entry in feed.entries[:50]:
            try:
                dt = parsedate_to_datetime(entry.published)
                date_str = dt.strftime("%d %b %Y")
                headlines.append(f"[{date_str}] {entry.title}")
            except Exception:
                headlines.append(entry.title)

        return headlines
    except Exception as e:
        logger.error(f"[red]Failed to fetch news for {symbol}: {e}[/red]")
        return []


def get_macro_headlines() -> list[str]:
    """
    Fetches general Indian economy and market news.
    """
    try:
        url = (
            "https://economictimes.indiatimes.com/news/economy/rssfeeds/1373380680.cms"
        )
        feed = _fetch_feed(url)
        return [entry.title for entry in feed.entries[:50]]
    except Exception as e:
        logger.error(f"[red]Failed to fetch macro news: {e}[/red]")
        return []
