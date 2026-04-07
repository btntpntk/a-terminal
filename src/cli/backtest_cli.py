"""
backtest_cli.py  —  Walk-forward backtesting CLI

Usage (from project root):
    python -m src.cli.backtest_cli
    python -m src.cli.backtest_cli --strategy MomentumStrategy --universe SP500_SAMPLE \\
        --optimizer EqualWeightOptimizer --period 3 --capital 1000000 --stop-loss 5

Navigate the bullet-list menus with  ↑ / ↓  arrow keys and press  SPACE or ENTER  to confirm.
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

# ── Path fix ──────────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import questionary
from questionary import Style as QStyle
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import FloatPrompt
from rich import box

from src.strategies import STRATEGY_MAP
from src.universes  import UNIVERSE_MAP
from src.backtesting.optimizers import OPTIMIZER_MAP
from src.backtesting.data_loader import load_prices
from src.backtesting.engine import run_backtest, BacktestResult

console = Console()

# ─────────────────────────────────────────────────────────────────────────────
# Questionary style  (matches the terminal's dark theme)
# ─────────────────────────────────────────────────────────────────────────────

_STYLE = QStyle([
    ("qmark",          "fg:#818cf8 bold"),       # ? mark
    ("question",       "fg:#e0e0f0 bold"),        # question text
    ("answer",         "fg:#4ade80 bold"),         # confirmed answer
    ("pointer",        "fg:#818cf8 bold"),         # ❯ bullet
    ("highlighted",    "fg:#e0e0f0 bg:#1e1e3a"),  # hovered item
    ("selected",       "fg:#4ade80"),              # selected item
    ("instruction",    "fg:#555577 italic"),       # (Use arrow keys)
    ("text",           "fg:#c0c0d0"),
    ("disabled",       "fg:#444466 italic"),
])

# ─────────────────────────────────────────────────────────────────────────────
# Option definitions  (key → display label)
# ─────────────────────────────────────────────────────────────────────────────

_STRATEGIES = [
    questionary.Choice(title="Momentum (12-1)      — long top quintile, short bottom quintile",  value="MomentumStrategy"),
    questionary.Choice(title="Mean Reversion        — Z-score ±1.5 of 20-day return",             value="MeanReversionStrategy"),
    questionary.Choice(title="MA Cross (20/50)      — per-asset 20 vs 50-day SMA",               value="MovingAverageCrossStrategy"),
    questionary.Choice(title="RSI (14)              — long <30, short >70",                       value="RSIStrategy"),
    questionary.Choice(title="Volatility Breakout   — break above 20-day high + 0.5×ATR",        value="VolatilityBreakoutStrategy"),
]

_UNIVERSES = [
    questionary.Choice(title="S&P 500 Sample   — AAPL MSFT GOOGL AMZN META TSLA NVDA JPM JNJ XOM  [benchmark: SPY]",    value="SP500_SAMPLE"),
    questionary.Choice(title="Thai Large Cap   — PTT KBANK SCB AOT CPALL GULF ADVANC BBL MINT BDMS [benchmark: ^SET.BK]", value="THAI_LARGE_CAP"),
    questionary.Choice(title="Crypto Majors    — BTC ETH BNB SOL ADA                               [benchmark: BTC-USD]", value="CRYPTO_MAJORS"),
    questionary.Choice(title="Global ETF       — SPY QQQ EEM GLD TLT IWM EFA VNQ HYG DBC          [benchmark: SPY]",     value="GLOBAL_ETF"),
    questionary.Choice(title="Watchlist A      — 44 SET blue-chips + NYSE:BKV                      [benchmark: ^SET.BK]", value="WATCHLIST_A"),
]

_OPTIMIZERS = [
    questionary.Choice(title="Equal Weight          — 1/N per long or short asset",                value="EqualWeightOptimizer"),
    questionary.Choice(title="Inverse Volatility    — weight ∝ 1/σ (20-day vol)",                  value="InverseVolatilityOptimizer"),
    questionary.Choice(title="Mean-Variance         — max Sharpe via scipy, L2 regularised",       value="MeanVarianceOptimizer"),
    questionary.Choice(title="Risk Parity           — equal risk contribution per asset",           value="RiskParityOptimizer"),
    questionary.Choice(title="Kelly Criterion (25%) — fractional Kelly, 40% individual cap",       value="KellyCriterionOptimizer"),
]

_PERIODS = [
    questionary.Choice(title=" 1 year",   value=1),
    questionary.Choice(title=" 2 years",  value=2),
    questionary.Choice(title=" 3 years",  value=3),
    questionary.Choice(title=" 5 years",  value=5),
    questionary.Choice(title="10 years",  value=10),
]

# Short labels used in summaries
_STRATEGY_SHORT = {c.value: c.title.split("—")[0].strip() for c in _STRATEGIES}
_UNIVERSE_SHORT = {c.value: c.title.split("—")[0].strip() for c in _UNIVERSES}
_OPTIMIZER_SHORT = {c.value: c.title.split("—")[0].strip() for c in _OPTIMIZERS}

# ─────────────────────────────────────────────────────────────────────────────
# Interactive config  (bullet-list menus, spacebar or enter to confirm)
# ─────────────────────────────────────────────────────────────────────────────

def _select(message: str, choices, default=None):
    """Thin wrapper: questionary.select with shared style + error handling."""
    result = questionary.select(
        message,
        choices=choices,
        default=default,
        style=_STYLE,
        use_shortcuts=False,
        use_arrow_keys=True,
        instruction="(↑↓ navigate · SPACE/ENTER confirm)",
    ).ask()
    if result is None:          # user hit Ctrl-C
        console.print("\n[dim]Aborted.[/dim]")
        sys.exit(0)
    return result


def interactive_config() -> dict:
    console.print()
    console.print(Panel(
        "[bold]WALK-FORWARD BACKTEST  ·  CONFIGURATION[/bold]\n"
        "[dim]Navigate with arrow keys — press SPACE or ENTER to confirm each choice[/dim]",
        style="blue", expand=False,
    ))
    console.print()

    strategy  = _select("Trading Strategy",       _STRATEGIES)
    universe  = _select("Asset Universe",          _UNIVERSES)
    optimizer = _select("Portfolio Optimizer",     _OPTIMIZERS)
    period    = _select("Backtest Period",          _PERIODS)

    console.print()
    capital   = FloatPrompt.ask("[cyan]Initial Capital[/cyan] [dim](USD)[/dim]",   default=1_000_000.0)
    stop_loss = FloatPrompt.ask("[cyan]Max Stop-Loss[/cyan]   [dim](%)[/dim]",      default=5.0)

    return {
        "strategy":          strategy,
        "universe":          universe,
        "optimizer":         optimizer,
        "period_years":      period,
        "initial_capital":   capital,
        "max_stop_loss_pct": stop_loss,
    }

# ─────────────────────────────────────────────────────────────────────────────
# Display helpers
# ─────────────────────────────────────────────────────────────────────────────

def _pct(v, decimals=1, plus=True) -> str:
    if v is None:
        return "[dim]—[/dim]"
    sign = "+" if (plus and v >= 0) else ""
    return f"{sign}{v * 100:.{decimals}f}%"


def _num(v, decimals=2) -> str:
    if v is None:
        return "[dim]—[/dim]"
    return f"{v:.{decimals}f}"


def _currency(v: float) -> str:
    return f"${v:,.0f}"


def _style(v, good_above=None, bad_below=None) -> str:
    if v is None:
        return "dim"
    if good_above is not None and v >= good_above:
        return "green"
    if bad_below is not None and v <= bad_below:
        return "red"
    return "yellow"

# ─────────────────────────────────────────────────────────────────────────────
# Result display
# ─────────────────────────────────────────────────────────────────────────────

def display_config_summary(cfg: dict) -> None:
    t = Table(show_header=False, box=box.SIMPLE_HEAVY, padding=(0, 2))
    t.add_column("Key",   style="dim",        width=24)
    t.add_column("Value", style="bold white")
    t.add_row("Strategy",   _STRATEGY_SHORT.get(cfg["strategy"],  cfg["strategy"]))
    t.add_row("Universe",   _UNIVERSE_SHORT.get(cfg["universe"],   cfg["universe"]))
    t.add_row("Optimizer",  _OPTIMIZER_SHORT.get(cfg["optimizer"], cfg["optimizer"]))
    t.add_row("Period",     f"{cfg['period_years']}Y")
    t.add_row("Capital",    _currency(cfg["initial_capital"]))
    t.add_row("Stop-Loss",  f"{cfg['max_stop_loss_pct']}%")
    console.print(Panel(t, title="[bold]Config[/bold]", expand=False))


def display_metrics(result: BacktestResult, cfg: dict) -> None:
    m = result.metrics

    final_value = result.equity_curve.iloc[-1] if len(result.equity_curve) else cfg["initial_capital"]
    bm_final    = result.benchmark_curve.iloc[-1] if len(result.benchmark_curve) else cfg["initial_capital"]
    pnl         = final_value - cfg["initial_capital"]

    summary = Table(show_header=False, box=box.SIMPLE_HEAVY, padding=(0, 2))
    summary.add_column("", style="dim", width=22)
    summary.add_column("Portfolio", style="bold", width=16)
    summary.add_column("Benchmark", style="dim",  width=16)
    summary.add_row(
        "Final Value",
        f"[bold white]{_currency(final_value)}[/bold white]",
        f"[dim]{_currency(bm_final)}[/dim]",
    )
    pnl_col = "green" if pnl >= 0 else "red"
    summary.add_row("P&L", f"[{pnl_col}]{'+' if pnl >= 0 else ''}{_currency(pnl)}[/{pnl_col}]", "")
    date_range = ""
    if len(result.equity_curve) >= 2:
        date_range = f"{result.equity_curve.index[0].date()}  →  {result.equity_curve.index[-1].date()}"
    summary.add_row("Period", f"[dim]{date_range}[/dim]", "")
    summary.add_row("Folds",  f"[dim]{len(result.fold_returns)} walk-forward folds[/dim]", "")
    console.print(Panel(summary, title="[bold]Summary[/bold]", expand=False))

    # ── KPI table ────────────────────────────────────────────────────────
    kpi = Table(title="Performance Metrics", box=box.ROUNDED, show_lines=False, padding=(0, 2))
    kpi.add_column("Metric",  style="dim", width=22)
    kpi.add_column("Value",   justify="right", width=14)
    kpi.add_column("",        width=3)

    def _row(label, val_str, s):
        kpi.add_row(label, f"[{s}]{val_str}[/{s}]", f"[{s}]●[/{s}]")

    _row("Total Return",     _pct(m.get("total_return")),         _style(m.get("total_return"),  good_above=0,    bad_below=0))
    _row("CAGR",             _pct(m.get("cagr")),                 _style(m.get("cagr"),          good_above=0.05, bad_below=0))
    _row("Sharpe Ratio",     _num(m.get("sharpe_ratio")),         _style(m.get("sharpe_ratio"),  good_above=1.0,  bad_below=0))
    _row("Max Drawdown",     _pct(m.get("max_drawdown"), plus=False), _style(m.get("max_drawdown"), good_above=-0.10, bad_below=-0.20))
    _row("Calmar Ratio",     _num(m.get("calmar_ratio")),         _style(m.get("calmar_ratio"),  good_above=1.0,  bad_below=0))
    _row("Ann. Volatility",  _pct(m.get("volatility_ann")),       "dim")
    _row("Avg Trade Return", _pct(m.get("avg_trade_return")),     _style(m.get("avg_trade_return"), good_above=0, bad_below=0))
    _row("Win Rate",         _pct(m.get("win_rate"), decimals=0), _style(m.get("win_rate"),      good_above=0.5,  bad_below=0.4))
    _row("Avg Win",          _pct(m.get("avg_win")),              "green")
    _row("Avg Loss",         _pct(m.get("avg_loss"), plus=False), "red")
    _row("Reward / Risk",    _num(m.get("reward_to_risk")),       _style(m.get("reward_to_risk"), good_above=1.0, bad_below=0.5))
    _row("Total Trades",     str(m.get("total_trades", 0)),       "dim")
    _row("  Long Trades",    str(m.get("long_trades",  0)),       "dim")
    _row("  Short Trades",   str(m.get("short_trades", 0)),       "dim")
    console.print(kpi)


def display_equity_sparkline(result: BacktestResult, width: int = 60) -> None:
    eq = result.equity_curve.dropna()
    bm = result.benchmark_curve.dropna()
    if len(eq) < 2:
        return

    step  = max(1, len(eq) // width)
    sampl = eq.iloc[::step]
    lo, hi = float(sampl.min()), float(sampl.max())
    rng   = hi - lo if hi > lo else 1.0
    rows  = 8

    grid = [[" "] * len(sampl) for _ in range(rows)]
    for col, val in enumerate(sampl):
        row = rows - 1 - int((float(val) - lo) / rng * (rows - 1))
        row = max(0, min(rows - 1, row))
        grid[row][col] = "▪"

    console.print("\n[bold]Equity Curve (ASCII)[/bold]")
    console.print(f"[dim]  Hi: {_currency(hi)}[/dim]")
    for row in grid:
        console.print("  " + "".join(row))
    console.print(f"[dim]  Lo: {_currency(lo)}[/dim]")

    if len(bm) >= 2:
        bm_ret = float(bm.iloc[-1] / bm.iloc[0] - 1)
        eq_ret = float(eq.iloc[-1] / eq.iloc[0] - 1)
        alpha  = eq_ret - bm_ret
        eq_col = "green" if eq_ret >= 0 else "red"
        al_col = "green" if alpha  >= 0 else "red"
        console.print(
            f"\n  Portfolio: [{eq_col}]{_pct(eq_ret)}[/{eq_col}]"
            f"  |  Benchmark: [dim]{_pct(bm_ret)}[/]"
            f"  |  Alpha: [{al_col}]{_pct(alpha, plus=True)}[/{al_col}]\n"
        )


def display_fold_breakdown(result: BacktestResult) -> None:
    if not result.fold_returns:
        return

    t = Table(title="Walk-Forward Fold Breakdown", box=box.SIMPLE, padding=(0, 2))
    t.add_column("Fold",      style="dim", width=6,  justify="right")
    t.add_column("Start",     style="dim", width=12)
    t.add_column("End",       style="dim", width=12)
    t.add_column("Days",      justify="right", width=6)
    t.add_column("Return",    justify="right", width=10)
    t.add_column("Final Val", justify="right", width=14)

    for i, fold in enumerate(result.fold_returns, 1):
        if len(fold) < 2:
            continue
        fold_ret = float(fold.iloc[-1] / fold.iloc[0] - 1)
        s = "green" if fold_ret >= 0 else "red"
        t.add_row(
            str(i),
            str(fold.index[0].date()),
            str(fold.index[-1].date()),
            str(len(fold)),
            f"[{s}]{_pct(fold_ret)}[/{s}]",
            _currency(float(fold.iloc[-1])),
        )
    console.print(t)


def display_trade_sample(result: BacktestResult) -> None:
    tl = result.trade_log
    if tl is None or tl.empty:
        console.print("[dim]No completed trades.[/dim]")
        return

    worst = tl.nsmallest(5, "return_pct")
    best  = tl.nlargest(5,  "return_pct")
    sample = worst._append(best).drop_duplicates()

    t = Table(
        title=f"Trade Sample  (worst 5 + best 5 of {len(tl)} total trades)",
        box=box.SIMPLE, padding=(0, 1),
    )
    t.add_column("Asset",     style="cyan", width=12)
    t.add_column("Direction", width=7)
    t.add_column("Entry",     style="dim",  width=12)
    t.add_column("Exit",      style="dim",  width=12)
    t.add_column("Return",    justify="right", width=10)
    t.add_column("P&L",       justify="right", width=12)

    for _, row in sample.iterrows():
        ret = row.get("return_pct")
        pnl = row.get("pnl")
        s   = "green" if (ret is not None and ret >= 0) else "red"
        d   = row.get("direction", "")
        ds  = "green" if d == "long" else "red"
        t.add_row(
            str(row.get("asset", "")),
            f"[{ds}]{d}[/{ds}]",
            str(row.get("entry_date", ""))[:10],
            str(row.get("exit_date",  ""))[:10],
            f"[{s}]{_pct(ret)}[/{s}]"  if ret is not None else "[dim]—[/dim]",
            f"[{s}]{_currency(float(pnl))}[/{s}]" if pnl is not None else "[dim]—[/dim]",
        )
    console.print(t)


# ─────────────────────────────────────────────────────────────────────────────
# Validation checklist
# ─────────────────────────────────────────────────────────────────────────────

def run_validation(result: BacktestResult, cfg: dict) -> None:
    console.print(Panel("[bold]VALIDATION CHECKLIST[/bold]", style="magenta", expand=False))

    checks: list[tuple[str, bool, str]] = []

    n_folds = len(result.fold_returns)
    checks.append(("≥ 3 walk-forward folds", n_folds >= 3, f"{n_folds} folds"))

    eq = result.equity_curve.dropna()
    eq_ok = len(eq) > 0 and abs(float(eq.iloc[0]) - cfg["initial_capital"]) < cfg["initial_capital"] * 0.01
    checks.append(("Equity starts at initial capital", eq_ok,
                   f"first={_currency(float(eq.iloc[0])) if len(eq) else 'empty'}"))

    fold_total = sum(len(f) for f in result.fold_returns)
    checks.append(("Equity length == sum of fold lengths", len(eq) == fold_total,
                   f"equity={len(eq)}, folds={fold_total}"))

    bm = result.benchmark_curve.dropna()
    bm_ok = len(bm) > 0 and abs(float(bm.iloc[0]) - cfg["initial_capital"]) < cfg["initial_capital"] * 0.01
    checks.append(("Benchmark rebased to initial capital", bm_ok,
                   f"first={_currency(float(bm.iloc[0])) if len(bm) else 'empty'}"))

    tl = result.trade_log
    required_cols = {"asset", "entry_date", "exit_date", "direction", "return_pct", "pnl"}
    cols_ok = required_cols.issubset(set(tl.columns)) if tl is not None else False
    checks.append(("Trade log has all required columns", cols_ok, ""))

    if tl is not None and not tl.empty and "direction" in tl.columns:
        bad_dirs = set(tl["direction"].unique()) - {"long", "short"}
        dir_ok = len(bad_dirs) == 0
    else:
        dir_ok = True
    checks.append(("All trade directions ∈ {long, short}", dir_ok, ""))

    required_metrics = {
        "total_return", "cagr", "sharpe_ratio", "max_drawdown",
        "avg_trade_return", "win_rate", "avg_win", "avg_loss",
        "reward_to_risk", "total_trades",
    }
    missing_m = required_metrics - set(result.metrics.keys())
    checks.append(("All 10 KPI metrics present", len(missing_m) == 0,
                   f"missing={missing_m}" if missing_m else "all present"))

    cagr = result.metrics.get("cagr")
    cagr_ok = cagr is not None and not math.isnan(cagr) and not math.isinf(cagr)
    checks.append(("CAGR is finite", cagr_ok, f"cagr={cagr}"))

    mdd = result.metrics.get("max_drawdown")
    mdd_ok = mdd is not None and mdd <= 0
    checks.append(("Max drawdown ≤ 0 (correct sign)", mdd_ok,
                   f"mdd={_pct(mdd, plus=False) if mdd is not None else '—'}"))

    fold_dates = [set(f.index) for f in result.fold_returns]
    overlap = any(
        fold_dates[i] & fold_dates[j]
        for i in range(len(fold_dates))
        for j in range(i + 1, len(fold_dates))
    )
    checks.append(("OOS fold periods are non-overlapping", not overlap, ""))

    t = Table(box=box.SIMPLE, padding=(0, 2), show_header=True)
    t.add_column("Check",  width=46)
    t.add_column("Status", width=8, justify="center")
    t.add_column("Detail", style="dim")

    passed = 0
    for label, ok, detail in checks:
        if ok:
            t.add_row(label, "[green]PASS[/green]", detail)
            passed += 1
        else:
            t.add_row(f"[red]{label}[/red]", "[red bold]FAIL[/red bold]", f"[red]{detail}[/red]")

    console.print(t)
    total = len(checks)
    col   = "green" if passed == total else ("yellow" if passed >= total * 0.7 else "red")
    console.print(f"[{col}]{passed}/{total} checks passed[/{col}]\n")


# ─────────────────────────────────────────────────────────────────────────────
# CLI argument parser
# ─────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Walk-forward backtest CLI  —  same parameters as the frontend widget.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join([
            "Strategies:  " + ", ".join(STRATEGY_MAP),
            "Universes:   " + ", ".join(UNIVERSE_MAP),
            "Optimizers:  " + ", ".join(OPTIMIZER_MAP),
        ]),
    )
    p.add_argument("--strategy",    default=None, choices=list(STRATEGY_MAP))
    p.add_argument("--universe",    default=None, choices=list(UNIVERSE_MAP))
    p.add_argument("--optimizer",   default=None, choices=list(OPTIMIZER_MAP))
    p.add_argument("--period",      type=int,     default=None, choices=[1, 2, 3, 5, 10])
    p.add_argument("--capital",     type=float,   default=None, help="Initial capital USD")
    p.add_argument("--stop-loss",   type=float,   default=None, dest="stop_loss", help="Max stop-loss %%")
    p.add_argument("--no-validate", action="store_true")
    p.add_argument("--no-trades",   action="store_true")
    p.add_argument("--no-sparkline",action="store_true")
    return p.parse_args()


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()

    any_missing = any(
        v is None for v in [args.strategy, args.universe, args.optimizer,
                             args.period, args.capital, args.stop_loss]
    )

    if any_missing:
        cfg = interactive_config()
        if args.strategy:  cfg["strategy"]          = args.strategy
        if args.universe:  cfg["universe"]           = args.universe
        if args.optimizer: cfg["optimizer"]          = args.optimizer
        if args.period:    cfg["period_years"]        = args.period
        if args.capital:   cfg["initial_capital"]    = args.capital
        if args.stop_loss: cfg["max_stop_loss_pct"]  = args.stop_loss
    else:
        cfg = {
            "strategy":          args.strategy,
            "universe":          args.universe,
            "optimizer":         args.optimizer,
            "period_years":      args.period,
            "initial_capital":   args.capital,
            "max_stop_loss_pct": args.stop_loss,
        }

    display_config_summary(cfg)

    universe  = UNIVERSE_MAP[cfg["universe"]]
    strategy  = STRATEGY_MAP[cfg["strategy"]]()
    optimizer = OPTIMIZER_MAP[cfg["optimizer"]]()

    with console.status("[bold yellow]Downloading price data…[/bold yellow]", spinner="dots"):
        t0 = time.time()
        try:
            prices = load_prices(
                tickers=universe.tickers,
                period_years=cfg["period_years"] + 2,
                extra_tickers=[universe.benchmark_ticker],
            )
        except Exception as e:
            console.print(f"[red]Failed to load prices: {e}[/red]")
            sys.exit(1)

    console.print(
        f"[dim]Loaded {len(prices)} trading days × "
        f"{len([t for t in universe.tickers if t in prices.columns])} assets "
        f"({time.time() - t0:.1f}s)[/dim]"
    )

    bm_ticker = universe.benchmark_ticker
    if bm_ticker in prices.columns:
        benchmark_prices = prices[bm_ticker]
        asset_prices     = prices[universe.tickers].dropna(how="all")
    else:
        asset_prices     = prices[universe.tickers].dropna(how="all")
        benchmark_prices = asset_prices.iloc[:, 0]

    with console.status("[bold yellow]Running walk-forward backtest…[/bold yellow]", spinner="dots"):
        t1 = time.time()
        try:
            result = run_backtest(
                prices            = asset_prices,
                benchmark_prices  = benchmark_prices,
                strategy          = strategy,
                optimizer         = optimizer,
                initial_capital   = cfg["initial_capital"],
                max_stop_loss_pct = cfg["max_stop_loss_pct"] / 100.0,
            )
        except ValueError as e:
            console.print(f"[red]Backtest error: {e}[/red]")
            sys.exit(1)
        except Exception as e:
            console.print(f"[red]Unexpected error: {e}[/red]")
            raise

    console.print(f"[dim]Completed in {time.time() - t1:.1f}s[/dim]\n")

    display_metrics(result, cfg)

    if not args.no_sparkline:
        display_equity_sparkline(result)

    display_fold_breakdown(result)

    if not args.no_trades:
        display_trade_sample(result)

    if not args.no_validate:
        run_validation(result, cfg)


if __name__ == "__main__":
    main()
