"""
src/graph/graph.py
Alpha-Stream Agent Graph — Full Five-Node Committee Pipeline

Node execution order:
  fundamental_node
       ↓
  technical_node
       ↓
  sentiment_node
       ↓
  risk_node
       ↓
  portfolio_manager_node → END

Every node reads pre-computed quant scores from state["metadata"]
(injected by cli.py before ainvoke) and writes qualitative reasoning
to state["analysis_steps"] and a numeric score to state["agent_scores"].

The portfolio_manager_node reads all agent_scores for a weighted vote
and writes the final state["decision"] as BUY / SELL / HOLD.
"""

from langgraph.graph import StateGraph, END
from src.graph.state import AgentState


# ══════════════════════════════════════════════════════════════
# NODE 1 — FUNDAMENTAL AGENT
# Reads: roic, wacc, sloan_ratio, fcf_quality, altman_z, alpha_score
# Writes: analysis_steps, agent_scores
# ══════════════════════════════════════════════════════════════

def fundamental_node(state: AgentState) -> dict:
    """
    Qualitative assessment of financial quality and economic moat.
    Does NOT recompute — uses pre-calculated values from metadata.
    """
    m = state["metadata"]
    ticker = state["ticker"]

    roic        = m.get("roic",        0.0)
    wacc        = m.get("wacc",        0.0)
    moat_spread = m.get("moat_spread", 0.0)
    sloan       = m.get("sloan_ratio", 0.0)
    fcf_q       = m.get("fcf_quality", 0.0)
    z_score     = m.get("altman_z",    0.0)
    alpha       = m.get("alpha_score", 0.0)
    sector      = m.get("sector",      "UNKNOWN")

    reasoning_parts = []
    score = 50  # neutral anchor

    # ── Economic moat ─────────────────────────────────────────
    if moat_spread > 0.10:
        reasoning_parts.append(f"strong ROIC spread of {moat_spread*100:.1f}% — wide moat confirmed")
        score += 20
    elif moat_spread > 0.05:
        reasoning_parts.append(f"positive ROIC spread {moat_spread*100:.1f}% — narrow moat")
        score += 10
    elif moat_spread > 0:
        reasoning_parts.append(f"marginal ROIC > WACC ({moat_spread*100:.1f}%) — weak moat")
        score += 4
    else:
        reasoning_parts.append(f"ROIC {roic*100:.1f}% < WACC {wacc*100:.1f}% — value destroyer")
        score -= 15

    # ── Earnings quality ──────────────────────────────────────
    if abs(sloan) < 0.05 and fcf_q > 0.6:
        reasoning_parts.append(f"earnings quality clean (Sloan {sloan:.3f}, FCF quality {fcf_q:.2f})")
        score += 12
    elif sloan > 0.15:
        reasoning_parts.append(f"elevated Sloan ratio {sloan:.3f} — possible accrual inflation")
        score -= 10
        state["risk_flags"].append(f"FundamentalAgent: High Sloan ratio {sloan:.3f} on {ticker}")

    # ── Survival ─────────────────────────────────────────────
    if z_score > 2.99:
        reasoning_parts.append(f"Altman Z {z_score:.2f} in safe zone")
        score += 10
    elif z_score > 1.81:
        reasoning_parts.append(f"Altman Z {z_score:.2f} in grey zone — monitor leverage")
        score += 2
    else:
        reasoning_parts.append(f"Altman Z {z_score:.2f} DISTRESS zone — bankruptcy risk elevated")
        score -= 20
        state["risk_flags"].append(f"FundamentalAgent: Altman Z {z_score:.2f} — distress signal on {ticker}")

    # ── Alpha score context ────────────────────────────────────
    reasoning_parts.append(f"composite alpha score {alpha:.0f}/100 in sector {sector}")
    score = max(0, min(100, score))

    stance = "BULLISH" if score >= 65 else "BEARISH" if score <= 35 else "NEUTRAL"

    return {
        "analysis_steps": [f"FundamentalAgent: {'; '.join(reasoning_parts)}"],
        "agent_scores":   [{"agent": "FundamentalAgent", "score": score, "stance": stance}],
    }


# ══════════════════════════════════════════════════════════════
# NODE 2 — TECHNICAL AGENT
# Reads: technical_strategy, entry_price, tp_price, sl_price,
#        rr_ratio, signal_strength, composite_risk
# Writes: analysis_steps, agent_scores
# ══════════════════════════════════════════════════════════════

def technical_node(state: AgentState) -> dict:
    """
    Qualitative assessment of the technical setup and strategy fit.
    """
    m = state["metadata"]

    strategy        = m.get("technical_strategy", "UNKNOWN")
    entry           = m.get("entry_price",   0.0)
    tp              = m.get("tp_price",      0.0)
    sl              = m.get("sl_price",      0.0)
    rr              = m.get("rr_ratio",      0.0)
    sig_strength    = m.get("signal_strength", 0)
    composite_risk  = m.get("composite_risk",  50)

    reasoning_parts = []
    score = 50

    # ── Strategy fit ──────────────────────────────────────────
    reasoning_parts.append(f"{strategy} strategy selected for current price regime")

    # ── Signal strength ───────────────────────────────────────
    if sig_strength >= 70:
        reasoning_parts.append(f"signal strength {sig_strength}/100 — high conviction setup")
        score += 20
    elif sig_strength >= 50:
        reasoning_parts.append(f"signal strength {sig_strength}/100 — moderate conviction")
        score += 8
    else:
        reasoning_parts.append(f"signal strength {sig_strength}/100 — low conviction, caution")
        score -= 10

    # ── R:R assessment ────────────────────────────────────────
    if rr >= 2.5:
        reasoning_parts.append(f"excellent R:R of 1:{rr:.2f} — asymmetric upside confirmed")
        score += 18
    elif rr >= 1.5:
        reasoning_parts.append(f"acceptable R:R of 1:{rr:.2f} — meets minimum threshold")
        score += 6
    else:
        reasoning_parts.append(f"R:R of 1:{rr:.2f} below minimum — setup quality questionable")
        score -= 18

    # ── Regime context ────────────────────────────────────────
    if composite_risk > 65:
        reasoning_parts.append(f"elevated macro risk {composite_risk:.0f} — reduced conviction on technical entries")
        score -= 8

    score = max(0, min(100, score))
    stance = "BULLISH" if score >= 65 else "BEARISH" if score <= 35 else "NEUTRAL"

    return {
        "analysis_steps": [f"TechnicalAgent: {'; '.join(reasoning_parts)}"],
        "agent_scores":   [{"agent": "TechnicalAgent", "score": score, "stance": stance}],
    }


# ══════════════════════════════════════════════════════════════
# NODE 3 — SENTIMENT AGENT
# Reads: sector, macro_regime, macro_bias, sector_rotation,
#        composite_risk, sector_score
# Writes: analysis_steps, agent_scores
# ══════════════════════════════════════════════════════════════

def sentiment_node(state: AgentState) -> dict:
    """
    Macro-sentiment and sector rotation assessment.
    Synthesises Stage 1 (macro) and Stage 2 (sector) context qualitatively.
    """
    m = state["metadata"]

    macro_regime     = m.get("macro_regime",    "NEUTRAL_GROWTH")
    macro_bias       = m.get("macro_bias",      "NEUTRAL")
    sector           = m.get("sector",          "UNKNOWN")
    sector_score     = m.get("sector_score",    50.0)
    sector_rotation  = m.get("sector_rotation", "TRANSITION_MIXED")
    composite_risk   = m.get("composite_risk",  50.0)

    reasoning_parts = []
    score = 50

    # ── Macro backdrop ────────────────────────────────────────
    macro_positive = any(k in macro_regime for k in ("RISK_ON", "NEUTRAL_GROWTH", "EXPANSION"))
    macro_negative = any(k in macro_regime for k in ("RISK_OFF", "CRISIS", "DEFENSIVE"))

    if macro_positive:
        reasoning_parts.append(f"macro regime {macro_regime} supportive of equity risk")
        score += 12
    elif macro_negative:
        reasoning_parts.append(f"macro regime {macro_regime} — defensive tilt, reduce cyclical exposure")
        score -= 15
    else:
        reasoning_parts.append(f"macro regime {macro_regime} — neutral backdrop")

    # ── Sector rotation alignment ─────────────────────────────
    if sector_score >= 65:
        reasoning_parts.append(f"{sector} sector strong (score {sector_score:.0f}) in {sector_rotation} rotation")
        score += 15
    elif sector_score >= 45:
        reasoning_parts.append(f"{sector} sector neutral (score {sector_score:.0f})")
        score += 3
    else:
        reasoning_parts.append(f"{sector} sector weak (score {sector_score:.0f}) — fighting sector headwind")
        score -= 12

    # ── DXY / EM flow for SET universe ───────────────────────
    if "DEFENSIVE" in macro_bias.upper() or "REDUCE_EM" in macro_bias.upper():
        reasoning_parts.append("USD strength / risk-off signal — EM/SET outflow risk elevated")
        score -= 8
        state["risk_flags"].append("SentimentAgent: EM outflow risk — consider position size reduction")
    elif "RISK_ON" in macro_bias.upper() or "ADD_EM" in macro_bias.upper():
        reasoning_parts.append("USD weakness / risk-on — EM/SET inflow tailwind")
        score += 8

    score = max(0, min(100, score))
    stance = "BULLISH" if score >= 65 else "BEARISH" if score <= 35 else "NEUTRAL"

    return {
        "analysis_steps": [f"SentimentAgent: {'; '.join(reasoning_parts)}"],
        "agent_scores":   [{"agent": "SentimentAgent", "score": score, "stance": stance}],
    }


# ══════════════════════════════════════════════════════════════
# NODE 4 — RISK AGENT
# Reads: cvar, sortino, beta, composite_risk, risk_verdict,
#        position_pct, risk_amount, regime_scale, kelly_fraction,
#        risk_flags (from other agents)
# Writes: analysis_steps, agent_scores, risk_flags
# ══════════════════════════════════════════════════════════════

def risk_node(state: AgentState) -> dict:
    """
    Quantitative risk review and position sizing validation.
    Reviews what the risk engine (Stage 5) computed and provides
    qualitative context to the committee.
    """
    m = state["metadata"]

    cvar          = m.get("cvar",          0.0)
    sortino       = m.get("sortino",       0.0)
    beta          = m.get("beta",          1.0)
    composite_risk = m.get("composite_risk", 50.0)
    risk_verdict  = m.get("risk_verdict",  "UNKNOWN")
    position_pct  = m.get("position_pct",  0.0)
    regime_scale  = m.get("regime_scale",  1.0)
    kelly_frac    = m.get("kelly_fraction", 0.0)
    r_flags       = m.get("risk_flags",    [])

    reasoning_parts = []
    score = 50
    new_flags = []

    # ── Position sizing verdict ───────────────────────────────
    if risk_verdict == "APPROVED":
        reasoning_parts.append(f"risk engine APPROVED position — {position_pct:.2f}% portfolio exposure")
        score += 15
    elif risk_verdict == "REDUCED":
        reasoning_parts.append(f"risk engine REDUCED position to {position_pct:.2f}% — {len(r_flags)} flag(s) triggered")
        score += 2
    else:
        reasoning_parts.append("risk engine REJECTED trade — position size is zero")
        score -= 30

    # ── Regime scaling ────────────────────────────────────────
    if regime_scale < 0.5:
        reasoning_parts.append(f"regime scale {regime_scale*100:.0f}% — high macro risk forcing reduced exposure")
        score -= 10
    elif regime_scale >= 0.8:
        reasoning_parts.append(f"regime scale {regime_scale*100:.0f}% — macro environment supportive of full sizing")
        score += 5

    # ── Return quality ────────────────────────────────────────
    if sortino > 1.5:
        reasoning_parts.append(f"Sortino {sortino:.2f} — strong risk-adjusted return profile")
        score += 10
    elif sortino < 0.5:
        reasoning_parts.append(f"Sortino {sortino:.2f} — weak risk-adjusted returns")
        score -= 8

    # ── CVaR ─────────────────────────────────────────────────
    if cvar > 0.03:
        reasoning_parts.append(f"CVaR {cvar*100:.2f}% — high tail risk, monitor closely")
        new_flags.append(f"RiskAgent: CVaR {cvar*100:.2f}% exceeds 3% daily tail threshold")
        score -= 8

    # ── Beta ─────────────────────────────────────────────────
    if beta > 1.5 and composite_risk > 55:
        reasoning_parts.append(f"high beta {beta:.2f} in elevated risk environment — amplified downside")
        new_flags.append(f"RiskAgent: Beta {beta:.2f} + composite risk {composite_risk:.0f} = volatility trap risk")
        score -= 10

    score = max(0, min(100, score))
    stance = "BULLISH" if score >= 65 else "BEARISH" if score <= 35 else "NEUTRAL"

    return {
        "analysis_steps": [f"RiskAgent: {'; '.join(reasoning_parts)}"],
        "agent_scores":   [{"agent": "RiskAgent", "score": score, "stance": stance}],
        "risk_flags":     new_flags,
    }


# ══════════════════════════════════════════════════════════════
# NODE 5 — PORTFOLIO MANAGER
# Reads: all agent_scores, all risk_flags, all analysis_steps
# Writes: decision (BUY / SELL / HOLD), analysis_steps
# ══════════════════════════════════════════════════════════════

# Agent weights in the final vote.
# Fundamental and Risk carry more weight — they are the structural
# filters. Technical and Sentiment are directional refiners.
AGENT_WEIGHTS = {
    "FundamentalAgent": 0.35,
    "TechnicalAgent":   0.25,
    "SentimentAgent":   0.20,
    "RiskAgent":        0.20,
}


def portfolio_manager_node(state: AgentState) -> dict:
    """
    Weighted-vote aggregation across all four agents.
    Applies a hard veto if any critical risk flag is present.
    Writes the final BUY / SELL / HOLD decision.
    """
    scores      = state.get("agent_scores", [])
    risk_flags  = state.get("risk_flags",   [])
    m           = state["metadata"]

    risk_verdict = m.get("risk_verdict", "UNKNOWN")
    alpha        = m.get("alpha_score",  0.0)

    # ── Hard veto: risk engine rejected ──────────────────────
    if risk_verdict == "REJECTED":
        return {
            "analysis_steps": [
                "PortfolioManager: HARD VETO — risk engine rejected the trade; "
                "position size is zero. Decision: HOLD."
            ],
            "decision": "HOLD",
        }

    # ── Weighted vote ─────────────────────────────────────────
    weighted_sum  = 0.0
    total_weight  = 0.0
    stance_counts = {"BULLISH": 0, "NEUTRAL": 0, "BEARISH": 0}

    for entry in scores:
        agent   = entry.get("agent",  "Unknown")
        sc      = entry.get("score",  50)
        stance  = entry.get("stance", "NEUTRAL")
        weight  = AGENT_WEIGHTS.get(agent, 0.10)
        weighted_sum  += sc * weight
        total_weight  += weight
        stance_counts[stance] = stance_counts.get(stance, 0) + 1

    if total_weight == 0:
        composite_score = 50.0
    else:
        composite_score = weighted_sum / total_weight

    # ── Soft veto: critical flags ─────────────────────────────
    # Each critical flag (distress, EM outflow etc.) deducts from score
    critical_flag_penalty = min(len(risk_flags) * 5, 20)
    composite_score -= critical_flag_penalty

    # ── Decision threshold ────────────────────────────────────
    # BUY  requires: weighted score ≥ 62, alpha ≥ 50, ≥ 2 bullish agents
    # SELL requires: weighted score ≤ 38 OR ≥ 3 bearish agents
    # HOLD: everything in between
    composite_score = max(0, min(100, composite_score))

    n_bullish = stance_counts["BULLISH"]
    n_bearish = stance_counts["BEARISH"]

    if composite_score >= 62 and alpha >= 50 and n_bullish >= 2:
        decision = "BUY"
    elif composite_score <= 38 or n_bearish >= 3:
        decision = "SELL"
    else:
        decision = "HOLD"

    # ── Reasoning summary ─────────────────────────────────────
    flag_note = f"; {len(risk_flags)} risk flag(s) applied penalty -{critical_flag_penalty}pts" if risk_flags else ""
    reasoning = (
        f"committee weighted score {composite_score:.1f}/100 "
        f"(Bullish: {n_bullish}, Neutral: {stance_counts['NEUTRAL']}, Bearish: {n_bearish}){flag_note}. "
        f"Alpha {alpha:.0f}/100. Final decision: {decision}."
    )

    return {
        "analysis_steps": [f"PortfolioManager: {reasoning}"],
        "decision":        decision,
    }


# ══════════════════════════════════════════════════════════════
# GRAPH ASSEMBLY
# ══════════════════════════════════════════════════════════════

def _build_graph() -> StateGraph:
    builder = StateGraph(AgentState)

    builder.add_node("fundamental",        fundamental_node)
    builder.add_node("technical",          technical_node)
    builder.add_node("sentiment",          sentiment_node)
    builder.add_node("risk",               risk_node)
    builder.add_node("portfolio_manager",  portfolio_manager_node)

    builder.set_entry_point("fundamental")
    builder.add_edge("fundamental",       "technical")
    builder.add_edge("technical",         "sentiment")
    builder.add_edge("sentiment",         "risk")
    builder.add_edge("risk",              "portfolio_manager")
    builder.add_edge("portfolio_manager", END)

    return builder


hedge_fund_app = _build_graph().compile()