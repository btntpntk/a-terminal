"""
src/cli/cli.py
Alpha-Stream Architect — Quantitative Terminal

Five-stage institutional pipeline:
  Stage 0 · Market Fragility Monitor     (macro backdrop + regime)
  Stage 1 · Global Macro Signals         (Gold, Oil, DXY, Copper)
  Stage 2 · Sector Overall               (rotation, RS, breadth, flow)
  Stage 3 · Stock Filtering              (fundamental + quant screening)
  Stage 4 · Technical Indicator          (adaptive strategy, TP/SL/R:R)
  Stage 5 · Risk Management              (Kelly, heat, correlation, CVaR)
  Stage 6 · Agent Committee              (multi-agent qualitative verdict)
"""

import asyncio
import questionary
import pandas as pd
import numpy as np
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich.rule import Rule
from rich.live import Live
from rich.align import Align
from rich.text import Text
from rich import box
from dataclasses import asdict

# ── Core infrastructure ────────────────────────────────────────
from src.data.providers import fetch_all_data
from src.graph.graph import hedge_fund_app

# ── Stage 0: Market Fragility ─────────────────────────────────
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

# ── Stage 1: Global Macro ─────────────────────────────────────
from src.agents.global_macro import run_global_macro_analysis

# ── Stage 2: Sector Screener ──────────────────────────────────
from src.agents.sector_screener import run_sector_screener, get_sector_for_ticker, UNIVERSE_REGISTRY

# ── Stage 3: Calculator ───────────────────────────────────────
from src.agents.calculator import (
    calculate_sloan_ratio, calculate_cvar_95, calculate_wacc,
    calculate_roic, calculate_rolling_sortino, calculate_asset_turnover,
    calculate_altman_z, calculate_ccc, calculate_fcf_quality,
    generate_alpha_score,
)

# ── Stage 4: Technical ────────────────────────────────────────
from src.agents.technical import run_technical_analysis, TechnicalSignal

# ── Stage 5: Risk Management ──────────────────────────────────
from src.agents.risk_manager import (
    make_risk_decision, RiskDecision, OpenPosition,
    MAX_PORTFOLIO_HEAT, MIN_RR_RATIO,
)

console = Console()


# ══════════════════════════════════════════════════════════════
# THEME & PRIMITIVES
# ══════════════════════════════════════════════════════════════

ACCENT    = "bright_cyan"
DIM       = "grey50"
SEPARATOR = "grey23"

STAGE_COLORS = {
    0: "bright_cyan",
    1: "gold1",
    2: "medium_purple1",
    3: "steel_blue1",
    4: "orange1",
    5: "red1",
    6: "bright_green",
}

def _risk_color(score: float) -> str:
    if score < 30:  return "bright_green"
    if score < 50:  return "green3"
    if score < 65:  return "yellow3"
    if score < 80:  return "orange3"
    return "red1"

def _signal_color(signal: str) -> str:
    bullish = {"BULL", "STEEP_GROWTH", "TIGHT_BENIGN", "BROAD_PARTICIPATION",
               "EQUAL_WEIGHT_LEADING", "COMPLACENCY", "STEEP_CONTANGO",
               "RISK_ON", "EXPANSION", "APPROVED", "STRONG_BUY"}
    bearish = {"BEAR", "INVERTED", "ACUTE_CRISIS", "BREADTH_COLLAPSE",
               "EXTREME_CONCENTRATION", "PANIC", "BACKWARDATION",
               "REJECTED", "AVOID", "CRISIS", "DESTRUCTION"}
    s = signal.upper()
    if any(k in s for k in bullish): return "bright_green"
    if any(k in s for k in bearish): return "red1"
    return "yellow3"

def _verdict_color(verdict: str) -> str:
    v = verdict.upper()
    if "APPROVED" in v or "BUY" in v:  return "bright_green"
    if "REJECTED" in v or "SELL" in v: return "red1"
    return "yellow3"

def _bar(score: float, width: int = 20) -> str:
    """Filled/empty block progress bar, color-coded by score."""
    filled = int(score / 100 * width)
    empty  = width - filled
    col    = _risk_color(score)
    return f"[{col}]{'█' * filled}[/{col}][{SEPARATOR}]{'░' * empty}[/{SEPARATOR}]"

def _mini_bar(score: float, width: int = 12) -> str:
    filled = int(score / 100 * width)
    empty  = width - filled
    col    = _risk_color(score)
    return f"[{col}]{'▪' * filled}[/{col}][{SEPARATOR}]{'·' * empty}[/{SEPARATOR}]"

def _kpi(title: str, value, color: str = "white",
         width: int = 18, suffix: str = "") -> Panel:
    """Compact KPI panel card."""
    if isinstance(value, float):
        formatted = f"{value:+.4f}{suffix}" if "+" in f"{value:+.4f}" or value < 0 else f"{value:.4f}{suffix}"
    else:
        formatted = f"{value}{suffix}"
    return Panel(
        f"[bold {color}]{formatted}[/bold {color}]",
        title=f"[{DIM}]{title}[/{DIM}]",
        title_align="left",
        border_style=SEPARATOR,
        padding=(0, 1),
        expand=False,
    )

def _stage_rule(n: int, title: str) -> None:
    col = STAGE_COLORS.get(n, "white")
    console.print()
    console.print(Rule(
        f"[bold {col}]  STAGE {n}  ·  {title}  [/bold {col}]",
        style=f"{col} dim",
        characters="─",
    ))
    console.print()

def _gate_result(passed: bool, reason: str) -> None:
    icon  = "✓" if passed else "✗"
    color = "bright_green" if passed else "red1"
    console.print(f"  [{color}]{icon}[/{color}]  [{color}]{reason}[/{color}]")
    console.print()


# ══════════════════════════════════════════════════════════════
# STAGE 0 — MARKET FRAGILITY MONITOR
# ══════════════════════════════════════════════════════════════

def _fragility_signal_row(table: Table, label: str, value_str: str,
                          signal: str, score: float) -> None:
    table.add_row(
        f"[white]{label}[/white]",
        f"[bold white]{value_str}[/bold white]",
        _bar(score),
        f"[{_signal_color(signal)}]{signal}[/{_signal_color(signal)}]",
        f"[{_risk_color(score)} bold]{score:.0f}[/{_risk_color(score)} bold]",
    )

async def run_stage0_fragility(spx_data: dict) -> dict:
    _stage_rule(0, "MARKET FRAGILITY MONITOR")
    console.print(f"  [{DIM}]Regime → Fragility → Trigger   ·   Three-layer institutional risk framework[/{DIM}]\n")

    with console.status(f"[{DIM}]Scanning regime layer...[/{DIM}]", spinner="dots"):
        dma_r  = calculate_spx_200dma_buffer(spx_data)
        yc_r   = calculate_yield_curve_spread()
        hy_r   = calculate_hy_credit_spread()

    with console.status(f"[{DIM}]Scanning fragility layer...[/{DIM}]", spinner="dots"):
        brd_r  = calculate_breadth_above_50dma()
        rsp_r  = calculate_rsp_spy_ratio()

    with console.status(f"[{DIM}]Scanning trigger layer...[/{DIM}]", spinner="dots"):
        vix_r  = calculate_vix_level()
        term_r = calculate_vix_term_structure()

    reg_sc  = [dma_r.get("risk_score",50), yc_r.get("risk_score",50), hy_r.get("risk_score",50)]
    fra_sc  = [brd_r.get("risk_score",50), rsp_r.get("risk_score",50)]
    tri_sc  = [vix_r.get("risk_score",50), term_r.get("risk_score",50)]
    all_sc  = reg_sc + fra_sc + tri_sc

    composite  = calculate_composite_risk(reg_sc, fra_sc, tri_sc)
    confidence = calculate_confidence(all_sc)
    comp_score = composite["composite_risk"]
    conf_score = confidence["confidence"]

    # ── Headline KPIs ────────────────────────────────────────
    console.print(Columns([
        _kpi("COMPOSITE RISK",    round(comp_score, 1), _risk_color(comp_score)),
        _kpi("CONFIDENCE",        round(conf_score, 1),
             "bright_green" if conf_score >= 80 else "yellow3" if conf_score >= 60 else "red1"),
        _kpi("REGIME LABEL",      composite["regime_label"],     _risk_color(comp_score)),
        _kpi("SIGNAL CONVERGENCE",confidence["signal"],
             "bright_green" if "HIGH" in confidence["signal"] else "yellow3"),
    ], equal=False, expand=False))
    console.print()

    # ── Per-signal table ──────────────────────────────────────
    t = Table(box=None, show_header=True, header_style=f"bold {DIM}",
              padding=(0, 1), show_edge=False)
    t.add_column("Signal",    style="cyan", width=24)
    t.add_column("Value",     style="white", width=14)
    t.add_column("Risk",      width=22, no_wrap=True)
    t.add_column("Status",    width=28)
    t.add_column("Score",     width=6, justify="right")

    ls = composite["layer_scores"]

    t.add_row(f"[bold {STAGE_COLORS[0]}]REGIME  ·  {ls['regime']:.0f}/100[/bold {STAGE_COLORS[0]}]",
              "", _mini_bar(ls["regime"], 12), "", "")
    _fragility_signal_row(t, "  SPX vs 200 DMA",
        f"{dma_r.get('distance_pct','N/A'):+.2f}%",
        dma_r.get("signal","N/A"), dma_r.get("risk_score",50))
    _fragility_signal_row(t, "  2s/10s Spread",
        f"{yc_r.get('spread_bps','N/A'):.1f} bps",
        yc_r.get("signal","N/A"), yc_r.get("risk_score",50))
    _fragility_signal_row(t, "  HY Credit OAS",
        f"{hy_r.get('oas_bps','N/A'):.1f} bps",
        hy_r.get("signal","N/A"), hy_r.get("risk_score",50))

    t.add_row("", "", "", "", "")
    t.add_row(f"[bold yellow3]FRAGILITY  ·  {ls['fragility']:.0f}/100[/bold yellow3]",
              "", _mini_bar(ls["fragility"], 12), "", "")
    _fragility_signal_row(t, "  Breadth > 50 DMA",
        f"{brd_r.get('pct_above_50dma','N/A'):.1f}%",
        brd_r.get("signal","N/A"), brd_r.get("risk_score",50))
    _fragility_signal_row(t, "  RSP/SPY Z-Score",
        f"{rsp_r.get('z_score_1y','N/A'):.2f}σ",
        rsp_r.get("signal","N/A"), rsp_r.get("risk_score",50))

    t.add_row("", "", "", "", "")
    t.add_row(f"[bold green3]TRIGGER  ·  {ls['trigger']:.0f}/100[/bold green3]",
              "", _mini_bar(ls["trigger"], 12), "", "")
    _fragility_signal_row(t, "  VIX Spot",
        f"{vix_r.get('vix_level','N/A'):.2f}",
        vix_r.get("signal","N/A"), vix_r.get("risk_score",50))
    _fragility_signal_row(t, "  VIX Roll Yield",
        f"{term_r.get('roll_yield','N/A'):.2f}",
        term_r.get("signal","N/A"), term_r.get("risk_score",50))

    console.print(t)
    console.print()

    gate_pass = comp_score < 65
    _gate_result(gate_pass,
        f"Composite risk {comp_score:.0f} — {'proceed' if gate_pass else 'ELEVATED — position sizes will be scaled'}.")

    return {
        "composite": composite, "confidence": confidence,
        "composite_risk": comp_score,
        "regime": {"dma": dma_r, "yield_curve": yc_r, "hy": hy_r},
        "fragility": {"breadth": brd_r, "rsp_spy": rsp_r},
        "trigger": {"vix": vix_r, "term": term_r},
        "gate_pass": gate_pass,
    }


# ══════════════════════════════════════════════════════════════
# STAGE 1 — GLOBAL MACRO
# ══════════════════════════════════════════════════════════════

async def run_stage1_macro() -> dict:
    _stage_rule(1, "GLOBAL MACRO SIGNALS")
    console.print(f"  [{DIM}]Gold  ·  Crude Oil  ·  DXY  ·  Copper   ·   Cross-asset regime detection[/{DIM}]\n")

    with console.status(f"[{DIM}]Fetching commodity & FX signals...[/{DIM}]", spinner="dots"):
        macro = run_global_macro_analysis()

    # ── Headline ─────────────────────────────────────────────
    macro_risk = macro["composite_macro_risk"]
    console.print(Columns([
        _kpi("MACRO RISK",      macro_risk, _risk_color(macro_risk)),
        _kpi("REGIME",          macro["macro_regime"],     _risk_color(macro_risk)),
        _kpi("MACRO BIAS",      macro["macro_bias_summary"][:28],  _risk_color(macro_risk)),
    ], equal=False, expand=False))
    console.print()

    # ── Per-asset table ───────────────────────────────────────
    assets = [
        ("Gold (GC=F)",      macro["gold"]),
        ("Crude Oil (CL=F)", macro["crude_oil"]),
        ("DXY (Dollar)",     macro["dxy"]),
        ("Copper (HG=F)",    macro["copper"]),
    ]

    t = Table(box=None, show_header=True, header_style=f"bold {DIM}",
              padding=(0, 1), show_edge=False)
    t.add_column("Asset",       style="gold1",  width=20)
    t.add_column("Price",       style="white",  width=12)
    t.add_column("20d Mom",     width=10, justify="right")
    t.add_column("Z-Score",     width=10, justify="right")
    t.add_column("Signal",      width=26)
    t.add_column("Bias",        width=22)
    t.add_column("Risk",        width=6, justify="right")

    for name, d in assets:
        mom   = d.get("mom_20d_pct", 0)
        z     = d.get("z_score_60d", 0)
        sig   = d.get("signal", "N/A")
        bias  = d.get("macro_bias", "N/A")
        risk  = d.get("risk_score", 50)
        price = d.get("current_price", "N/A")
        mc    = "bright_green" if mom > 0 else "red1"
        zc    = "bright_green" if z > 0 else "red1"
        t.add_row(
            name,
            str(price),
            f"[{mc}]{mom:+.2f}%[/{mc}]",
            f"[{zc}]{z:+.2f}σ[/{zc}]",
            f"[{_signal_color(sig)}]{sig}[/{_signal_color(sig)}]",
            f"[{DIM}]{bias}[/{DIM}]",
            f"[{_risk_color(risk)} bold]{risk}[/{_risk_color(risk)} bold]",
        )

    console.print(t)
    console.print()

    # ── Sector adjustment preview ─────────────────────────────
    adj = macro.get("sector_adjustments", {})
    if adj:
        adj_parts = []
        for sector, pts in sorted(adj.items(), key=lambda x: -abs(x[1])):
            col = "bright_green" if pts > 0 else "red1" if pts < 0 else DIM
            adj_parts.append(f"[{col}]{sector} {pts:+d}[/{col}]")
        console.print(f"  [{DIM}]Sector adjustments:[/{DIM}]  " + "   ".join(adj_parts[:6]))
        console.print()

    gate_pass = macro_risk < 65
    _gate_result(gate_pass,
        f"Macro risk {macro_risk:.0f} — {'macro backdrop supportive' if gate_pass else 'macro headwinds — reduce cyclical exposure'}.")
    return macro


# ══════════════════════════════════════════════════════════════
# STAGE 2 — SECTOR SCREENER
# ══════════════════════════════════════════════════════════════

async def run_stage2_sector(macro_results: dict, universe_cfg: dict) -> dict:
    _stage_rule(2, f"SECTOR OVERALL  ·  {universe_cfg['display_name']}")
    console.print(f"  [{DIM}]Momentum  ·  Relative Strength  ·  Breadth  ·  Volume Flow  ·  Macro Alignment[/{DIM}]\n")

    with console.status(f"[{DIM}]Scanning {universe_cfg['display_name']} sector universe...[/{DIM}]", spinner="dots"):
        sector = run_sector_screener(
            macro_results=macro_results,
            custom_universe=universe_cfg["universe"],
            benchmark_ticker=universe_cfg["benchmark"],
        )

    ranked = sector["ranked_sectors"]

    # ── Headline ─────────────────────────────────────────────
    top = sector["top_sectors"]
    console.print(Columns([
        _kpi("ROTATION PHASE",  sector["sector_rotation"],  "medium_purple1"),
        _kpi("TOP SECTORS",     " · ".join(top) if top else "NONE", "bright_green"),
        _kpi("SECTOR GATE",     "OPEN" if sector["sector_gate"] else "CLOSED",
             "bright_green" if sector["sector_gate"] else "red1"),
    ], equal=False, expand=False))
    console.print()

    # ── Ranked sector table ───────────────────────────────────
    t = Table(box=None, show_header=True, header_style=f"bold {DIM}",
              padding=(0, 1), show_edge=False)
    t.add_column("Rank", style=DIM, width=5)
    t.add_column("Sector",       style="medium_purple1", width=18)
    t.add_column("Score",        width=6, justify="right")
    t.add_column("Bar",          width=16, no_wrap=True)
    t.add_column("20d Mom",      width=10, justify="right")
    t.add_column("RS vs Index",  width=12, justify="right")
    t.add_column("Breadth",      width=10, justify="right")
    t.add_column("Vol Flow",     width=10, justify="right")
    t.add_column("Macro Adj",    width=10, justify="right")
    t.add_column("Signal",       width=22)

    for i, s in enumerate(ranked, 1):
        sc   = s["sector_score"]
        sig  = s["signal"]
        mom  = s["mom_20d_pct"]
        rs   = s["rs_vs_index"]
        br   = s["breadth_pct"]
        vf   = s["volume_flow"]
        adj  = s["macro_adj"]
        gate = s["gate_pass"]
        rank_str = f"[bright_green bold]{i}[/bright_green bold]" if gate else f"[{DIM}]{i}[/{DIM}]"
        mc   = "bright_green" if mom > 0 else "red1"
        rc   = "bright_green" if rs > 0 else "red1"
        ac   = "bright_green" if adj > 0 else "red1" if adj < 0 else DIM
        t.add_row(
            rank_str,
            f"[bold white]{s['sector']}[/bold white]" if gate else f"[{DIM}]{s['sector']}[/{DIM}]",
            f"[{_risk_color(100-sc)} bold]{sc:.0f}[/{_risk_color(100-sc)} bold]",
            _mini_bar(sc, 14),
            f"[{mc}]{mom:+.2f}%[/{mc}]",
            f"[{rc}]{rs:+.2f}%[/{rc}]",
            f"{br:.0f}%",
            f"{vf:+.3f}",
            f"[{ac}]{adj:+d}[/{ac}]",
            f"[{_signal_color(sig)}]{sig}[/{_signal_color(sig)}]",
        )

    console.print(t)
    console.print()

    gate_pass = sector["sector_gate"]
    _gate_result(gate_pass,
        f"{'At least one sector passes' if gate_pass else 'No sectors pass minimum score — consider waiting'}.")
    return sector


# ══════════════════════════════════════════════════════════════
# STAGE 3 — STOCK FILTERING
# ══════════════════════════════════════════════════════════════

async def run_stage3_stock(ticker: str, market_data: dict,
                            composite_risk: float,
                            macro_results: dict,
                            universe: dict = None) -> dict:
    _stage_rule(3, f"STOCK FILTERING  ·  {ticker.upper()}")
    console.print(f"  [{DIM}]ROIC/WACC  ·  Altman Z  ·  Sloan  ·  FCF Quality  ·  CVaR  ·  Sortino  ·  Alpha Score[/{DIM}]\n")

    stock   = market_data["raw_stock_obj"]
    returns = market_data["returns"]

    # ── Sector lookup ─────────────────────────────────────────
    sector_name = get_sector_for_ticker(ticker, universe=universe)
    sector_adj  = macro_results.get("sector_adjustments", {}).get(sector_name, 0)

    # ── All calculations ──────────────────────────────────────
    roic      = calculate_roic(stock.financials, stock.balance_sheet)
    wacc      = calculate_wacc(stock.info, stock.financials, stock.balance_sheet, stock.cashflow)
    s_ratio   = calculate_sloan_ratio(stock.financials, stock.cashflow, stock.balance_sheet)
    fcf_q     = calculate_fcf_quality(stock.financials, stock.cashflow)
    z_score   = calculate_altman_z(stock.financials, stock.balance_sheet, stock.info)
    ccc_val   = calculate_ccc(stock.financials, stock.balance_sheet)
    a_turn    = calculate_asset_turnover(stock.financials, stock.balance_sheet)
    cvar      = calculate_cvar_95(returns)
    sortino   = calculate_rolling_sortino(returns)
    beta      = stock.info.get("beta", 1.0) or 1.0

    alpha = generate_alpha_score(
        roic=roic, wacc=wacc, sloan=s_ratio, z_score=z_score,
        sortino=sortino, beta=beta, fcf_quality=fcf_q,
        composite_risk=composite_risk, sector_macro_adj=sector_adj,
    )

    moat_spread  = roic - wacc
    spread_color = "bright_green" if moat_spread > 0 else "red1"

    # ── Row 1: Moat ───────────────────────────────────────────
    console.print(f"  [{DIM}]Moat & Alpha[/{DIM}]")
    console.print(Columns([
        _kpi("ROIC",        roic,       "steel_blue1"),
        _kpi("WACC",        wacc,       "yellow3"),
        _kpi("MOAT SPREAD", moat_spread, spread_color),
        _kpi("ALPHA SCORE", f"{alpha:.0f}/100",
             "bright_green" if alpha >= 60 else "yellow3" if alpha >= 40 else "red1"),
        _kpi("SECTOR",      sector_name, "medium_purple1"),
        _kpi("MACRO ADJ",   f"{sector_adj:+d} pts",
             "bright_green" if sector_adj > 0 else "red1" if sector_adj < 0 else DIM),
    ], equal=False, expand=False))
    console.print()

    # ── Row 2: Quality ────────────────────────────────────────
    console.print(f"  [{DIM}]Earnings Quality & Survival[/{DIM}]")
    console.print(Columns([
        _kpi("SLOAN RATIO",  s_ratio,
             "bright_green" if abs(s_ratio) < 0.05 else "yellow3" if abs(s_ratio) < 0.10 else "red1"),
        _kpi("FCF QUALITY",  fcf_q,
             "bright_green" if fcf_q > 0.6 else "yellow3" if fcf_q > 0.3 else "red1"),
        _kpi("ALTMAN Z",     z_score,
             "bright_green" if z_score > 2.99 else "yellow3" if z_score > 1.81 else "red1"),
        _kpi("BETA",         f"{beta:.2f}",
             "bright_green" if beta < 1.0 else "yellow3" if beta < 1.5 else "red1"),
    ], equal=False, expand=False))
    console.print()

    # ── Row 3: Risk ───────────────────────────────────────────
    console.print(f"  [{DIM}]Risk & Efficiency[/{DIM}]")
    console.print(Columns([
        _kpi("CVaR 95%",     cvar,     "red1"),
        _kpi("SORTINO",      sortino,
             "bright_green" if sortino > 1.5 else "yellow3" if sortino > 0.5 else "red1"),
        _kpi("ASSET TURN.",  a_turn,   "steel_blue1"),
        _kpi("CASH CYCLE",   f"{ccc_val:.0f}d", "steel_blue1"),
    ], equal=False, expand=False))
    console.print()

    # ── Alpha score breakdown bar ─────────────────────────────
    alpha_col = "bright_green" if alpha >= 60 else "yellow3" if alpha >= 40 else "red1"
    console.print(f"  [{DIM}]Alpha score breakdown[/{DIM}]  {_bar(alpha, 30)}  [{alpha_col} bold]{alpha:.0f}[/{alpha_col} bold]")
    console.print()

    # ── Z-score zone label ────────────────────────────────────
    z_label = ("SAFE ZONE (>2.99)" if z_score > 2.99
               else "GREY ZONE (1.81–2.99)" if z_score > 1.81
               else "DISTRESS ZONE (<1.81)")
    z_col   = "bright_green" if z_score > 2.99 else "yellow3" if z_score > 1.81 else "red1"
    console.print(f"  [{DIM}]Altman Z interpretation:[/{DIM}]  [{z_col}]{z_label}[/{z_col}]")
    console.print()

    gate_pass = alpha >= 50 and z_score > 1.81
    _gate_result(gate_pass,
        f"Alpha {alpha:.0f}/100, Z-Score {z_score:.2f} — {'passes screening filters' if gate_pass else 'does NOT pass minimum quality filters'}.")

    return {
        "roic": roic, "wacc": wacc, "moat_spread": moat_spread,
        "sloan": s_ratio, "fcf_quality": fcf_q, "altman_z": z_score,
        "beta": beta, "cvar": cvar, "sortino": sortino,
        "asset_turnover": a_turn, "ccc": ccc_val,
        "alpha": alpha, "sector": sector_name, "sector_adj": sector_adj,
        "gate_pass": gate_pass,
    }


# ══════════════════════════════════════════════════════════════
# STAGE 4 — TECHNICAL INDICATOR
# ══════════════════════════════════════════════════════════════

async def run_stage4_technical(ticker: str, composite_risk: float) -> TechnicalSignal:
    _stage_rule(4, f"TECHNICAL INDICATOR  ·  {ticker.upper()}")
    console.print(f"  [{DIM}]Adaptive strategy selection  ·  ATR-based TP/SL  ·  Regime-fit optimiser[/{DIM}]\n")

    with console.status(f"[{DIM}]Running strategy optimiser on {ticker}...[/{DIM}]", spinner="dots"):
        sig = run_technical_analysis(ticker, composite_risk=composite_risk)

    regime = sig.indicators.get("price_regime", "N/A")
    adx    = sig.indicators.get("adx", 0)
    opt    = sig.indicators.get("optimisation", {})
    sharpe_scores = opt.get("sharpe_scores", {})

    # ── Headline ─────────────────────────────────────────────
    strat_col = {"MOMENTUM": "orange1", "MEAN_REVERSION": "steel_blue1", "BREAKOUT": "bright_green"}.get(sig.strategy, "white")
    console.print(Columns([
        _kpi("STRATEGY",       sig.strategy,           strat_col),
        _kpi("PRICE REGIME",   regime,                 "white"),
        _kpi("ADX",            f"{adx:.1f}",           "bright_green" if adx > 25 else "yellow3"),
        _kpi("SIGNAL STRENGTH",f"{sig.signal_strength}/100",
             "bright_green" if sig.signal_strength >= 70 else "yellow3" if sig.signal_strength >= 40 else "red1"),
    ], equal=False, expand=False))
    console.print()

    # ── Trade setup panel ─────────────────────────────────────
    rr_col = "bright_green" if sig.rr_ratio >= 2 else "yellow3" if sig.rr_ratio >= 1.5 else "red1"
    console.print(Columns([
        _kpi("ENTRY PRICE",  f"{sig.entry_price:.4f}",  "white"),
        _kpi("TAKE PROFIT",  f"{sig.tp_price:.4f}",     "bright_green"),
        _kpi("STOP LOSS",    f"{sig.sl_price:.4f}",     "red1"),
        _kpi("R:R RATIO",    f"1 : {sig.rr_ratio:.2f}", rr_col),
        _kpi("ATR-14",       f"{sig.atr_14:.4f}",       DIM),
    ], equal=False, expand=False))
    console.print()

    # ── Strategy optimiser Sharpe scores ─────────────────────
    if sharpe_scores:
        console.print(f"  [{DIM}]Strategy Sharpe scores (60-day rolling simulation + regime-fit bonus)[/{DIM}]")
        t = Table(box=None, show_header=False, padding=(0, 2), show_edge=False)
        t.add_column("", style=DIM, width=20)
        t.add_column("", width=40)
        t.add_column("", width=10, justify="right")
        for strat, sharpe in sorted(sharpe_scores.items(), key=lambda x: -x[1]):
            is_selected = strat == sig.strategy
            scol = strat_col if is_selected else DIM
            bar_val = max(0, min(100, (sharpe + 1) * 50))   # map ~[-1,1] to [0,100]
            sel_tag = f" ← [bold {strat_col}]SELECTED[/bold {strat_col}]" if is_selected else ""
            t.add_row(
                f"[{scol}]{strat}[/{scol}]",
                _bar(bar_val, 25),
                f"[{scol}]{sharpe:.3f}[/{scol}]{sel_tag}",
            )
        console.print(t)
        console.print()

    # ── Regime fit note ───────────────────────────────────────
    console.print(f"  [{DIM}]Regime fit:[/{DIM}]  [white]{sig.regime_fit}[/white]")
    if sig.notes:
        note_col = "yellow3" if "WARNING" in sig.notes.upper() else DIM
        console.print(f"  [{DIM}]Notes:[/{DIM}]  [{note_col}]{sig.notes}[/{note_col}]")
    console.print()

    gate_pass = sig.rr_ratio >= 1.5 and sig.signal_strength >= 40
    _gate_result(gate_pass,
        f"R:R {sig.rr_ratio:.2f}, signal strength {sig.signal_strength} — {'valid setup' if gate_pass else 'setup does not meet minimum criteria'}.")
    return sig


# ══════════════════════════════════════════════════════════════
# STAGE 5 — RISK MANAGEMENT
# ══════════════════════════════════════════════════════════════

async def run_stage5_risk(ticker: str,
                           sig: TechnicalSignal,
                           composite_risk: float,
                           portfolio_value: float,
                           win_rate: float = 0.50) -> RiskDecision:
    _stage_rule(5, "RISK MANAGEMENT")
    console.print(f"  [{DIM}]Half-Kelly sizing  ·  Regime scaling  ·  Portfolio heat  ·  Correlation  ·  CVaR budget[/{DIM}]\n")

    with console.status(f"[{DIM}]Running risk engine...[/{DIM}]", spinner="dots"):
        decision = make_risk_decision(
            ticker          = ticker,
            entry_price     = sig.entry_price,
            sl_price        = sig.sl_price,
            tp_price        = sig.tp_price,
            rr_ratio        = sig.rr_ratio,
            portfolio_value = portfolio_value,
            composite_risk  = composite_risk,
            win_rate        = win_rate,
            open_positions  = [],
            open_tickers    = [],
        )

    v_col = _verdict_color(decision.verdict)

    # ── Headline ─────────────────────────────────────────────
    console.print(Columns([
        _kpi("VERDICT",        decision.verdict,              v_col),
        _kpi("POSITION SIZE",  f"{decision.position_size_shares} shares",  v_col),
        _kpi("EXPOSURE",       f"{decision.position_size_pct:.2f}%",       v_col),
        _kpi("RISK AMOUNT",    f"฿{decision.risk_amount:,.0f}",            "red1"),
    ], equal=False, expand=False))
    console.print()

    # ── Sizing mechanics ──────────────────────────────────────
    console.print(Columns([
        _kpi("KELLY FRACTION",  f"{decision.kelly_fraction*100:.3f}%",  "white"),
        _kpi("REGIME SCALE",    f"{decision.regime_scale*100:.0f}%",
             "bright_green" if decision.regime_scale >= 0.8 else
             "yellow3"      if decision.regime_scale >= 0.5 else "red1"),
        _kpi("COMPOSITE RISK",  f"{composite_risk:.0f}/100",            _risk_color(composite_risk)),
        _kpi("WIN RATE",        f"{win_rate*100:.0f}%",                 DIM),
    ], equal=False, expand=False))
    console.print()

    # ── Heat bar ─────────────────────────────────────────────
    heat_pct = (decision.risk_amount / portfolio_value * 100) if portfolio_value > 0 else 0
    heat_of_limit = heat_pct / (MAX_PORTFOLIO_HEAT * 100) * 100
    console.print(f"  [{DIM}]Portfolio heat from this trade:[/{DIM}]  "
                  f"{_bar(heat_of_limit, 20)}  "
                  f"[{'red1' if heat_of_limit > 80 else 'yellow3' if heat_of_limit > 50 else 'bright_green'}]"
                  f"{heat_pct:.3f}% at risk[/]  [{DIM}](limit {MAX_PORTFOLIO_HEAT*100:.0f}%)[/{DIM}]")
    console.print()

    # ── Flags ─────────────────────────────────────────────────
    if decision.flags:
        console.print(f"  [yellow3]Risk flags:[/yellow3]")
        for flag in decision.flags:
            console.print(f"  [yellow3]⚠[/yellow3]  [{DIM}]{flag}[/{DIM}]")
        console.print()

    # ── Notes ─────────────────────────────────────────────────
    if decision.notes:
        console.print(f"  [{DIM}]{decision.notes}[/{DIM}]")
        console.print()

    gate_pass = decision.verdict != "REJECTED"
    _gate_result(gate_pass,
        f"Risk decision: {decision.verdict} — "
        f"{f'{decision.position_size_shares} shares at ฿{decision.risk_amount:,.0f} at risk' if gate_pass else 'trade blocked by risk engine'}.")
    return decision


# ══════════════════════════════════════════════════════════════
# STAGE 6 — AGENT COMMITTEE VERDICT
# ══════════════════════════════════════════════════════════════

async def run_stage6_agents(ticker: str,
                             market_data:   dict,
                             stock_data:    dict,
                             tech_sig:      "TechnicalSignal",
                             risk_decision: "RiskDecision",
                             sector_data:   dict,
                             macro_results: dict,
                             composite_risk: float) -> dict:
    """
    Assemble the full metadata snapshot from all upstream stages and
    invoke the LangGraph committee pipeline.

    Passes every pre-computed score as metadata so agents read once —
    no re-fetching, no re-calculation inside the graph.
    """
    _stage_rule(6, "AGENT COMMITTEE")
    console.print(f"  [{DIM}]Multi-agent qualitative consensus  ·  LangGraph pipeline[/{DIM}]\n")

    # ── Find which sector this ticker belongs to ──────────────
    sector_name  = stock_data.get("sector", "UNKNOWN")
    sector_score = next(
        (s["sector_score"] for s in sector_data.get("ranked_sectors", [])
         if s["sector"] == sector_name),
        50.0,
    )

    # ── Build full metadata snapshot ─────────────────────────
    metadata = {
        # Stage 0 — Market Fragility
        "composite_risk":    composite_risk,

        # Stage 1 — Global Macro
        "macro_regime":      macro_results.get("macro_regime",     "NEUTRAL_GROWTH"),
        "macro_bias":        macro_results.get("macro_bias_summary", "NEUTRAL"),

        # Stage 2 — Sector
        "sector":            sector_name,
        "sector_score":      sector_score,
        "sector_rotation":   sector_data.get("sector_rotation",    "TRANSITION_MIXED"),

        # Stage 3 — Stock Fundamentals
        "alpha_score":       stock_data.get("alpha",           0.0),
        "roic":              stock_data.get("roic",            0.0),
        "wacc":              stock_data.get("wacc",            0.0),
        "moat_spread":       stock_data.get("moat_spread",     0.0),
        "sloan_ratio":       stock_data.get("sloan",           0.0),
        "fcf_quality":       stock_data.get("fcf_quality",     0.0),
        "altman_z":          stock_data.get("altman_z",        0.0),
        "beta":              stock_data.get("beta",            1.0),
        "cvar":              stock_data.get("cvar",            0.0),
        "sortino":           stock_data.get("sortino",         0.0),

        # Stage 4 — Technical
        "technical_strategy": tech_sig.strategy,
        "entry_price":        tech_sig.entry_price,
        "tp_price":           tech_sig.tp_price,
        "sl_price":           tech_sig.sl_price,
        "rr_ratio":           tech_sig.rr_ratio,
        "signal_strength":    tech_sig.signal_strength,

        # Stage 5 — Risk Management
        "risk_verdict":      risk_decision.verdict,
        "position_shares":   risk_decision.position_size_shares,
        "position_pct":      risk_decision.position_size_pct,
        "risk_amount":       risk_decision.risk_amount,
        "regime_scale":      risk_decision.regime_scale,
        "kelly_fraction":    risk_decision.kelly_fraction,
        "risk_flags":        risk_decision.flags,
    }

    with console.status(f"[{DIM}]Convening agent committee for {ticker}...[/{DIM}]", spinner="bouncingBar"):
        result = await hedge_fund_app.ainvoke({
            "ticker":         ticker,
            "data":           market_data,
            "analysis_steps": [],
            "agent_scores":   [],
            "risk_flags":     [],
            "metadata":       metadata,
            "decision":       "HOLD",   # default — overwritten by portfolio_manager_node
        })

    # ── Agent conviction score summary ───────────────────────
    agent_scores = result.get("agent_scores", [])
    if agent_scores:
        score_parts = []
        for entry in agent_scores:
            sc     = entry.get("score",  50)
            stance = entry.get("stance", "NEUTRAL")
            agent  = entry.get("agent",  "?")
            sc_col = "bright_green" if sc >= 65 else "red1" if sc <= 35 else "yellow3"
            score_parts.append(
                f"[{sc_col}]{agent.replace('Agent','').replace('Manager','')} {sc:.0f}[/{sc_col}]"
            )
        console.print("  " + "   ".join(score_parts))
        console.print()

    # ── Reasoning audit table ─────────────────────────────────
    t = Table(box=None, show_header=True, header_style=f"bold {DIM}",
              padding=(0, 1), show_edge=False)
    t.add_column("Agent",       style="bright_cyan", width=20)
    t.add_column("Stance",      width=10)
    t.add_column("Reasoning",   style="white")

    # Build stance lookup from agent_scores
    stance_map = {e.get("agent", ""): e.get("stance", "NEUTRAL") for e in agent_scores}

    for step in result.get("analysis_steps", []):
        if ":" in step:
            agent, reason = step.split(":", 1)
            agent  = agent.strip()
            stance = stance_map.get(agent, "")
            st_col = "bright_green" if stance == "BULLISH" else "red1" if stance == "BEARISH" else "yellow3"
            stance_str = f"[{st_col}]{stance}[/{st_col}]" if stance else ""
            t.add_row(agent, stance_str, reason.strip())
        else:
            t.add_row("System", "", step)

    console.print(t)

    # ── Risk flags raised by committee ───────────────────────
    all_flags = result.get("risk_flags", [])
    if all_flags:
        console.print()
        for flag in all_flags:
            console.print(f"  [yellow3]⚠[/yellow3]  [{DIM}]{flag}[/{DIM}]")

    console.print()
    return result


# ══════════════════════════════════════════════════════════════
# FINAL VERDICT PANEL
# ══════════════════════════════════════════════════════════════

def render_final_verdict(ticker: str,
                          agent_result: dict,
                          risk_decision: RiskDecision,
                          technical_sig: TechnicalSignal,
                          stock_data: dict) -> None:
    decision  = agent_result.get("decision", "HOLD")
    d_col     = _verdict_color(decision)
    r_col     = _verdict_color(risk_decision.verdict)
    alpha     = stock_data.get("alpha", 0)
    z_score   = stock_data.get("altman_z", 0)

    console.print()
    console.print(Rule(style=f"{d_col} dim"))

    # ── Trade summary ─────────────────────────────────────────
    summary_lines = [
        f"[bold {d_col}]  FINAL DECISION:  {decision}[/bold {d_col}]",
        "",
        f"  [{DIM}]Entry[/{DIM}]  [bold white]{technical_sig.entry_price:.4f}[/bold white]"
        f"   [{DIM}]TP[/{DIM}]  [bold bright_green]{technical_sig.tp_price:.4f}[/bold bright_green]"
        f"   [{DIM}]SL[/{DIM}]  [bold red1]{technical_sig.sl_price:.4f}[/bold red1]"
        f"   [{DIM}]R:R[/{DIM}]  [bold {d_col}]1:{technical_sig.rr_ratio:.2f}[/bold {d_col}]",
        "",
        f"  [{DIM}]Size[/{DIM}]  [bold {r_col}]{risk_decision.position_size_shares} shares[/bold {r_col}]"
        f"   [{DIM}]Exposure[/{DIM}]  [bold {r_col}]{risk_decision.position_size_pct:.2f}%[/bold {r_col}]"
        f"   [{DIM}]At risk[/{DIM}]  [bold red1]฿{risk_decision.risk_amount:,.0f}[/bold red1]"
        f"   [{DIM}]Regime scale[/{DIM}]  [bold white]{risk_decision.regime_scale*100:.0f}%[/bold white]",
        "",
        f"  [{DIM}]Strategy[/{DIM}]  [white]{technical_sig.strategy}[/white]"
        f"   [{DIM}]Alpha[/{DIM}]  [bold {'bright_green' if alpha >= 60 else 'yellow3'}]{alpha:.0f}/100[/bold {'bright_green' if alpha >= 60 else 'yellow3'}]"
        f"   [{DIM}]Altman Z[/{DIM}]  [bold {'bright_green' if z_score > 2.99 else 'yellow3' if z_score > 1.81 else 'red1'}]{z_score:.2f}[/bold {'bright_green' if z_score > 2.99 else 'yellow3' if z_score > 1.81 else 'red1'}]"
        f"   [{DIM}]Risk verdict[/{DIM}]  [bold {r_col}]{risk_decision.verdict}[/bold {r_col}]",
    ]

    console.print(Panel(
        "\n".join(summary_lines),
        title=f"[bold {d_col}]  {ticker.upper()}  ·  PORTFOLIO MANAGER VERDICT  [/bold {d_col}]",
        title_align="center",
        border_style=d_col,
        padding=(1, 2),
    ))
    console.print(Rule(style=f"{d_col} dim"))
    console.print()


# ══════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════

async def run_analysis_cli():
    console.clear()

    # ── Banner ────────────────────────────────────────────────
    console.print()
    console.print(Align.center(Panel(
        f"[bold {ACCENT}]ALPHA-STREAM ARCHITECT[/bold {ACCENT}]\n"
        f"[{DIM}]Quantitative Terminal  ·  Institutional Five-Stage Pipeline[/{DIM}]",
        border_style=ACCENT,
        padding=(1, 6),
        expand=False,
    )))
    console.print()

    # ── Universe selection ────────────────────────────────────
    universe_key = await questionary.select(
        "Select universe:",
        choices=[
            questionary.Choice("SET100 Thailand",    value="SET100"),
            questionary.Choice("Personal Watchlist", value="WATCHLIST"),
        ],
    ).ask_async()
    if not universe_key:
        return
    universe_cfg = UNIVERSE_REGISTRY[universe_key]

    # ── User input ────────────────────────────────────────────
    ticker = await questionary.text(
        "Ticker symbol:",
        instruction="(e.g. CPALL.BK  BBL.BK  KBANK.BK)",
    ).ask_async()
    if not ticker:
        return
    ticker = ticker.strip().upper()

    portfolio_str = await questionary.text(
        "Portfolio value (THB):",
        default="1000000",
    ).ask_async()
    try:
        portfolio_value = float(portfolio_str.replace(",", "").replace("฿", ""))
    except Exception:
        portfolio_value = 1_000_000.0

    win_rate_str = await questionary.text(
        "System win rate [0–1]:",
        default="0.50",
    ).ask_async()
    try:
        win_rate = max(0.1, min(0.9, float(win_rate_str)))
    except Exception:
        win_rate = 0.50

    console.print()

    # ══════════════════════════════════════════════════════════
    # PIPELINE EXECUTION
    # ══════════════════════════════════════════════════════════

    # Stage 0: Market Fragility
    with console.status(f"[{DIM}]Fetching SPX data...[/{DIM}]", spinner="dots"):
        spx_data = await fetch_all_data("^GSPC")
    fragility = await run_stage0_fragility(spx_data)
    composite_risk = fragility["composite_risk"]

    # Stage 1: Global Macro
    macro = await run_stage1_macro()

    # Stage 2: Sector Screener
    sector = await run_stage2_sector(macro, universe_cfg)

    # Gate: warn if sector gate closed but let user continue
    if not sector["sector_gate"]:
        console.print(f"  [yellow3]⚠  No sectors pass minimum score. Proceeding with caution.[/yellow3]\n")

    # Stage 3: Stock Filtering
    with console.status(f"[{DIM}]Fetching {ticker} fundamentals...[/{DIM}]", spinner="dots"):
        market_data = await fetch_all_data(ticker)

    stock_data = await run_stage3_stock(ticker, market_data, composite_risk, macro,
                                        universe=universe_cfg["universe"])

    if not stock_data["gate_pass"]:
        console.print(f"  [yellow3]⚠  Stock did not pass quality filters. Continuing with reduced confidence.[/yellow3]\n")

    # Stage 4: Technical
    try:
        tech_sig = await run_stage4_technical(ticker, composite_risk)
    except Exception as e:
        console.print(f"  [red1]Technical analysis failed: {e}[/red1]")
        return

    # Stage 5: Risk Management
    risk_decision = await run_stage5_risk(
        ticker=ticker, sig=tech_sig,
        composite_risk=composite_risk,
        portfolio_value=portfolio_value,
        win_rate=win_rate,
    )

    # Stage 6: Agent Committee
    agent_result = await run_stage6_agents(
        ticker         = ticker,
        market_data    = market_data,
        stock_data     = stock_data,
        tech_sig       = tech_sig,
        risk_decision  = risk_decision,
        sector_data    = sector,
        macro_results  = macro,
        composite_risk = composite_risk,
    )

    # Final Verdict
    render_final_verdict(
        ticker=ticker,
        agent_result=agent_result,
        risk_decision=risk_decision,
        technical_sig=tech_sig,
        stock_data=stock_data,
    )


if __name__ == "__main__":
    asyncio.run(run_analysis_cli())