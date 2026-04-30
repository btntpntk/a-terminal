"""
news_pipeline — data ingestion layer for the news sentiment system.

Public API:
  fetch_yfinance_articles(ticker, seen)   → per-ticker yfinance (EN)
  fetch_gnews_ticker(ticker, seen)        → per-ticker GNews (TH)
  fetch_global_macro_articles(seen)       → SPY/VIX + GNews EN/US BUSINESS
  fetch_thai_macro_articles(seen)         → ^SET.BK + GNews TH/TH BUSINESS + Thai query bank
  fetch_macro_articles(seen)             → global + thai combined (for per-ticker endpoint)

All articles share the shape:
  {
    "title": str,
    "summary": str,
    "lang": str,              # "en" | "th"
    "ticker_source": str,     # ticker symbol or "MACRO"
    "source": str,            # publisher display name, e.g. "Reuters"
    "published_at": int|None, # Unix epoch seconds (UTC)
  }
"""
from __future__ import annotations

import re
import time
from email.utils import parsedate_to_datetime

import yfinance as yf

try:
    from gnews import GNews
    _GNEWS_OK = True
except ImportError:
    _GNEWS_OK = False

# ── Constants ─────────────────────────────────────────────────────────────────

_GLOBAL_PROXY_TICKERS: list[str] = ["SPY", "^VIX"]
_THAI_PROXY_TICKERS:   list[str] = ["^SET.BK"]

THAI_MACRO_QUERIES: list[tuple[str, str]] = [
    ("th", "ตลาดหุ้น SET index"),
    ("th", "กนง อัตราดอกเบี้ย นโยบาย"),
    ("th", "เศรษฐกิจไทย GDP"),
    ("th", "ราคาน้ำมัน ไทย"),
    ("th", "ค่าเงินบาท ดอลลาร์"),
    ("th", "นักท่องเที่ยว ไทย"),
    ("th", "หุ้นไทย วันนี้"),
    ("en", "SET index Thailand stock market"),
    ("en", "Thailand economy baht interest rate"),
    ("en", "Thailand stocks today"),
]


# ── Internal helpers ──────────────────────────────────────────────────────────

def _normalize_title(title: str) -> str:
    return re.sub(r"\W+", "", title.lower())


def _parse_iso(s: str) -> int | None:
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return int(dt.timestamp())
    except Exception:
        return None


def _parse_rfc2822(s: str) -> int | None:
    try:
        dt = parsedate_to_datetime(s)
        return int(dt.timestamp())
    except Exception:
        return None


def _parse_yf_item(raw: dict) -> dict | None:
    content = raw.get("content") or raw
    title   = content.get("title", "")
    summary = content.get("summary") or content.get("description", "")

    provider = content.get("provider") or {}
    source: str = provider.get("displayName") or content.get("publisher") or ""

    published_at: int | None = None
    pub_date = content.get("pubDate") or content.get("displayDate")
    if pub_date:
        published_at = _parse_iso(str(pub_date))
    if published_at is None:
        pt = content.get("providerPublishTime")
        if isinstance(pt, (int, float)):
            published_at = int(pt)

    url = ""
    for key in ("canonicalUrl", "clickThroughUrl"):
        obj = content.get(key)
        if isinstance(obj, dict):
            url = obj.get("url", "")
        if url:
            break
    if not url:
        url = content.get("link") or content.get("url", "")
    if not url or not title:
        return None
    return {"title": title, "summary": summary, "source": source, "published_at": published_at}


def _gnews_source(item: dict) -> str:
    pub = item.get("publisher") or {}
    if isinstance(pub, dict):
        return pub.get("title") or pub.get("href", "")
    return str(pub)


def _gnews_published_at(item: dict) -> int | None:
    raw = item.get("published date") or item.get("publishedAt") or ""
    if raw:
        return _parse_rfc2822(str(raw)) or _parse_iso(str(raw))
    return None


def _add_article(
    articles: list[dict],
    seen: set[str],
    title: str,
    summary: str,
    lang: str,
    ticker_source: str,
    source: str = "",
    published_at: int | None = None,
) -> None:
    key = _normalize_title(title)
    if not key or key in seen:
        return
    seen.add(key)
    articles.append({
        "title":         title,
        "summary":       summary,
        "lang":          lang,
        "ticker_source": ticker_source,
        "source":        source,
        "published_at":  published_at,
    })


def _fetch_yf_proxy(tickers: list[str], seen: set[str]) -> list[dict]:
    articles: list[dict] = []
    for proxy in tickers:
        try:
            raw_news = yf.Ticker(proxy).news or []
        except Exception:
            continue
        for raw in raw_news:
            parsed = _parse_yf_item(raw)
            if not parsed:
                continue
            _add_article(
                articles, seen,
                parsed["title"], parsed["summary"],
                "en", "MACRO",
                parsed["source"], parsed["published_at"],
            )
    return articles


# ── Public fetchers ───────────────────────────────────────────────────────────

def fetch_yfinance_articles(ticker: str, seen: set[str]) -> list[dict]:
    """Pull yfinance news for a single ticker."""
    articles: list[dict] = []
    try:
        raw_news = yf.Ticker(ticker).news or []
    except Exception:
        return articles
    for raw in raw_news:
        parsed = _parse_yf_item(raw)
        if not parsed:
            continue
        _add_article(
            articles, seen,
            parsed["title"], parsed["summary"],
            "en", ticker,
            parsed["source"], parsed["published_at"],
        )
    return articles


def fetch_gnews_ticker(ticker: str, seen: set[str]) -> list[dict]:
    """Pull Thai-language GNews articles for a single ticker."""
    if not _GNEWS_OK:
        return []
    articles: list[dict] = []
    base = ticker.replace(".BK", "").replace(".TH", "")
    try:
        items = GNews(language="th", country="TH", max_results=5).get_news(base) or []
    except Exception:
        return articles
    for item in items:
        _add_article(
            articles, seen,
            item.get("title", ""), item.get("description", ""),
            "th", ticker,
            _gnews_source(item), _gnews_published_at(item),
        )
        time.sleep(0.1)
    return articles


def fetch_global_macro_articles(seen: set[str]) -> list[dict]:
    """
    Global macro articles:
      1. yfinance SPY + ^VIX proxy news
      2. GNews EN/US BUSINESS topic feed
    """
    articles: list[dict] = []
    articles.extend(_fetch_yf_proxy(_GLOBAL_PROXY_TICKERS, seen))

    if not _GNEWS_OK:
        return articles

    try:
        items = GNews(language="en", country="US", max_results=15).get_news_by_topic("BUSINESS") or []
    except Exception:
        items = []
    for item in items:
        _add_article(
            articles, seen,
            item.get("title", ""), item.get("description", ""),
            "en", "MACRO",
            _gnews_source(item), _gnews_published_at(item),
        )

    return articles


def fetch_thai_macro_articles(seen: set[str]) -> list[dict]:
    """
    Thailand macro articles via GNews targeted financial queries:
      1. yfinance ^SET.BK proxy news
      2. Thai-language financial queries (stocks, SET, BOT rate, baht, economy)
      3. English-language Thailand finance queries
    """
    articles: list[dict] = []
    articles.extend(_fetch_yf_proxy(_THAI_PROXY_TICKERS, seen))

    if not _GNEWS_OK:
        return articles

    queries: list[tuple[str, str]] = [
        ("th", "หุ้นไทย"),
        ("th", "ตลาดหุ้น SET"),
        ("th", "กนง ดอกเบี้ย"),
        ("th", "เศรษฐกิจไทย"),
        ("th", "ค่าเงินบาท"),
        ("th", "หุ้น วันนี้"),
        ("en", "Thailand stock market"),
        ("en", "SET index Thailand"),
        ("en", "Thai baht exchange rate"),
    ]

    gn_cache: dict[str, GNews] = {}
    for lang, query in queries:
        if lang not in gn_cache:
            gn_cache[lang] = GNews(language=lang, country="TH", max_results=5)
        try:
            items = gn_cache[lang].get_news(query) or []
        except Exception:
            items = []
        for item in items:
            _add_article(
                articles, seen,
                item.get("title", ""), item.get("description", ""),
                lang, "MACRO",
                _gnews_source(item), _gnews_published_at(item),
            )
        time.sleep(0.2)

    return articles


def fetch_macro_articles(seen: set[str]) -> list[dict]:
    """Combined global + Thai macro articles (used by per-ticker analysis endpoint)."""
    articles = fetch_global_macro_articles(seen)
    articles.extend(fetch_thai_macro_articles(seen))
    return articles
