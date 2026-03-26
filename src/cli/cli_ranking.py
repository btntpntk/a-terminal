"""
src/cli/cli_ranking.py
Universe Ranking Scanner

Scans ALL tickers in the selected universe through Stages 0–4 in parallel
and presents a ranked leaderboard table sorted by composite score.

Stage 6 (LangGraph agent committee) is intentionally skipped to keep
batch analysis fast. For deep per-stock analysis, use cli4.py.

Composite rank score = 45% Alpha + 30% Signal Strength + 15% Sector Score + 10% R:R
"""

import asyncio
import questionary
import yfinance as yf
import pandas as pd
import numpy as np
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich.rule import Rule
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn, TaskProgressColumn
from rich.align import Align
from rich import box

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
from src.agents.sector_screener import (
    run_sector_screener,
    get_sector_for_ticker,
    UNIVERSE_REGISTRY,
)

# ── Stage 3: Financial metrics ────────────────────────────────
from src.agents.calculator import (
    calculate_sloan_ratio,
    calculate_cvar_95,
    calculate_wacc,
    calculate_roic,
    calculate_rolling_sortino,
    calculate_asset_turnover,
    calculate_altman_z,
    calculate_ccc,
    calculate_fcf_quality,
    generate_alpha_score,
)

# ── Stage 4: Technical ────────────────────────────────────────
from src.agents.technical import run_technical_analysis


console = Console()

# ══════════════════════════════════════════════════════════════
# THEME
# ══════════════════════════════════════════════════════════════

ACCENT    = "bright_cyan"
DIM       = "grey50"
SEPARATOR = "grey23"

STAGE_COLORS = {0: "bright_cyan", 1: "gold1", 2: "medium_purple1", 3: "steel_blue1"}
STRAT_COLORS = {"MOMENTUM": "orange1", "MEAN_REVERSION": "steel_blue1", "BREAKOUT": "bright_green"}


def _risk_color(score: float) -> str:
    if score < 30: return "bright_green"
    if score < 50: return "green3"
    if score < 65: return "yellow3"
    if score < 80: return "orange3"
    return "red1"


def _signal_color(signal: str) -> str:
    bullish = {"BULL", "STEEP_GROWTH", "TIGHT_BENIGN", "BROAD_PARTICIPATION",
               "EQUAL_WEIGHT_LEADING", "COMPLACENCY", "STEEP_CONTANGO", "RISK_ON", "EXPANSION"}
    bearish = {"BEAR", "INVERTED", "ACUTE_CRISIS", "BREADTH_COLLAPSE",
               "EXTREME_CONCENTRATION", "PANIC", "BACKWARDATION", "CRISIS", "DESTRUCTION"}
    s = signal.upper()
    if any(k in s for k in bullish): return "bright_green"
    if any(k in s for k in bearish): return "red1"
    return "yellow3"


def _mini_bar(score: float, width: int = 10) -> str:
    filled = int(max(0.0, min(100.0, score)) / 100 * width)
    empty  = width - filled
    col    = _risk_color(score)
    return f"[{col}]{'█' * filled}[/{col}][{SEPARATOR}]{'░' * empty}[/{SEPARATOR}]"


def _kpi(title: str, value, color: str = "white") -> Panel:
    if isinstance(value, float):
        txt = f"{value:+.3f}" if value < 0 or "+" in f"{value:+.3f}" else f"{value:.3f}"
    else:
        txt = str(value)
    return Panel(
        f"[bold {color}]{txt}[/bold {color}]",
        title=f"[{DIM}]{title}[/{DIM}]",
        title_align="left",
        border_style=SEPARATOR,
        padding=(0, 1),
        expand=False,
    )


def _section(n: int, title: str) -> None:
    col = STAGE_COLORS.get(n, "white")
    console.print()
    console.print(Rule(
        f"[bold {col}]  STAGE {n}  ·  {title}  [/bold {col}]",
        style=f"{col} dim",
    ))
    console.print()


def _regime_scale(composite_risk: float) -> str:
    if composite_risk <= 30: return "100% — Full Kelly"
    if composite_risk <= 45: return "80%"
    if composite_risk <= 60: return "60%"
    if composite_risk <= 74: return "40%"
    return "25% — Capital Preservation"


# ══════════════════════════════════════════════════════════════
# STAGE 0  —  sync helper (runs in thread pool)
# ══════════════════════════════════════════════════════════════

def _sync_stage0(spx_prices: dict) -> tuple:
    """All Stage 0 calculations are synchronous — run inside asyncio.to_thread."""
    dma_r  = calculate_spx_200dma_buffer(spx_prices)
    yc_r   = calculate_yield_curve_spread()
    hy_r   = calculate_hy_credit_spread()
    brd_r  = calculate_breadth_above_50dma()
    rsp_r  = calculate_rsp_spy_ratio()
    vix_r  = calculate_vix_level()
    term_r = calculate_vix_term_structure()

    reg_sc = [dma_r.get("risk_score", 50), yc_r.get("risk_score", 50), hy_r.get("risk_score", 50)]
    fra_sc = [brd_r.get("risk_score", 50), rsp_r.get("risk_score", 50)]
    tri_sc = [vix_r.get("risk_score", 50), term_r.get("risk_score", 50)]

    composite  = calculate_composite_risk(reg_sc, fra_sc, tri_sc)
    confidence = calculate_confidence(reg_sc + fra_sc + tri_sc)

    return (
        composite["composite_risk"],
        composite["regime_label"],
        composite["layer_scores"],
        confidence["confidence"],
        confidence["signal"],
        {
            "dma":    dma_r,  "yield_curve": yc_r, "hy":   hy_r,
            "breadth": brd_r, "rsp_spy":     rsp_r,
            "vix":    vix_r,  "term":        term_r,
        },
    )


def _fetch_spx_sync() -> dict:
    """Fetch SPX data synchronously for stage 0."""
    stock   = yf.Ticker("^GSPC")
    history = stock.history(period="1y")
    returns = history["Close"].pct_change().dropna()
    return {"raw_stock_obj": stock, "prices": history, "returns": returns, "info": stock.info}


# ══════════════════════════════════════════════════════════════
# PER-TICKER ANALYSIS  (fully synchronous — called via to_thread)
# ══════════════════════════════════════════════════════════════

def _sync_analyze_ticker(
    ticker: str,
    composite_risk: float,
    macro_results: dict,
    sector_scores: dict,
    universe: dict,
) -> dict:
    """
    Runs Stage 3 (fundamentals) and Stage 4 (technical) for one ticker.
    Entirely synchronous — designed to run inside asyncio.to_thread.
    """
    try:
        # ── Data fetch ────────────────────────────────────────
        stock   = yf.Ticker(ticker)
        history = stock.history(period="1y")
        if history.empty:
            return {"ok": False, "ticker": ticker, "error": "No price history"}

        returns = history["Close"].pct_change().dropna()
        price   = float(history["Close"].iloc[-1])

        fin  = stock.financials
        bs   = stock.balance_sheet
        cf   = stock.cashflow
        info = stock.info

        # ── Stage 3: Fundamentals ─────────────────────────────
        sector_name  = get_sector_for_ticker(ticker, universe=universe)
        sector_adj   = macro_results.get("sector_adjustments", {}).get(sector_name, 0)
        sector_score = sector_scores.get(sector_name, 50.0)

        roic    = calculate_roic(fin, bs)
        wacc    = calculate_wacc(info, fin, bs, cf)
        sloan   = calculate_sloan_ratio(fin, cf, bs)
        fcf_q   = calculate_fcf_quality(fin, cf)
        z       = calculate_altman_z(fin, bs, info)
        cvar    = calculate_cvar_95(returns)
        sortino = calculate_rolling_sortino(returns)
        a_turn  = calculate_asset_turnover(fin, bs)
        ccc_val = calculate_ccc(fin, bs)
        beta    = float(info.get("beta", 1.0) or 1.0)

        alpha = generate_alpha_score(
            roic=roic, wacc=wacc, sloan=sloan, z_score=z,
            sortino=sortino, beta=beta, fcf_quality=fcf_q,
            composite_risk=composite_risk, sector_macro_adj=sector_adj,
        )

        gate3 = alpha >= 50 and z > 1.81

        # ── Stage 4: Technical ────────────────────────────────
        try:
            sig   = run_technical_analysis(ticker, composite_risk=composite_risk)
            gate4 = sig.rr_ratio >= 1.5 and sig.signal_strength >= 40
        except Exception:
            sig   = None
            gate4 = False

        rr_score  = min((sig.rr_ratio / 3.0) * 100, 100.0) if sig else 0.0
        ss_score  = float(sig.signal_strength) if sig else 0.0

        # ── Composite rank score (0–100) ──────────────────────
        rank_score = (
            alpha        * 0.45
            + ss_score   * 0.30
            + sector_score * 0.15
            + rr_score   * 0.10
        )

        return {
            "ok":           True,
            "ticker":       ticker,
            "sector":       sector_name,
            "price":        price,
            # Stage 3
            "alpha":        alpha,
            "roic":         roic,
            "wacc":         wacc,
            "moat":         roic - wacc,
            "z":            z,
            "sloan":        sloan,
            "fcf_q":        fcf_q,
            "beta":         beta,
            "cvar":         cvar,
            "sortino":      sortino,
            "a_turn":       a_turn,
            "ccc":          ccc_val,
            "sector_score": sector_score,
            "sector_adj":   sector_adj,
            # Stage 4
            "strategy":     sig.strategy      if sig else "N/A",
            "regime_fit":   sig.regime_fit    if sig else "N/A",
            "signal_str":   int(ss_score),
            "rr":           sig.rr_ratio      if sig else 0.0,
            "entry":        sig.entry_price   if sig else 0.0,
            "tp":           sig.tp_price      if sig else 0.0,
            "sl":           sig.sl_price      if sig else 0.0,
            "atr":          sig.atr_14        if sig else 0.0,
            # Gates & composite
            "gate3":        gate3,
            "gate4":        gate4,
            "rank_score":   rank_score,
        }

    except Exception as exc:
        return {"ok": False, "ticker": ticker, "error": str(exc)}


# ══════════════════════════════════════════════════════════════
# ASYNC WRAPPER  +  BATCH RUNNER
# ══════════════════════════════════════════════════════════════

async def _analyze_ticker_async(
    ticker: str,
    composite_risk: float,
    macro_results: dict,
    sector_scores: dict,
    universe: dict,
    sem: asyncio.Semaphore,
) -> dict:
    async with sem:
        return await asyncio.to_thread(
            _sync_analyze_ticker,
            ticker, composite_risk, macro_results, sector_scores, universe,
        )


async def scan_universe(
    universe: dict,
    composite_risk: float,
    macro_results: dict,
    sector_data: dict,
    concurrency: int = 8,
) -> tuple[list, list]:
    """
    Runs per-ticker analysis for every member in the universe concurrently.
    Returns (ok_rows_sorted_by_rank, err_rows).
    """
    tickers = list(dict.fromkeys(
        t for s in universe.values() for t in s["members"]
    ))
    sector_scores = {
        s["sector"]: s["sector_score"]
        for s in sector_data.get("ranked_sectors", [])
    }

    sem   = asyncio.Semaphore(concurrency)
    tasks = [
        asyncio.ensure_future(
            _analyze_ticker_async(
                ticker=t,
                composite_risk=composite_risk,
                macro_results=macro_results,
                sector_scores=sector_scores,
                universe=universe,
                sem=sem,
            )
        )
        for t in tickers
    ]

    results = []
    with Progress(
        SpinnerColumn(style=ACCENT),
        TextColumn(f"[{ACCENT}]{{task.description}}"),
        BarColumn(bar_width=28, style=SEPARATOR, complete_style=ACCENT),
        TaskProgressColumn(),
        TextColumn("[bold]{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as prog:
        task_id = prog.add_task("Initialising...", total=len(tasks))
        for coro in asyncio.as_completed(tasks):
            result = await coro
            results.append(result)
            prog.advance(task_id)
            lbl = result["ticker"] if result["ok"] else f"{result['ticker']} ✗"
            col = "bright_green" if (result.get("gate3") and result.get("gate4")) else \
                  "yellow3"      if (result.get("gate3") or result.get("gate4"))  else \
                  "red1"         if result["ok"] else DIM
            prog.update(task_id, description=f"[{col}]{lbl:12}[/{col}]  scanned")

    ok_rows  = sorted(
        [r for r in results if r["ok"]],
        key=lambda r: (-(r["gate3"] and r["gate4"]), -r["rank_score"]),
    )
    err_rows = [r for r in results if not r["ok"]]
    return ok_rows, err_rows


# ══════════════════════════════════════════════════════════════
# RANKING TABLE
# ══════════════════════════════════════════════════════════════

def render_ranking_table(
    rows: list,
    universe_name: str,
    composite_risk: float,
    macro_regime: str,
) -> None:
    console.print()
    console.print(Rule(
        f"[bold {ACCENT}]  UNIVERSE RANKING  ·  {universe_name}  [/bold {ACCENT}]",
        style=f"{ACCENT} dim",
    ))
    console.print()

    buy_count  = sum(1 for r in rows if r["gate3"] and r["gate4"])
    f3_only    = sum(1 for r in rows if r["gate3"] and not r["gate4"])
    f4_only    = sum(1 for r in rows if not r["gate3"] and r["gate4"])
    fail_count = len(rows) - buy_count - f3_only - f4_only

    # ── Summary KPIs ──────────────────────────────────────────
    console.print(Columns([
        _kpi("SCANNED",        len(rows),                 ACCENT),
        _kpi("BUY CANDIDATES", buy_count,                 "bright_green" if buy_count > 0 else "red1"),
        _kpi("FUND. ONLY",     f3_only,                   "yellow3"),
        _kpi("TECH. ONLY",     f4_only,                   "yellow3"),
        _kpi("FAILED BOTH",    fail_count,                "red1"),
        _kpi("REGIME RISK",    f"{composite_risk:.0f}/100", _risk_color(composite_risk)),
        _kpi("MACRO REGIME",   macro_regime,              _risk_color(composite_risk)),
    ], equal=False, expand=False))
    console.print()

    # ── Main table ────────────────────────────────────────────
    t = Table(
        box=box.SIMPLE_HEAD,
        show_header=True,
        header_style=f"bold {DIM}",
        padding=(0, 1),
        show_edge=False,
    )

    t.add_column("#",        style=DIM,              width=4,  justify="right")
    t.add_column("Ticker",                            width=12)
    t.add_column("Sector",   style="medium_purple1", width=16)
    t.add_column("Score",                             width=6,  justify="right")
    t.add_column("",                                  width=12, no_wrap=True)
    t.add_column("Alpha",                             width=6,  justify="right")
    t.add_column("Moat",                              width=8,  justify="right")
    t.add_column("Z",                                 width=6,  justify="right")
    t.add_column("Sloan",                             width=7,  justify="right")
    t.add_column("FCF",                               width=5,  justify="right")
    t.add_column("Sortino",                           width=7,  justify="right")
    t.add_column("β",                                 width=5,  justify="right")
    t.add_column("Strategy",                          width=14)
    t.add_column("SS",                                width=4,  justify="right")
    t.add_column("R:R",                               width=5,  justify="right")
    t.add_column("Entry",                             width=9,  justify="right")
    t.add_column("TP",                                width=9,  justify="right")
    t.add_column("SL",                                width=9,  justify="right")
    t.add_column("Gate",                              width=7,  justify="center")

    for i, r in enumerate(rows, 1):
        both = r["gate3"] and r["gate4"]
        f3   = r["gate3"]
        f4   = r["gate4"]

        if both:
            gate_str   = "[bold bright_green]  BUY [/bold bright_green]"
            ticker_str = f"[bold bright_green]{r['ticker']}[/bold bright_green]"
            rank_str   = f"[bold bright_green]{i}[/bold bright_green]"
        elif f3:
            gate_str   = "[yellow3] F✓ T✗[/yellow3]"
            ticker_str = f"[yellow3]{r['ticker']}[/yellow3]"
            rank_str   = f"[yellow3]{i}[/yellow3]"
        elif f4:
            gate_str   = "[yellow3] F✗ T✓[/yellow3]"
            ticker_str = f"[yellow3]{r['ticker']}[/yellow3]"
            rank_str   = f"[yellow3]{i}[/yellow3]"
        else:
            gate_str   = f"[{DIM}] FAIL[/{DIM}]"
            ticker_str = f"[{DIM}]{r['ticker']}[/{DIM}]"
            rank_str   = f"[{DIM}]{i}[/{DIM}]"

        sc     = r["rank_score"]
        alpha  = r["alpha"]
        moat   = r["moat"]
        z      = r["z"]
        sloan  = r["sloan"]
        fcf    = r["fcf_q"]
        sort_  = r["sortino"]
        beta_  = r["beta"]
        strat  = r["strategy"]
        ss     = r["signal_str"]
        rr     = r["rr"]
        entry  = r["entry"]
        tp     = r["tp"]
        sl     = r["sl"]

        sc_c   = _risk_color(100 - sc)
        al_c   = "bright_green" if alpha >= 60 else "yellow3" if alpha >= 40 else "red1"
        mo_c   = "bright_green" if moat > 0 else "red1"
        z_c    = "bright_green" if z > 2.99 else "yellow3" if z > 1.81 else "red1"
        sl_c   = "bright_green" if abs(sloan) < 0.05 else "yellow3" if abs(sloan) < 0.10 else "red1"
        fc_c   = "bright_green" if fcf > 0.6 else "yellow3" if fcf > 0.3 else "red1"
        so_c   = "bright_green" if sort_ > 1.5 else "yellow3" if sort_ > 0.5 else "red1"
        be_c   = "bright_green" if beta_ < 1.0 else "yellow3" if beta_ < 1.5 else "red1"
        st_c   = STRAT_COLORS.get(strat, DIM)
        ss_c   = "bright_green" if ss >= 70 else "yellow3" if ss >= 40 else "red1"
        rr_c   = "bright_green" if rr >= 2.0 else "yellow3" if rr >= 1.5 else "red1"

        t.add_row(
            rank_str,
            ticker_str,
            r["sector"],
            f"[{sc_c} bold]{sc:.0f}[/{sc_c} bold]",
            _mini_bar(sc, 10),
            f"[{al_c} bold]{alpha:.0f}[/{al_c} bold]",
            f"[{mo_c}]{moat:+.3f}[/{mo_c}]",
            f"[{z_c}]{z:.2f}[/{z_c}]",
            f"[{sl_c}]{sloan:+.3f}[/{sl_c}]",
            f"[{fc_c}]{fcf:.2f}[/{fc_c}]",
            f"[{so_c}]{sort_:.2f}[/{so_c}]",
            f"[{be_c}]{beta_:.2f}[/{be_c}]",
            f"[{st_c}]{strat[:13]}[/{st_c}]",
            f"[{ss_c}]{ss}[/{ss_c}]",
            f"[{rr_c}]{rr:.2f}[/{rr_c}]",
            f"[white]{entry:.3f}[/white]" if entry else f"[{DIM}]N/A[/{DIM}]",
            f"[bright_green]{tp:.3f}[/bright_green]" if tp else f"[{DIM}]N/A[/{DIM}]",
            f"[red1]{sl:.3f}[/red1]" if sl else f"[{DIM}]N/A[/{DIM}]",
            gate_str,
        )

    console.print(t)
    console.print()

    # ── Legend ────────────────────────────────────────────────
    console.print(
        f"  [{DIM}]Score = 45% Alpha + 30% Signal Strength + 15% Sector + 10% R:R   ·   [/{DIM}]"
        f"[bold bright_green]BUY[/bold bright_green] [{DIM}]= Fund ✓ & Tech ✓   [/{DIM}]"
        f"[yellow3]F✓ T✗[/yellow3] [{DIM}]= Fundamental only   [/{DIM}]"
        f"[yellow3]F✗ T✓[/yellow3] [{DIM}]= Technical only[/{DIM}]"
    )
    console.print()

    # ── BUY candidates callout ────────────────────────────────
    buys = [r for r in rows if r["gate3"] and r["gate4"]]
    if buys:
        console.print(Rule(style="bright_green dim"))
        console.print(
            f"\n  [bold bright_green]TOP BUY CANDIDATES[/bold bright_green]  "
            f"[{DIM}]{len(buys)} ticker{'s' if len(buys) != 1 else ''} pass both gates[/{DIM}]\n"
        )
        for r in buys[:8]:
            rr_c  = "bright_green" if r["rr"] >= 2.0 else "yellow3"
            al_c  = "bright_green" if r["alpha"] >= 60 else "yellow3"
            st_c  = STRAT_COLORS.get(r["strategy"], DIM)
            console.print(
                f"  [bold bright_green]{r['ticker']:12}[/bold bright_green]"
                f"  [{DIM}]α[/{DIM}] [{al_c} bold]{r['alpha']:.0f}[/{al_c} bold]"
                f"  [{DIM}]R:R[/{DIM}] [{rr_c}]1:{r['rr']:.2f}[/{rr_c}]"
                f"  [{DIM}]SS[/{DIM}] [{_risk_color(100 - r['signal_str'])}]{r['signal_str']}[/{_risk_color(100 - r['signal_str'])}]"
                f"  [{DIM}]Entry[/{DIM}] [white]{r['entry']:.4f}[/white]"
                f"  [{DIM}]TP[/{DIM}] [bright_green]{r['tp']:.4f}[/bright_green]"
                f"  [{DIM}]SL[/{DIM}] [red1]{r['sl']:.4f}[/red1]"
                f"  [{DIM}]Moat[/{DIM}] [{'bright_green' if r['moat'] > 0 else 'red1'}]{r['moat']:+.3f}[/{'bright_green' if r['moat'] > 0 else 'red1'}]"
                f"  [{st_c}]{r['strategy']}[/{st_c}]"
                f"  [medium_purple1]{r['sector']}[/medium_purple1]"
            )
        console.print()
    else:
        console.print(
            f"  [yellow3]No tickers pass both gates at current market conditions "
            f"(regime risk: {composite_risk:.0f}/100).[/yellow3]\n"
        )


# ══════════════════════════════════════════════════════════════
# SECTOR MINI-TABLE  (compact overview after Stage 2)
# ══════════════════════════════════════════════════════════════

def _render_sector_overview(ranked: list) -> None:
    st = Table(
        box=None, show_header=True,
        header_style=f"bold {DIM}", padding=(0, 1), show_edge=False,
    )
    st.add_column("Sector",   style="medium_purple1", width=18)
    st.add_column("Score",    width=6,  justify="right")
    st.add_column("",         width=14, no_wrap=True)
    st.add_column("20d Mom",  width=10, justify="right")
    st.add_column("RS",       width=10, justify="right")
    st.add_column("Breadth",  width=10, justify="right")
    st.add_column("Signal",   width=22)
    st.add_column("Members",  width=6,  justify="right")

    for s in ranked:
        sc   = s["sector_score"]
        sig  = s["signal"]
        gate = s["gate_pass"]
        mc   = "bright_green" if s["mom_20d_pct"] > 0 else "red1"
        rc   = "bright_green" if s["rs_vs_index"] > 0 else "red1"
        sty  = "bold white" if gate else DIM
        n_mem = len(s.get("members", []))
        st.add_row(
            f"[{sty}]{s['sector']}[/{sty}]",
            f"[{_risk_color(100 - sc)} bold]{sc:.0f}[/{_risk_color(100 - sc)} bold]",
            _mini_bar(sc, 12),
            f"[{mc}]{s['mom_20d_pct']:+.2f}%[/{mc}]",
            f"[{rc}]{s['rs_vs_index']:+.2f}%[/{rc}]",
            f"{s['breadth_pct']:.0f}%",
            f"[{_signal_color(sig)}]{sig}[/{_signal_color(sig)}]",
            f"[{DIM}]{n_mem}[/{DIM}]" if n_mem else "",
        )
    console.print(st)
    console.print()


# ══════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════

async def run_ranking_cli() -> None:
    console.clear()

    # ── Banner ────────────────────────────────────────────────
    console.print()
    console.print(Align.center(Panel(
        f"[bold {ACCENT}]ALPHA-STREAM RANKING SCANNER[/bold {ACCENT}]\n"
        f"[{DIM}]Full Universe Batch Analysis  ·  Stages 0–4  ·  Ranked Leaderboard[/{DIM}]",
        border_style=ACCENT,
        padding=(1, 6),
        expand=False,
    )))
    console.print()

    # ── Universe selection ────────────────────────────────────
    universe_key = await questionary.select(
        "Select universe to scan:",
        choices=[
            questionary.Choice("SET100 Thailand",    value="SET100"),
            questionary.Choice("Personal Watchlist", value="WATCHLIST"),
        ],
    ).ask_async()
    if not universe_key:
        return
    universe_cfg = UNIVERSE_REGISTRY[universe_key]

    # ── Scan concurrency ──────────────────────────────────────
    speed = await questionary.select(
        "Scan speed:",
        choices=[
            questionary.Choice("Conservative  (4  concurrent — slower, more reliable)", value="4"),
            questionary.Choice("Standard      (8  concurrent — recommended)",           value="8"),
            questionary.Choice("Aggressive    (12 concurrent — faster, may hit limits)", value="12"),
        ],
    ).ask_async()
    concurrency = int(speed or "8")
    console.print()

    all_tickers = list(dict.fromkeys(
        t for s in universe_cfg["universe"].values() for t in s["members"]
    ))
    console.print(
        f"  [{DIM}]Universe:[/{DIM}]  [bold {ACCENT}]{universe_cfg['display_name']}[/bold {ACCENT}]"
        f"  [{DIM}]·[/{DIM}]  [bold]{len(all_tickers)} tickers[/bold]"
        f"  [{DIM}]across[/{DIM}]  [bold]{len(universe_cfg['universe'])} sectors[/bold]"
        f"  [{DIM}]·[/{DIM}]  [bold]concurrency = {concurrency}[/bold]"
    )
    console.print()

    # ══════════════════════════════════════════════════════════
    # STAGE 0  —  Market Fragility
    # ══════════════════════════════════════════════════════════

    _section(0, "MARKET FRAGILITY  ·  REGIME SNAPSHOT")
    with console.status(
        f"[{DIM}]Fetching regime signals (SPX, yield curve, VIX, credit, breadth)...[/{DIM}]",
        spinner="dots",
    ):
        spx_data = await asyncio.to_thread(_fetch_spx_sync)
        (composite_risk, regime_label, layer_scores,
         confidence, conf_signal, raw_signals) = await asyncio.to_thread(_sync_stage0, spx_data)

    console.print(Columns([
        _kpi("COMPOSITE RISK",  f"{composite_risk:.1f}/100",  _risk_color(composite_risk)),
        _kpi("REGIME",          regime_label,                  _risk_color(composite_risk)),
        _kpi("POSITION SCALE",  _regime_scale(composite_risk), _risk_color(composite_risk)),
        _kpi("CONFIDENCE",      f"{confidence:.0f}/100",
             "bright_green" if confidence >= 80 else "yellow3" if confidence >= 60 else "red1"),
        _kpi("SIGNAL CONV.",    conf_signal,
             "bright_green" if "HIGH" in conf_signal else "yellow3"),
    ], equal=False, expand=False))
    console.print()

    # Layer breakdown
    ls = layer_scores
    vix_level  = raw_signals["vix"].get("vix_level", "N/A")
    yc_bps     = raw_signals["yield_curve"].get("spread_bps", "N/A")
    brd_pct    = raw_signals["breadth"].get("pct_above_50dma", "N/A")
    console.print(
        f"  [{DIM}]Regime {ls['regime']:.0f}  ·  "
        f"Fragility {ls['fragility']:.0f}  ·  "
        f"Trigger {ls['trigger']:.0f}  ·  "
        f"VIX {vix_level:.1f}  ·  "
        f"2s10s {yc_bps:.0f}bps  ·  "
        f"Breadth {brd_pct:.0f}%[/{DIM}]"
        if isinstance(vix_level, float) else
        f"  [{DIM}]Regime {ls['regime']:.0f}  ·  Fragility {ls['fragility']:.0f}  ·  Trigger {ls['trigger']:.0f}[/{DIM}]"
    )
    console.print()

    # ══════════════════════════════════════════════════════════
    # STAGE 1  —  Global Macro
    # ══════════════════════════════════════════════════════════

    _section(1, "GLOBAL MACRO  ·  CROSS-ASSET REGIME")
    with console.status(f"[{DIM}]Running cross-asset macro analysis...[/{DIM}]", spinner="dots"):
        macro = await asyncio.to_thread(run_global_macro_analysis)

    macro_risk = macro["composite_macro_risk"]
    adj = macro.get("sector_adjustments", {})

    console.print(Columns([
        _kpi("MACRO RISK",  f"{macro_risk:.0f}/100",        _risk_color(macro_risk)),
        _kpi("REGIME",      macro["macro_regime"],           _risk_color(macro_risk)),
        _kpi("MACRO BIAS",  macro["macro_bias_summary"][:30], _risk_color(macro_risk)),
    ], equal=False, expand=False))
    console.print()

    if adj:
        parts = []
        for sector, pts in sorted(adj.items(), key=lambda x: -abs(x[1])):
            col = "bright_green" if pts > 0 else "red1" if pts < 0 else DIM
            parts.append(f"[{col}]{sector} {pts:+d}[/{col}]")
        console.print(f"  [{DIM}]Sector adjustments:[/{DIM}]  " + "   ".join(parts[:7]))
        console.print()

    # ══════════════════════════════════════════════════════════
    # STAGE 2  —  Sector Screener
    # ══════════════════════════════════════════════════════════

    _section(2, f"SECTOR SCREENER  ·  {universe_cfg['display_name']}")
    with console.status(
        f"[{DIM}]Scoring {len(universe_cfg['universe'])} sectors...[/{DIM}]",
        spinner="dots",
    ):
        sector = await asyncio.to_thread(
            run_sector_screener,
            macro,
            universe_cfg["universe"],
            universe_cfg["benchmark"],
        )

    ranked = sector["ranked_sectors"]
    top    = sector["top_sectors"]
    console.print(Columns([
        _kpi("ROTATION PHASE", sector["sector_rotation"],  "medium_purple1"),
        _kpi("TOP SECTORS",    " · ".join(top) if top else "NONE",
             "bright_green" if top else "red1"),
        _kpi("SECTOR GATE",    "OPEN" if sector["sector_gate"] else "CLOSED",
             "bright_green" if sector["sector_gate"] else "red1"),
    ], equal=False, expand=False))
    console.print()
    _render_sector_overview(ranked)

    # ══════════════════════════════════════════════════════════
    # STAGES 3 + 4  —  Batch ticker scan
    # ══════════════════════════════════════════════════════════

    _section(3, f"BATCH SCAN  ·  {len(all_tickers)} TICKERS  ·  FUND. + TECHNICAL")
    console.print(
        f"  [{DIM}]Alpha score, moat spread, Altman Z, technicals, R:R  ·  "
        f"concurrency = {concurrency}[/{DIM}]\n"
    )

    ok_rows, err_rows = await scan_universe(
        universe       = universe_cfg["universe"],
        composite_risk = composite_risk,
        macro_results  = macro,
        sector_data    = sector,
        concurrency    = concurrency,
    )

    if err_rows:
        console.print(
            f"  [yellow3]⚠  {len(err_rows)} ticker{'s' if len(err_rows) != 1 else ''} "
            f"failed (no data / delisted):[/yellow3]  "
            + "  ".join(f"[{DIM}]{r['ticker']}[/{DIM}]" for r in err_rows)
        )
        console.print()

    # ── Final ranked table ────────────────────────────────────
    render_ranking_table(
        rows           = ok_rows,
        universe_name  = universe_cfg["display_name"],
        composite_risk = composite_risk,
        macro_regime   = macro["macro_regime"],
    )


if __name__ == "__main__":
    asyncio.run(run_ranking_cli())
