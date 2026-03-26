"""
src/graph/state.py
Shared State Schema for the Alpha-Stream Agent Graph

Every field here is visible to every node in the LangGraph pipeline.
Fields annotated with operator.add are append-only lists — each agent
adds its own entries without overwriting what previous agents wrote.

Pipeline context injected by cli.py before ainvoke():
  ticker          — the stock symbol
  data            — raw market data dict from fetch_all_data()
  analysis_steps  — running log of agent reasoning (append-only)
  metadata        — pre-computed quant scores from Stages 0-5

Agents write to:
  analysis_steps  — each agent appends "AgentName: reasoning string"
  decision        — final BUY / SELL / HOLD (set by portfolio_manager node)
  agent_scores    — per-agent numeric conviction score (0-100)
  risk_flags      — any risk concerns raised during committee review
"""

from typing import Annotated, TypedDict, List, Optional
import operator


class AgentState(TypedDict):

    # ── Core identity ─────────────────────────────────────────
    ticker: str                  # e.g. "CPALL.BK"

    # ── Raw market data ───────────────────────────────────────
    # Full dict from fetch_all_data(): keys are raw_stock_obj, prices,
    # returns, info, metrics. Agents read this for qualitative context.
    data: dict

    # ── Running reasoning log (append-only) ──────────────────
    # Each agent appends one string: "AgentName: concise reasoning"
    # cli.py renders this as the Committee Reasoning Log table.
    analysis_steps: Annotated[List[str], operator.add]

    # ── Pre-computed quant context (set by cli.py) ────────────
    # Agents must READ these — never recompute them — so all stages
    # see a consistent set of numbers.
    #
    # Keys injected by cli.py:
    #   alpha_score       float  — generate_alpha_score() output (0-100)
    #   composite_risk    float  — Stage 0 fragility composite (0-100)
    #   macro_regime      str    — e.g. "NEUTRAL_GROWTH"
    #   macro_bias        str    — e.g. "NEUTRAL — sector selection is the alpha driver"
    #   sector            str    — e.g. "FINANCIALS"
    #   sector_score      float  — Stage 2 sector score (0-100)
    #   sector_rotation   str    — e.g. "MID_CYCLE_EXPANSION"
    #   roic              float
    #   wacc              float
    #   moat_spread       float  — roic - wacc
    #   sloan_ratio       float
    #   fcf_quality       float
    #   altman_z          float
    #   beta              float
    #   cvar              float
    #   sortino           float
    #   technical_strategy str   — "MOMENTUM" / "MEAN_REVERSION" / "BREAKOUT"
    #   entry_price       float
    #   tp_price          float
    #   sl_price          float
    #   rr_ratio          float
    #   signal_strength   int
    #   risk_verdict      str    — "APPROVED" / "REDUCED" / "REJECTED"
    #   position_shares   int
    #   position_pct      float
    #   risk_amount       float
    #   regime_scale      float
    #   kelly_fraction    float
    #   risk_flags        list[str]
    metadata: dict

    # ── Agent conviction scores (append-only) ─────────────────
    # Each agent appends a dict: {"agent": str, "score": int, "stance": str}
    # portfolio_manager_node uses this for weighted voting.
    agent_scores: Annotated[List[dict], operator.add]

    # ── Risk flags raised during committee review ─────────────
    # Any agent can append a warning string here.
    risk_flags: Annotated[List[str], operator.add]

    # ── Final output ──────────────────────────────────────────
    # Written by portfolio_manager_node as the last node in the graph.
    decision: str   # "BUY" | "SELL" | "HOLD"