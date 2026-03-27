"""
src/agents/fundamental_agent.py
Fundamental Analysis Agent — wired to the full calculator.py metrics pipeline.

Produces a structured fundamental signal dict consumed by the LangGraph state,
replacing the original stub that used only raw forward P/E.
"""

from src.agents.calculator import (
    calculate_sloan_ratio,
    calculate_roic,
    calculate_wacc,
    calculate_fcf_quality,
    calculate_altman_z,
    calculate_asset_turnover,
    calculate_ccc,
    generate_alpha_score,
)


def fundamental_agent(state: dict) -> dict:
    """
    Full fundamental analysis node for the LangGraph pipeline.

    Reads pre-fetched financial statements from state["data"] and runs every
    calculator metric.  Produces:
      - alpha_score       : composite 0–100 score
      - fundamental_signal: STRONG_BUY / BUY / NEUTRAL / SELL / STRONG_SELL
      - metrics           : full breakdown dict (passed downstream)
    """
    data        = state.get("data", {})
    financials  = data.get("financials")
    balance     = data.get("balance_sheet")
    cashflow    = data.get("cashflow")
    ticker_info = data.get("ticker_info", {})

    # Quantitative inputs already computed upstream (Stage 2 / calculator stage)
    quant       = data.get("quant", {})
    sortino     = quant.get("sortino", 0.0)
    beta        = quant.get("beta",    1.0)

    # Composite risk score from Stage 1 (market_risk.py)
    composite_risk   = state.get("composite_risk", 50.0)
    sector_macro_adj = state.get("sector_macro_adj", 0)

    # ── Compute all fundamental metrics ──────────────────────
    sloan        = calculate_sloan_ratio(financials, cashflow, balance)
    roic         = calculate_roic(financials, balance)
    wacc         = calculate_wacc(ticker_info, financials, balance, cashflow)
    fcf_quality  = calculate_fcf_quality(financials, cashflow)
    z_score      = calculate_altman_z(financials, balance, ticker_info)
    asset_to     = calculate_asset_turnover(financials, balance)
    ccc          = calculate_ccc(financials, balance)

    # ── Alpha score ───────────────────────────────────────────
    alpha = generate_alpha_score(
        roic            = roic,
        wacc            = wacc,
        sloan           = sloan,
        z_score         = z_score,
        sortino         = sortino,
        beta            = beta,
        fcf_quality     = fcf_quality,
        composite_risk  = composite_risk,
        sector_macro_adj= sector_macro_adj,
    )

    # ── Signal label ──────────────────────────────────────────
    if alpha >= 75:
        signal = "STRONG_BUY"
    elif alpha >= 55:
        signal = "BUY"
    elif alpha >= 40:
        signal = "NEUTRAL"
    elif alpha >= 25:
        signal = "SELL"
    else:
        signal = "STRONG_SELL"

    # ── ROIC vs WACC moat assessment ─────────────────────────
    spread = roic - wacc
    if spread > 0.10:
        moat = "WIDE"
    elif spread > 0.05:
        moat = "NARROW"
    elif spread > 0:
        moat = "MARGINAL"
    else:
        moat = "NONE — VALUE_DESTROYER"

    # ── Altman zone ───────────────────────────────────────────
    if z_score > 2.99:
        z_zone = "SAFE"
    elif z_score > 1.81:
        z_zone = "GREY"
    else:
        z_zone = "DISTRESS"

    metrics = {
        "alpha_score":   alpha,
        "roic":          round(roic,  4),
        "wacc":          round(wacc,  4),
        "roic_wacc_spread": round(spread, 4),
        "moat":          moat,
        "sloan_ratio":   round(sloan, 4),
        "fcf_quality":   round(fcf_quality, 4),
        "altman_z":      round(z_score, 4),
        "altman_zone":   z_zone,
        "asset_turnover":round(asset_to, 4),
        "cash_conversion_cycle": round(ccc, 2),
        "sortino":       round(sortino, 4),
        "beta":          round(beta, 4),
    }

    analysis_line = (
        f"Fundamental: {signal} | Alpha={alpha}/100 | "
        f"ROIC={roic*100:.1f}% WACC={wacc*100:.1f}% (spread={spread*100:+.1f}%) | "
        f"Moat={moat} | Sloan={sloan:+.3f} | FCFq={fcf_quality:.2f} | "
        f"Z={z_score:.2f} [{z_zone}]"
    )

    return {
        "analysis_steps":      [analysis_line],
        "fundamental_metrics": metrics,
        "metadata": {
            "fundamental_signal": signal,
            "alpha_score":        alpha,
        },
    }
