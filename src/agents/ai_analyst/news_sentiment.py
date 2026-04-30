"""
news_sentiment_agent — Gemini-powered news sentiment for Thai equities.

Data sources:
  1. yfinance  — English ticker news
  2. gnews     — Thai per-ticker news + Thai/EN macro queries

All sentiment classification is delegated to Gemini (gemini-2.0-flash) via
a single batched call per ticker, replacing the old rule-based keyword approach
and the per-article LLM call pattern.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

import yfinance as yf
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field
from typing_extensions import Literal

try:
    from gnews import GNews
    _GNEWS_OK = True
except ImportError:
    _GNEWS_OK = False

from src.graph.state import AgentState, show_agent_reasoning
from src.utils.progress import progress


# ── Thai macro queries (preserved from news_pipeline.py) ─────────────────────

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


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class Sentiment(BaseModel):
    """Sentiment classification for a single news article."""
    sentiment: Literal["positive", "negative", "neutral"]
    confidence: int = Field(ge=0, le=100, description="Confidence 0-100")


class _ArticleSentiment(BaseModel):
    index: int = Field(description="0-based index matching the input list")
    sentiment: Literal["positive", "negative", "neutral"]
    confidence: int = Field(ge=0, le=100)


class _BatchSentimentResult(BaseModel):
    results: list[_ArticleSentiment]


# ── yfinance helpers (ported from news_pipeline.py) ───────────────────────────

def _normalize_title(title: str) -> str:
    return re.sub(r"\W+", "", title.lower())


def _parse_yf_item(raw: dict) -> dict | None:
    content = raw.get("content") or raw
    title   = content.get("title", "")
    summary = content.get("summary") or content.get("description", "")

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
    return {"title": title, "summary": summary}


# ── News fetching ─────────────────────────────────────────────────────────────

def _fetch_yfinance_articles(ticker: str, seen: set[str]) -> list[dict]:
    articles: list[dict] = []
    try:
        raw_news = yf.Ticker(ticker).news or []
    except Exception:
        return articles
    for raw in raw_news:
        parsed = _parse_yf_item(raw)
        if not parsed:
            continue
        key = _normalize_title(parsed["title"])
        if not key or key in seen:
            continue
        seen.add(key)
        articles.append({"title": parsed["title"], "summary": parsed["summary"], "lang": "en"})
    return articles


def _fetch_gnews_ticker(ticker: str, seen: set[str]) -> list[dict]:
    if not _GNEWS_OK:
        return []
    articles: list[dict] = []
    base = ticker.replace(".BK", "").replace(".TH", "")
    try:
        items = GNews(language="th", country="TH", max_results=5).get_news(base) or []
    except Exception:
        return articles
    for item in items:
        key = _normalize_title(item.get("title", ""))
        if not key or key in seen:
            continue
        seen.add(key)
        articles.append({
            "title": item.get("title", ""),
            "summary": item.get("description", ""),
            "lang": "th",
        })
        time.sleep(0.1)
    return articles


def _fetch_macro_articles(seen: set[str]) -> list[dict]:
    if not _GNEWS_OK:
        return []
    articles: list[dict] = []
    gn_cache: dict[str, GNews] = {}
    for lang, query in THAI_MACRO_QUERIES:
        if lang not in gn_cache:
            gn_cache[lang] = GNews(language=lang, country="TH", max_results=5)
        try:
            items = gn_cache[lang].get_news(query) or []
        except Exception:
            items = []
        for item in items:
            key = _normalize_title(item.get("title", ""))
            if not key or key in seen:
                continue
            seen.add(key)
            articles.append({
                "title": item.get("title", ""),
                "summary": item.get("description", ""),
                "lang": lang,
            })
        time.sleep(0.3)
    return articles


# ── Gemini batch classifier ───────────────────────────────────────────────────

def _classify_with_gemini(ticker: str, articles: list[dict]) -> list[Sentiment]:
    """
    Classify a batch of articles in a single Gemini call.
    Returns one Sentiment per article in the same order as the input.
    Falls back to neutral/0 on any failure.
    """
    if not articles:
        return []

    fallback = [Sentiment(sentiment="neutral", confidence=0) for _ in articles]

    article_block = "\n".join(
        f"[{i}] TITLE: {a['title']}\n    SUMMARY: {a['summary'] or '(no summary)'}"
        for i, a in enumerate(articles)
    )

    prompt = (
        f"You are a financial news sentiment analyst specialising in Thai equities.\n"
        f"Ticker: {ticker}\n\n"
        f"For each article below, classify the sentiment specifically for {ticker}.\n"
        f"Return one result per article, index 0 to {len(articles) - 1}.\n"
        f"'positive' = good for the stock price, 'negative' = bad, 'neutral' = irrelevant or unclear.\n"
        f"confidence is 0-100.\n\n"
        f"Articles:\n{article_block}"
    )

    try:
        llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0)
        result: _BatchSentimentResult = llm.with_structured_output(_BatchSentimentResult).invoke(prompt)
        index_map = {r.index: r for r in result.results}
        return [
            Sentiment(
                sentiment=index_map[i].sentiment,
                confidence=index_map[i].confidence,
            ) if i in index_map else Sentiment(sentiment="neutral", confidence=0)
            for i in range(len(articles))
        ]
    except Exception:
        return fallback


# ── Signal aggregation ────────────────────────────────────────────────────────

def _aggregate_signal(sentiments: list[Sentiment]) -> tuple[str, float]:
    if not sentiments:
        return "neutral", 0.0

    counts: dict[str, int]  = {"bullish": 0, "bearish": 0, "neutral": 0}
    conf_sum: dict[str, int] = {"bullish": 0, "bearish": 0, "neutral": 0}

    for s in sentiments:
        mapped = "bullish" if s.sentiment == "positive" else "bearish" if s.sentiment == "negative" else "neutral"
        counts[mapped]   += 1
        conf_sum[mapped] += s.confidence

    dominant = max(counts, key=lambda k: (counts[k], conf_sum[k]))
    total    = len(sentiments)

    proportion_score = (counts[dominant] / total) * 100
    avg_conf         = conf_sum[dominant] / max(counts[dominant], 1)
    # 60% weight on signal dominance, 40% on Gemini average confidence
    confidence = round(0.6 * proportion_score + 0.4 * avg_conf, 2)

    return dominant, confidence


# ── Main agent ────────────────────────────────────────────────────────────────

def news_sentiment_agent(state: AgentState, agent_id: str = "news_sentiment_agent") -> dict:
    data: dict         = state.get("data", {})
    tickers: list[str] = data.get("tickers", [])

    sentiment_analysis: dict[str, Any] = {}

    # Macro articles fetched once and reused for every ticker
    progress.update_status(agent_id, None, "Fetching Thai macro news")
    macro_seen: set[str] = set()
    macro_articles = _fetch_macro_articles(macro_seen)

    for ticker in tickers:
        # per-ticker dedup set inherits the macro title keys
        seen: set[str] = set(macro_seen)

        progress.update_status(agent_id, ticker, "Fetching yfinance news")
        yf_articles = _fetch_yfinance_articles(ticker, seen)

        progress.update_status(agent_id, ticker, "Fetching Thai gnews")
        gn_articles = _fetch_gnews_ticker(ticker, seen)

        all_articles              = yf_articles + gn_articles + macro_articles
        sentiments: list[Sentiment] = []

        if all_articles:
            progress.update_status(agent_id, ticker, f"Classifying {len(all_articles)} articles via Gemini")
            for start in range(0, len(all_articles), 20):
                chunk = all_articles[start : start + 20]
                sentiments.extend(_classify_with_gemini(ticker, chunk))

        progress.update_status(agent_id, ticker, "Aggregating signals")
        overall_signal, confidence = _aggregate_signal(sentiments)

        counts = {
            "bullish": sum(1 for s in sentiments if s.sentiment == "positive"),
            "bearish": sum(1 for s in sentiments if s.sentiment == "negative"),
            "neutral": sum(1 for s in sentiments if s.sentiment == "neutral"),
        }

        reasoning = {
            "news_sentiment": {
                "signal": overall_signal,
                "confidence": confidence,
                "metrics": {
                    "total_articles":         len(sentiments),
                    "yfinance_articles":      len(yf_articles),
                    "gnews_ticker_articles":  len(gn_articles),
                    "macro_articles":         len(macro_articles),
                    "bullish_articles":       counts["bullish"],
                    "bearish_articles":       counts["bearish"],
                    "neutral_articles":       counts["neutral"],
                },
            }
        }

        sentiment_analysis[ticker] = {
            "signal":     overall_signal,
            "confidence": confidence,
            "reasoning":  reasoning,
        }

        progress.update_status(agent_id, ticker, "Done", analysis=json.dumps(reasoning, indent=4))

    message = HumanMessage(content=json.dumps(sentiment_analysis), name=agent_id)

    if state.get("metadata", {}).get("show_reasoning"):
        show_agent_reasoning(sentiment_analysis, "News Sentiment Analysis Agent")

    if "analyst_signals" not in state["data"]:
        state["data"]["analyst_signals"] = {}
    state["data"]["analyst_signals"][agent_id] = sentiment_analysis

    progress.update_status(agent_id, None, "Done")

    return {"messages": [message], "data": state["data"]}
