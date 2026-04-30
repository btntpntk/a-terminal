"""
gemini_analyst_agent — Gemini-powered fundamental analyst for Thai equities.

Mirrors the structure of warren_buffett_agent but uses a quantitative analyst
persona tailored to the SET market. All analysis helper functions are reused
directly from warren_buffett.py to avoid duplication.

Reasoning output is in Thai language; JSON keys and signal values stay in English.
"""
from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field
from typing_extensions import Literal

from src.graph.state import AgentState, show_agent_reasoning
from src.tools.api import get_financial_metrics, get_market_cap, search_line_items
from src.utils.progress import progress
from src.agents.ai_analyst.warren_buffett import (
    analyze_book_value_growth,
    analyze_consistency,
    analyze_fundamentals,
    analyze_management_quality,
    analyze_moat,
    analyze_pricing_power,
    calculate_intrinsic_value,
)


# ── Output schema ─────────────────────────────────────────────────────────────

class GeminiAnalystSignal(BaseModel):
    signal: Literal["bullish", "bearish", "neutral"]
    confidence: int = Field(ge=0, le=100, description="Confidence 0-100")
    reasoning: str = Field(description="Investment thesis in Thai language, max 150 characters")


# ── Prompt ────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = (
    "คุณเป็นนักวิเคราะห์การเงินเชิงปริมาณ (Quant Analyst) ผู้เชี่ยวชาญตลาดหุ้นไทย (SET)\n"
    "หน้าที่ของคุณคือประเมินคุณภาพธุรกิจและมูลค่าที่เหมาะสมของหุ้น โดยใช้เฉพาะข้อมูลที่ให้มา\n\n"
    "เกณฑ์การตัดสิน:\n"
    "- bullish  : ปัจจัยพื้นฐานแข็งแกร่ง AND margin_of_safety > 0 (ราคาต่ำกว่ามูลค่า)\n"
    "- bearish  : ปัจจัยพื้นฐานอ่อนแอ OR ราคาแพงกว่ามูลค่าอย่างชัดเจน\n"
    "- neutral  : ปัจจัยพื้นฐานดี แต่ราคาสะท้อนมูลค่าแล้ว หรือสัญญาณขัดแย้ง\n\n"
    "ระดับความมั่นใจ (confidence):\n"
    "- 80-100 : หลักฐานแข็งแกร่ง ทิศทางชัดเจน\n"
    "- 60-79  : แนวโน้มชัดแต่มีความไม่แน่นอน\n"
    "- 40-59  : สัญญาณผสมหรือข้อมูลไม่ครบ\n"
    "- 20-39  : หลักฐานขัดแย้งกัน\n\n"
    "ข้อบังคับ:\n"
    "- reasoning ต้องเป็นภาษาไทยเท่านั้น ไม่เกิน 150 ตัวอักษร\n"
    "- signal และ JSON keys ต้องเป็นภาษาอังกฤษ\n"
    "- ห้ามประดิษฐ์ข้อมูล — ใช้เฉพาะ facts ที่ให้มา"
)

_HUMAN_TEMPLATE = (
    "Ticker: {ticker}\n"
    "Facts:\n{facts}\n\n"
    "Return exactly:\n"
    "{{\n"
    '  "signal": "bullish" | "bearish" | "neutral",\n'
    '  "confidence": int,\n'
    '  "reasoning": "Thai language thesis (max 150 chars)"\n'
    "}}"
)


# ── Signal generator ──────────────────────────────────────────────────────────

def _generate_gemini_signal(ticker: str, analysis_data: dict[str, Any]) -> GeminiAnalystSignal:
    facts = {
        "score":             analysis_data.get("score"),
        "max_score":         analysis_data.get("max_score"),
        "fundamentals":      analysis_data.get("fundamental_analysis",    {}).get("details"),
        "consistency":       analysis_data.get("consistency_analysis",    {}).get("details"),
        "moat":              analysis_data.get("moat_analysis",           {}).get("details"),
        "pricing_power":     analysis_data.get("pricing_power_analysis",  {}).get("details"),
        "book_value":        analysis_data.get("book_value_analysis",     {}).get("details"),
        "management":        analysis_data.get("management_analysis",     {}).get("details"),
        "intrinsic_value":   analysis_data.get("intrinsic_value_analysis", {}).get("intrinsic_value"),
        "market_cap":        analysis_data.get("market_cap"),
        "margin_of_safety":  analysis_data.get("margin_of_safety"),
    }

    template = ChatPromptTemplate.from_messages([
        ("system", _SYSTEM_PROMPT),
        ("human",  _HUMAN_TEMPLATE),
    ])

    prompt = template.invoke({
        "ticker": ticker,
        "facts":  json.dumps(facts, separators=(",", ":"), ensure_ascii=False),
    })

    try:
        llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0.1)
        return llm.with_structured_output(GeminiAnalystSignal).invoke(prompt)
    except Exception:
        return GeminiAnalystSignal(
            signal="neutral",
            confidence=50,
            reasoning="ไม่สามารถวิเคราะห์ได้เนื่องจากข้อมูลไม่เพียงพอ",
        )


# ── Main agent ────────────────────────────────────────────────────────────────

_LINE_ITEMS = [
    "capital_expenditure",
    "depreciation_and_amortization",
    "net_income",
    "outstanding_shares",
    "total_assets",
    "total_liabilities",
    "shareholders_equity",
    "dividends_and_other_cash_distributions",
    "issuance_or_purchase_of_equity_shares",
    "gross_profit",
    "revenue",
    "free_cash_flow",
]


def gemini_analyst_agent(state: AgentState, agent_id: str = "gemini_analyst_agent") -> dict:
    data: dict         = state.get("data", {})
    tickers: list[str] = data.get("tickers", [])
    end_date           = data.get("end_date")

    gemini_analysis: dict[str, Any] = {}

    for ticker in tickers:
        progress.update_status(agent_id, ticker, "Fetching financial metrics")
        metrics = get_financial_metrics(ticker, end_date, period="ttm", limit=10)

        progress.update_status(agent_id, ticker, "Gathering financial line items")
        financial_line_items = search_line_items(ticker, _LINE_ITEMS, end_date, period="ttm", limit=10)

        progress.update_status(agent_id, ticker, "Getting market cap")
        market_cap = get_market_cap(ticker, end_date)

        progress.update_status(agent_id, ticker, "Running analysis modules")
        fundamental_analysis     = analyze_fundamentals(metrics)
        consistency_analysis     = analyze_consistency(financial_line_items)
        moat_analysis            = analyze_moat(metrics)
        pricing_power_analysis   = analyze_pricing_power(financial_line_items, metrics)
        book_value_analysis      = analyze_book_value_growth(financial_line_items)
        mgmt_analysis            = analyze_management_quality(financial_line_items)
        intrinsic_value_analysis = calculate_intrinsic_value(financial_line_items)

        total_score = (
            fundamental_analysis["score"]
            + consistency_analysis["score"]
            + moat_analysis["score"]
            + mgmt_analysis["score"]
            + pricing_power_analysis["score"]
            + book_value_analysis["score"]
        )
        max_possible_score = (
            10                          # fundamentals
            + moat_analysis["max_score"]
            + mgmt_analysis["max_score"]
            + 5                         # pricing_power
            + 5                         # book_value_growth
        )

        intrinsic_value  = intrinsic_value_analysis.get("intrinsic_value")
        margin_of_safety = None
        if intrinsic_value and market_cap:
            margin_of_safety = (intrinsic_value - market_cap) / market_cap

        analysis_data: dict[str, Any] = {
            "ticker":                   ticker,
            "score":                    total_score,
            "max_score":                max_possible_score,
            "fundamental_analysis":     fundamental_analysis,
            "consistency_analysis":     consistency_analysis,
            "moat_analysis":            moat_analysis,
            "pricing_power_analysis":   pricing_power_analysis,
            "book_value_analysis":      book_value_analysis,
            "management_analysis":      mgmt_analysis,
            "intrinsic_value_analysis": intrinsic_value_analysis,
            "market_cap":               market_cap,
            "margin_of_safety":         margin_of_safety,
        }

        progress.update_status(agent_id, ticker, "Generating Gemini analysis")
        output = _generate_gemini_signal(ticker, analysis_data)

        gemini_analysis[ticker] = {
            "signal":     output.signal,
            "confidence": output.confidence,
            "reasoning":  output.reasoning,
        }

        progress.update_status(agent_id, ticker, "Done", analysis=output.reasoning)

    message = HumanMessage(content=json.dumps(gemini_analysis), name=agent_id)

    if state.get("metadata", {}).get("show_reasoning"):
        show_agent_reasoning(gemini_analysis, agent_id)

    if "analyst_signals" not in state["data"]:
        state["data"]["analyst_signals"] = {}
    state["data"]["analyst_signals"][agent_id] = gemini_analysis

    progress.update_status(agent_id, None, "Done")

    return {"messages": [message], "data": state["data"]}
