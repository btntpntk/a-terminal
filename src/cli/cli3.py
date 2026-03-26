import asyncio
import questionary
import pandas as pd
import numpy as np
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich.rule import Rule
from rich.text import Text

# Core data & graph
from src.data.providers import fetch_all_data
from src.graph.graph import hedge_fund_app

# Fundamental & quant calculators
from src.agents.calculator import (
    calculate_sloan_ratio, calculate_cvar_95, calculate_wacc,
    calculate_roic, calculate_rolling_sortino, calculate_asset_turnover,
    calculate_altman_z, calculate_ccc, generate_alpha_score
)

# Market Fragility Monitor — three-layer institutional risk framework
from src.agents.market_risk import (
    calculate_spx_200dma_buffer,
    calculate_yield_curve_spread,
    calculate_hy_credit_spread,
    calculate_breadth_above_50dma,
    calculate_rsp_spy_ratio,
    calculate_vix_level,
    calculate_vix_term_structure,
    calculate_composite_risk,
    calculate_confidence,
)

console = Console()


# ─────────────────────────────────────────────
# SHARED HELPERS
# ─────────────────────────────────────────────

def create_metric_card(title: str, value, color: str = "white") -> Panel:
    """Small, scannable KPI card for Rich Columns layout."""
    formatted_val = f"{value:.4f}" if isinstance(value, float) else str(value)
    return Panel(
        f"[bold {color}]{formatted_val}[/bold {color}]",
        title=title,
        expand=False,
    )


def _risk_color(score: float) -> str:
    """Map a 0–100 risk score to a Rich color string."""
    if score < 30:
        return "green"
    if score < 50:
        return "bright_green"
    if score < 65:
        return "yellow"
    if score < 80:
        return "orange3"
    return "red"


def _signal_color(signal: str) -> str:
    """Map signal keywords to a Rich color string."""
    bullish = {"BULL", "STEEP_GROWTH", "TIGHT_BENIGN", "BROAD_PARTICIPATION",
               "EQUAL_WEIGHT_LEADING", "COMPLACENCY", "STEEP_CONTANGO"}
    bearish = {"BEAR", "INVERTED_RECESSION", "ACUTE_CRISIS", "BREADTH_COLLAPSE",
               "EXTREME_CONCENTRATION", "PANIC_REGIME", "BACKWARDATION_PANIC"}
    if any(k in signal for k in bullish):
        return "green"
    if any(k in signal for k in bearish):
        return "red"
    return "yellow"


# ─────────────────────────────────────────────
# SECTION 0 — MARKET FRAGILITY MONITOR
# ─────────────────────────────────────────────

def _render_signal_row(table: Table, name: str, value_str: str, signal: str, risk_score: float) -> None:
    """Add one signal row to the fragility table."""
    bar_filled  = int(risk_score / 5)          # out of 20 blocks
    bar_empty   = 20 - bar_filled
    bar_color   = _risk_color(risk_score)
    bar_display = f"[{bar_color}]{'█' * bar_filled}[/{bar_color}]{'░' * bar_empty}"
    table.add_row(
        name,
        value_str,
        bar_display,
        f"[{_signal_color(signal)}]{signal}[/{_signal_color(signal)}]",
        f"[{_risk_color(risk_score)} bold]{risk_score:.0f}[/{_risk_color(risk_score)} bold]",
    )


async def run_market_fragility_monitor(spx_data: dict) -> dict:
    """
    Fetch all seven sub-signals, compute composite risk & confidence,
    render a rich dashboard section, and return the full results dict.
    """
    console.print(Rule("[bold cyan]0. MARKET FRAGILITY MONITOR[/bold cyan]"))
    console.print("[dim]Three-layer institutional risk framework  ·  Regime → Fragility → Trigger[/dim]\n")

    with console.status("[bold yellow]Fetching regime layer...", spinner="dots"):
        dma_result = calculate_spx_200dma_buffer(spx_data)
        yc_result  = calculate_yield_curve_spread()
        hy_result  = calculate_hy_credit_spread()

    with console.status("[bold yellow]Fetching fragility layer (breadth scan)...", spinner="dots"):
        breadth_result = calculate_breadth_above_50dma()
        rsp_result     = calculate_rsp_spy_ratio()

    with console.status("[bold yellow]Fetching trigger layer...", spinner="dots"):
        vix_result  = calculate_vix_level()
        term_result = calculate_vix_term_structure()

    # ── Composite & Confidence ────────────────────────────────
    regime_scores    = [dma_result.get("risk_score", 50), yc_result.get("risk_score", 50),  hy_result.get("risk_score", 50)]
    fragility_scores = [breadth_result.get("risk_score", 50), rsp_result.get("risk_score", 50)]
    trigger_scores   = [vix_result.get("risk_score", 50), term_result.get("risk_score", 50)]
    all_scores       = regime_scores + fragility_scores + trigger_scores

    composite   = calculate_composite_risk(regime_scores, fragility_scores, trigger_scores)
    confidence  = calculate_confidence(all_scores)

    comp_score  = composite["composite_risk"]
    conf_score  = confidence["confidence"]
    comp_color  = _risk_color(comp_score)
    conf_color  = "green" if conf_score >= 80 else "yellow" if conf_score >= 60 else "red"

    # ── Composite headline cards ──────────────────────────────
    headline = Columns([
        create_metric_card("COMPOSITE RISK", round(comp_score, 1), comp_color),
        create_metric_card("SIGNAL CONFIDENCE", round(conf_score, 1), conf_color),
        create_metric_card("REGIME LABEL", composite["regime_label"],  comp_color),
        create_metric_card("CONVERGENCE", confidence["signal"], conf_color),
    ])
    console.print(headline)
    console.print()

    # ── Per-layer signal table ────────────────────────────────
    table = Table(box=None, show_header=True, header_style="bold white")
    table.add_column("Signal",       style="cyan",  width=22)
    table.add_column("Value",        style="white", width=14)
    table.add_column("Risk Bar",     width=22, no_wrap=True)
    table.add_column("Status",       width=26)
    table.add_column("Score /100",   width=10, justify="right")

    # Regime layer
    table.add_row("[bold purple]── REGIME (40%)[/bold purple]", "", "", "", "")
    _render_signal_row(table, "SPX vs 200 DMA",
                       f"{dma_result.get('distance_pct', 'N/A'):+.2f}%",
                       dma_result.get("signal", "N/A"),
                       dma_result.get("risk_score", 50))
    _render_signal_row(table, "2s/10s Yield Spread",
                       f"{yc_result.get('spread_bps', 'N/A'):.1f} bps",
                       yc_result.get("signal", "N/A"),
                       yc_result.get("risk_score", 50))
    _render_signal_row(table, "HY Credit OAS",
                       f"{hy_result.get('oas_bps', 'N/A'):.1f} bps",
                       hy_result.get("signal", "N/A"),
                       hy_result.get("risk_score", 50))

    # Fragility layer
    table.add_row("[bold orange3]── FRAGILITY (40%)[/bold orange3]", "", "", "", "")
    _render_signal_row(table, "Breadth > 50 DMA",
                       f"{breadth_result.get('pct_above_50dma', 'N/A'):.1f}%",
                       breadth_result.get("signal", "N/A"),
                       breadth_result.get("risk_score", 50))
    _render_signal_row(table, "RSP / SPY Z-Score",
                       f"{rsp_result.get('z_score_1y', 'N/A'):.2f}σ",
                       rsp_result.get("signal", "N/A"),
                       rsp_result.get("risk_score", 50))

    # Trigger layer
    table.add_row("[bold green]── TRIGGER (20%)[/bold green]", "", "", "", "")
    _render_signal_row(table, "VIX Spot",
                       f"{vix_result.get('vix_level', 'N/A'):.2f}",
                       vix_result.get("signal", "N/A"),
                       vix_result.get("risk_score", 50))
    _render_signal_row(table, "VIX Roll Yield",
                       f"{term_result.get('roll_yield', 'N/A'):.2f}",
                       term_result.get("signal", "N/A"),
                       term_result.get("risk_score", 50))

    console.print(table)
    console.print()

    # ── Layer average summary ─────────────────────────────────
    ls = composite["layer_scores"]
    layer_summary = Columns([
        create_metric_card("REGIME AVG",    round(ls["regime"], 1),    _risk_color(ls["regime"])),
        create_metric_card("FRAGILITY AVG", round(ls["fragility"], 1), _risk_color(ls["fragility"])),
        create_metric_card("TRIGGER AVG",   round(ls["trigger"], 1),   _risk_color(ls["trigger"])),
    ])
    console.print(layer_summary)
    console.print()

    return {
        "composite": composite,
        "confidence": confidence,
        "regime":    {"dma": dma_result, "yield_curve": yc_result, "hy": hy_result},
        "fragility": {"breadth": breadth_result, "rsp_spy": rsp_result},
        "trigger":   {"vix": vix_result, "term": term_result},
    }


# ─────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────

async def run_analysis_cli():
    console.print(Panel.fit(
        "[bold green]ALPHA-STREAM ARCHITECT: QUANTITATIVE TERMINAL[/bold green]",
        border_style="green",
    ))

    ticker = await questionary.text("Enter Ticker (e.g., CPALL.BK):").ask_async()
    if not ticker:
        return

    # ── 0. Market Fragility Monitor (macro backdrop first) ────
    # We fetch SPX data upfront so it can be reused by the monitor.
    with console.status("[bold yellow]Fetching SPX market data...", spinner="bouncingBar"):
        spx_data = await fetch_all_data("^GSPC")

    await run_market_fragility_monitor(spx_data)

    # ── 1–3. Stock-level institutional suite ──────────────────
    console.print(Rule(f"[bold cyan]STOCK ANALYSIS  ·  {ticker.upper()}[/bold cyan]"))

    with console.status(f"[bold yellow]Running Institutional Suite for {ticker}...", spinner="bouncingBar"):
        # Fetch ticker data
        market_data = await fetch_all_data(ticker)
        stock   = market_data["raw_stock_obj"]
        returns = market_data["returns"]

        # Local quantitative calculations
        s_ratio   = calculate_sloan_ratio(stock.financials, stock.cashflow, stock.balance_sheet)
        wacc      = calculate_wacc(stock.info, stock.financials, stock.balance_sheet, stock.cashflow)
        roic      = calculate_roic(stock.financials, stock.balance_sheet)
        cvar      = calculate_cvar_95(returns)
        sortino   = calculate_rolling_sortino(returns)
        a_turnover = calculate_asset_turnover(stock.financials, stock.balance_sheet)
        z_score   = calculate_altman_z(stock.financials, stock.balance_sheet)
        ccc_val   = calculate_ccc(stock.financials, stock.balance_sheet)
        alpha     = generate_alpha_score(roic, wacc, s_ratio, z_score, sortino, 0)

        # Multi-agent graph
        result = await hedge_fund_app.ainvoke({
            "ticker": ticker,
            "data": market_data,
            "analysis_steps": [],
            "metadata": {"alpha_score": alpha},
        })

    # ── Row 1: Moat & Alpha ───────────────────────────────────
    moat_spread  = roic - wacc
    spread_color = "green" if moat_spread > 0 else "red"

    moat_row = Columns([
        create_metric_card("ROIC",        roic,        "cyan"),
        create_metric_card("WACC",        wacc,        "yellow"),
        create_metric_card("Moat Spread", moat_spread, spread_color),
        create_metric_card("ALPHA SCORE", alpha,       "bold magenta"),
    ])

    # ── Row 2: Risk & Quality ─────────────────────────────────
    quality_row = Columns([
        create_metric_card("Sloan Ratio",    s_ratio, "white" if s_ratio < 0.1 else "red"),
        create_metric_card("Altman Z-Score", z_score, "green" if z_score > 2.9 else "red"),
        create_metric_card("CVaR (95%)",     cvar,    "red"),
        create_metric_card("Sortino",        sortino, "green" if sortino > 1 else "yellow"),
    ])

    # ── Row 3: Operational Efficiency ────────────────────────
    efficiency_row = Columns([
        create_metric_card("Asset Turnover",    a_turnover, "blue"),
        create_metric_card("Cash Conv. Cycle",  ccc_val,    "blue"),
    ])

    console.print("\n[bold]1. FUNDAMENTAL & QUANTITATIVE INTELLIGENCE[/bold]")
    console.print(moat_row)
    console.print(quality_row)
    console.print(efficiency_row)

    # ── Agent Audit Table ─────────────────────────────────────
    table = Table(
        title="\n[bold]2. COMMITTEE REASONING LOG[/bold]",
        title_justify="left",
        box=None,
    )
    table.add_column("Agent",       style="bold cyan", width=15)
    table.add_column("Audit Trail", style="italic white")

    for step in result["analysis_steps"]:
        if ":" in step:
            agent, reason = step.split(":", 1)
            table.add_row(agent.strip(), reason.strip())
        else:
            table.add_row("System", step)

    console.print(table)

    # ── Final Verdict ─────────────────────────────────────────
    decision       = result["decision"]
    decision_color = "green" if "BUY" in decision else "red" if "SELL" in decision else "yellow"
    console.print(Panel(
        f"[bold {decision_color}]FINAL DECISION: {decision}[/bold {decision_color}]",
        title="[bold]3. PORTFOLIO MANAGER VERDICT[/bold]",
        border_style=decision_color,
    ))


if __name__ == "__main__":
    asyncio.run(run_analysis_cli())