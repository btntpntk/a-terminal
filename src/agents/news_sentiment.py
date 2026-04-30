"""
news_sentiment_agent — Gemini-powered news sentiment + impact scoring for Thai equities.

Data ingestion is delegated to news_pipeline.py.
All sentiment + impact classification is handled by a single batched Gemini call per chunk.

Impact tiers:
  Tier 1: Systemic Catalyst  — rate decisions, wars, major regulatory shifts
  Tier 2: Sector Shock       — supply chain issues, localized political unrest
  Tier 3: Routine/Noise      — standard earnings recaps, analyst opinions
"""
from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field
from typing_extensions import Literal

from src.agents.news_pipeline import (
    fetch_gnews_ticker,
    fetch_macro_articles,
    fetch_yfinance_articles,
)

# ── Pydantic schemas ──────────────────────────────────────────────────────────

ImpactTier = Literal[
    "Tier 1: Systemic Catalyst",
    "Tier 2: Sector Shock",
    "Tier 3: Routine/Noise",
]


class Sentiment(BaseModel):
    """Sentiment + impact classification for a single news article."""
    sentiment: Literal["positive", "negative", "neutral"]
    confidence: int = Field(ge=0, le=100, description="Confidence 0-100")
    impact_tier: ImpactTier = Field(
        default="Tier 3: Routine/Noise",
        description="Market impact magnitude of this article",
    )


class _ArticleSentiment(BaseModel):
    index: int = Field(description="0-based index matching the input list")
    sentiment: Literal["positive", "negative", "neutral"]
    confidence: int = Field(ge=0, le=100)
    impact_tier: ImpactTier = "Tier 3: Routine/Noise"


class _BatchSentimentResult(BaseModel):
    results: list[_ArticleSentiment]


# ── Gemini batch classifier ───────────────────────────────────────────────────

_TIER_DEFINITIONS = (
    "  • 'Tier 1: Systemic Catalyst' — central bank decisions, geopolitical conflicts, "
    "major regulatory overhauls, sovereign debt crises, pandemic-level events.\n"
    "  • 'Tier 2: Sector Shock' — supply chain disruptions, localised political unrest, "
    "industry-wide regulatory changes, major commodity price shocks affecting one sector.\n"
    "  • 'Tier 3: Routine/Noise' — standard earnings reports, analyst upgrades/downgrades, "
    "routine corporate announcements, minor macro data prints."
)


def _classify_with_gemini(ticker: str, articles: list[dict]) -> list[Sentiment]:
    """
    Classify a batch of articles in a single Gemini call.
    Returns one Sentiment per article in the same order as the input.
    Falls back to neutral / 0 / Tier 3 on any failure.
    """
    if not articles:
        return []

    fallback = [Sentiment(sentiment="neutral", confidence=0, impact_tier="Tier 3: Routine/Noise") for _ in articles]

    article_block = "\n".join(
        f"[{i}] TITLE: {a['title']}\n    SUMMARY: {a.get('summary') or '(no summary)'}"
        for i, a in enumerate(articles)
    )

    prompt = (
        f"You are a quantitative hedge fund manager specialising in Thai equities and macro risk.\n"
        f"Ticker under analysis: {ticker}\n\n"
        f"For each article below, produce three outputs:\n"
        f"  1. sentiment — effect on {ticker}'s stock price: 'positive', 'negative', or 'neutral'.\n"
        f"     For MACRO articles with no direct link to {ticker}, use 'neutral' unless systemic.\n"
        f"  2. confidence — your conviction 0–100.\n"
        f"  3. impact_tier — market impact magnitude using EXACTLY one of these labels:\n"
        f"{_TIER_DEFINITIONS}\n\n"
        f"Return one result per article, index 0 to {len(articles) - 1}.\n\n"
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
                impact_tier=index_map[i].impact_tier,
            ) if i in index_map else Sentiment(sentiment="neutral", confidence=0)
            for i in range(len(articles))
        ]
    except Exception:
        return fallback


# ── Signal aggregation ────────────────────────────────────────────────────────

def _aggregate_signal(sentiments: list[Sentiment]) -> tuple[str, float]:
    if not sentiments:
        return "neutral", 0.0

    counts:   dict[str, int] = {"bullish": 0, "bearish": 0, "neutral": 0}
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


def _count_tiers(sentiments: list[Sentiment]) -> dict[str, int]:
    return {
        "tier1": sum(1 for s in sentiments if s.impact_tier == "Tier 1: Systemic Catalyst"),
        "tier2": sum(1 for s in sentiments if s.impact_tier == "Tier 2: Sector Shock"),
        "tier3": sum(1 for s in sentiments if s.impact_tier == "Tier 3: Routine/Noise"),
    }


# ── Main agent ────────────────────────────────────────────────────────────────

def news_sentiment_agent(state: Any, agent_id: str = "news_sentiment_agent") -> dict:
    from src.graph.state import show_agent_reasoning
    from src.utils.progress import progress

    data: dict         = state.get("data", {})
    tickers: list[str] = data.get("tickers", [])

    sentiment_analysis: dict[str, Any] = {}

    progress.update_status(agent_id, None, "Fetching breaking & macro news")
    macro_seen: set[str] = set()
    macro_articles = fetch_macro_articles(macro_seen)

    for ticker in tickers:
        seen: set[str] = set(macro_seen)

        progress.update_status(agent_id, ticker, "Fetching yfinance news")
        yf_articles = fetch_yfinance_articles(ticker, seen)

        progress.update_status(agent_id, ticker, "Fetching Thai gnews")
        gn_articles = fetch_gnews_ticker(ticker, seen)

        all_articles = yf_articles + gn_articles + macro_articles
        sentiments: list[Sentiment] = []

        if all_articles:
            progress.update_status(agent_id, ticker, f"Classifying {len(all_articles)} articles via Gemini")
            for start in range(0, len(all_articles), 20):
                chunk = all_articles[start : start + 20]
                sentiments.extend(_classify_with_gemini(ticker, chunk))

        progress.update_status(agent_id, ticker, "Aggregating signals")
        overall_signal, confidence = _aggregate_signal(sentiments)

        sentiment_counts = {
            "bullish": sum(1 for s in sentiments if s.sentiment == "positive"),
            "bearish": sum(1 for s in sentiments if s.sentiment == "negative"),
            "neutral": sum(1 for s in sentiments if s.sentiment == "neutral"),
        }
        tier_counts = _count_tiers(sentiments)
        high_impact = tier_counts["tier1"] > 0

        reasoning = {
            "news_sentiment": {
                "signal": overall_signal,
                "confidence": confidence,
                "metrics": {
                    "total_articles":         len(sentiments),
                    "yfinance_articles":      len(yf_articles),
                    "gnews_ticker_articles":  len(gn_articles),
                    "macro_articles":         len(macro_articles),
                    "bullish_articles":       sentiment_counts["bullish"],
                    "bearish_articles":       sentiment_counts["bearish"],
                    "neutral_articles":       sentiment_counts["neutral"],
                    "impact_tiers":           tier_counts,
                },
            }
        }

        ticker_result: dict[str, Any] = {
            "signal":     overall_signal,
            "confidence": confidence,
            "reasoning":  reasoning,
        }
        if high_impact:
            ticker_result["high_impact_alert"] = True

        sentiment_analysis[ticker] = ticker_result
        progress.update_status(agent_id, ticker, "Done", analysis=json.dumps(reasoning, indent=4))

    message = HumanMessage(content=json.dumps(sentiment_analysis), name=agent_id)

    if state.get("metadata", {}).get("show_reasoning"):
        show_agent_reasoning(sentiment_analysis, "News Sentiment Analysis Agent")

    if "analyst_signals" not in state["data"]:
        state["data"]["analyst_signals"] = {}
    state["data"]["analyst_signals"][agent_id] = sentiment_analysis

    progress.update_status(agent_id, None, "Done")

    return {"messages": [message], "data": state["data"]}
