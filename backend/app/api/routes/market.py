"""
Market Dashboard Route
GET /market/dashboard — indices, top movers, multi-category news
Cached: indices 60s, news 300s
"""

import time
import threading

try:
    import feedparser

    _FEEDPARSER_AVAILABLE = True
except ImportError:
    feedparser = None
    _FEEDPARSER_AVAILABLE = False

try:
    import yfinance as yf

    _YFINANCE_AVAILABLE = True
except ImportError:
    yf = None
    _YFINANCE_AVAILABLE = False

from urllib.parse import quote
from fastapi import APIRouter
from app.core.config import logger

router = APIRouter(prefix="/market", tags=["market"])

# ── In-memory cache ─────────────────────────────────────────────────────────
_cache: dict = {}
_cache_lock = threading.Lock()

INDICES_TTL = 60  # seconds
NEWS_TTL = 300  # seconds

# ── Indices to fetch ─────────────────────────────────────────────────────────
INDICES = {
    "NIFTY 50": "^NSEI",
    "SENSEX": "^BSESN",
    "BANK NIFTY": "^NSEBANK",
    "INDIA VIX": "^INDIAVIX",
    "S&P 500": "^GSPC",
    "NASDAQ": "^IXIC",
    "DOW JONES": "^DJI",
    "FTSE 100": "^FTSE",
    "NIKKEI 225": "^N225",
    "HANG SENG": "^HSI",
    "GOLD": "GC=F",
    "CRUDE OIL": "CL=F",
}

# ── News RSS feeds ────────────────────────────────────────────────────────────
NEWS_FEEDS = [
    {
        "label": "India Markets",
        "url": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    },
    {
        "label": "Global Markets",
        "url": "https://finance.yahoo.com/rss/headline?s=^GSPC,^IXIC",
    },
    {
        "label": "Economy",
        "url": "https://economictimes.indiatimes.com/news/economy/rssfeeds/1373380680.cms",
    },
    {
        "label": "Sectors",
        "url": "https://economictimes.indiatimes.com/industry/rssfeeds/13352306.cms",
    },
    {
        "label": "Earnings",
        "url": "https://economictimes.indiatimes.com/markets/stocks/earnings/rssfeeds/8371304.cms",
    },
]


def _fetch_indices() -> list[dict]:
    results = []
    if yf is None:
        logger.warning(
            "[yellow]yfinance is not installed; skipping indices fetch[/yellow]"
        )
        for name, sym in INDICES.items():
            results.append(
                {
                    "name": name,
                    "symbol": sym,
                    "price": None,
                    "change": None,
                    "change_pct": None,
                    "error": "yfinance not installed",
                }
            )
        return results
    try:
        import concurrent.futures

        def fetch_single(name, sym):
            try:
                t = yf.Ticker(sym)
                last_close = None
                prev_close = None
                try:
                    last_close = t.fast_info.last_price
                    prev_close = t.fast_info.previous_close
                except Exception:
                    pass

                if last_close is None or prev_close is None:
                    info = t.info
                    last_close = info.get("regularMarketPrice", last_close)
                    prev_close = info.get("previousClose", prev_close)

                if last_close is None or prev_close is None:
                    return {
                        "name": name,
                        "symbol": sym,
                        "price": None,
                        "change": None,
                        "change_pct": None,
                        "error": "no data",
                    }

                change = round(last_close - prev_close, 2)
                change_pct = (
                    round((change / prev_close) * 100, 2) if prev_close else 0.0
                )
                return {
                    "name": name,
                    "symbol": sym,
                    "price": round(last_close, 2),
                    "change": change,
                    "change_pct": change_pct,
                }
            except Exception as e:
                return {
                    "name": name,
                    "symbol": sym,
                    "price": None,
                    "change": None,
                    "change_pct": None,
                    "error": str(e),
                }

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(20, len(INDICES))
        ) as executor:
            future_to_name = {
                executor.submit(fetch_single, name, sym): name
                for name, sym in INDICES.items()
            }
            fetched_results = []
            for future in concurrent.futures.as_completed(future_to_name):
                fetched_results.append(future.result())

        # Maintain original order
        name_to_result = {r["name"]: r for r in fetched_results}
        for name in INDICES.keys():
            if name in name_to_result:
                results.append(name_to_result[name])
    except Exception as e:
        logger.error(f"[red]Market route: yfinance fetch failed — {e}[/red]")
        for name, sym in INDICES.items():
            results.append(
                {
                    "name": name,
                    "symbol": sym,
                    "price": None,
                    "change": None,
                    "change_pct": None,
                    "error": str(e),
                }
            )
    return results


def _fetch_news(limit_per_feed: int = 8) -> list[dict]:
    news = []
    if feedparser is None:
        logger.warning(
            "[yellow]feedparser is not installed; skipping dashboard news fetch[/yellow]"
        )
        return news

    import time
    import requests

    seen: set[str] = set()

    _HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    _COOKIES = {"CONSENT": "YES+cb.20210418-17-p0.en+FX+414"}

    for feed_cfg in NEWS_FEEDS:
        try:
            url = feed_cfg["url"]

            resp = requests.get(url, timeout=15, headers=_HEADERS, cookies=_COOKIES)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)

            count = 0
            for entry in feed.entries:
                title = (entry.get("title") or "").strip()
                if not title or title.lower() in seen:
                    continue
                seen.add(title.lower())
                link = entry.get("link", "")
                source = (
                    entry.get("source", {}).get("title", "")
                    if isinstance(entry.get("source"), dict)
                    else ""
                )
                pub_raw = entry.get("published", "")

                pub_ts = 0.0
                pp = entry.get("published_parsed")
                if pp:
                    try:
                        import calendar

                        pub_ts = calendar.timegm(pp)
                    except Exception:
                        pub_ts = 0.0

                news.append(
                    {
                        "category": feed_cfg["label"],
                        "title": title,
                        "source": source,
                        "link": link,
                        "published": pub_raw,
                        "_pub_ts": pub_ts,
                    }
                )
                count += 1
                if count >= limit_per_feed:
                    break
        except Exception as e:
            logger.warning(
                f"[yellow]Market news RSS failed for '{feed_cfg['label']}': {e}[/yellow]"
            )

    news.sort(key=lambda n: n.get("_pub_ts") or 0.0, reverse=True)
    return news


def _get_cached(key: str, ttl: int, fetcher):
    with _cache_lock:
        entry = _cache.get(key)
        if entry and (time.time() - entry["ts"]) < ttl:
            return entry["data"], False
    data = fetcher()
    with _cache_lock:
        _cache[key] = {"data": data, "ts": time.time()}
    return data, True


def _public_news(news: list[dict]) -> list[dict]:
    """Strip internal-only keys (e.g. the _pub_ts sort helper) from news items
    before they cross the API boundary."""
    return [{k: v for k, v in n.items() if not k.startswith("_")} for n in news]


@router.get("/dashboard")
def get_dashboard():
    """Returns indices + multi-category news for the Dashboard page."""
    indices, _ = _get_cached("indices", INDICES_TTL, _fetch_indices)
    news, _ = _get_cached("news", NEWS_TTL, _fetch_news)
    return {
        "indices": indices,
        "news": _public_news(news),
        "fetched_at": time.time(),
    }


@router.get("/news")
def get_news(category: str = None, search: str = None, page: int = 1, limit: int = 10):
    """Returns paginated news list, optionally filtered by category label and search query."""
    news, _ = _get_cached("news", NEWS_TTL, _fetch_news)
    if category:
        news = [n for n in news if n.get("category", "").lower() == category.lower()]
    if search and search.strip():
        q = search.strip().lower()
        news = [
            n
            for n in news
            if q in (n.get("title") or "").lower()
            or q in (n.get("source") or "").lower()
        ]
    total = len(news)
    if page < 1:
        page = 1
    if limit < 1:
        limit = 10
    total_pages = max(1, -(-total // limit))  # ceil division
    offset = (page - 1) * limit
    items = news[offset : offset + limit]
    return {
        "count": total,
        "page": page,
        "total_pages": total_pages,
        "items": _public_news(items),
    }


@router.get("/indices")
def get_indices():
    """Returns current index quotes."""
    indices, _ = _get_cached("indices", INDICES_TTL, _fetch_indices)
    return indices
