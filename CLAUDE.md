# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## What this project is

An **AI-powered quantitative trading dashboard** — FastAPI backend + React/TypeScript frontend.
It is NOT a live-trading system; it is a research and analysis platform with:
- Multi-stage fundamental + macro + technical stock ranking pipeline (Stages 0–4)
- Walk-forward backtesting engine (Normal mode)
- Monte Carlo Integrated walk-forward backtesting engine (MC mode)
- HMM regime detection
- Real-time market data via yfinance

---

## Commands

### Backend

```bash
# Install Python dependencies
poetry install

# Run backend (from app/backend/)
cd app/backend && poetry run uvicorn main:app --reload --port 8000

# CLI — single ticker analysis
poetry run python -m src.cli.cli4

# CLI — full universe scan to ranked table
poetry run python -m src.cli.cli_ranking

# Linting / formatting
poetry run black src/ app/backend/
poetry run isort src/ app/backend/
poetry run flake8 src/ app/backend/

# Run tests
poetry run pytest
```

### Frontend (from app/frontend/)

```bash
npm install
npm run dev        # Vite dev server → http://localhost:3000 (proxies /api to :8000)
npm run build      # tsc + vite build (also runs type check)
npm run lint       # ESLint, max-warnings 0
```

---

## Directory structure (key files)

```
alphas/
├── app/
│   ├── backend/
│   │   ├── main.py          # ALL FastAPI routes (~1250 lines)
│   │   ├── schemas.py       # Pydantic v2 response models
│   │   ├── pipeline.py      # Pure-function adapter calling each pipeline stage
│   │   └── cache.py         # Thread-safe in-memory TTL cache
│   └── frontend/
│       ├── App.tsx              # Root shell — tab bar + react-grid-layout
│       ├── components/widgets/  # One file per widget type (BacktestWidget, HMMRegimeWidget, …)
│       ├── store/
│       │   ├── useTabStore.ts   # Zustand — tabs, widgets, layout
│       │   └── useAppStore.ts
│       ├── lib/api.ts           # All fetch calls (single API client)
│       └── types/api.ts         # TypeScript interfaces for all API responses
├── src/
│   ├── agents/
│   │   ├── market_risk.py       # Stage 0 — 3-layer market fragility / position scale
│   │   ├── global_macro.py      # Stage 1 — 8 cross-asset macro signals + quadrant
│   │   ├── sector_screener.py   # Stage 2 — sector rotation & ranking
│   │   ├── calculator.py        # Stage 3 — fundamentals (ROIC, WACC, Z-score, etc.)
│   │   ├── technical.py         # Stage 4 — strategy selection, entry/TP/SL
│   │   └── risk_manager.py      # Stage 5 — Kelly sizing, CVaR, correlation checks
│   ├── backtesting/
│   │   ├── engine.py            # Normal walk-forward engine → BacktestResult
│   │   ├── mc_engine.py         # MC integrated engine → MCEngineResult
│   │   ├── metrics.py           # compute_metrics(equity, trade_log) → dict
│   │   ├── data_loader.py       # load_prices(tickers, period_years, extra) → DataFrame
│   │   ├── interfaces.py        # TradingStrategy + PortfolioOptimizer ABCs
│   │   └── optimizers/          # 5 optimizers (see below)
│   ├── strategies/              # 7 strategies + STRATEGY_MAP
│   ├── universes/               # 5 universes + UNIVERSE_MAP
│   ├── hmm_regime/              # 4-state HMM regime detection
│   └── cli/                     # cli4.py (single ticker), cli_ranking.py (batch)
├── pyproject.toml               # Poetry config, black line-length=420
└── cloudbuild*.yaml             # Cloud Build — root / backend / frontend
```

Backend adds project root to `sys.path` via `_PROJECT_ROOT = Path(__file__).resolve().parents[2]`.
`from src.xxx import yyy` always resolves correctly when the server runs from `app/backend/`.

---

## Pipeline (Stages 0–4)

Each stage builds on the previous. Stages 0–2 are market-wide; Stages 3–4 run per-ticker.

| Stage | Module | Output |
|-------|--------|--------|
| 0 — Market Regime | `market_risk.py` | Composite risk (0–100), position scale (25–100%) |
| 1 — Global Macro | `global_macro.py` | 8-signal composite, growth/inflation quadrant, sector adjustments |
| 2 — Sector Screener | `sector_screener.py` | Sector scores; sectors below gate flagged *avoid* |
| 3 — Fundamentals | `calculator.py` | Alpha score (0–100): ROIC−WACC 30%, Sloan 20%, Altman Z 20%, Sortino 20%, FCF 10% |
| 4 — Technical | `technical.py` | Best-Sharpe strategy per ticker; entry/TP/SL, R:R gate ≥ 1.5× |

**Rank Score** = Alpha × 0.45 + Signal Strength × 0.30 + Sector Score × 0.15 + R:R Score × 0.10

---

## API endpoints (all in app/backend/main.py)

| Method | Path | TTL | Description |
|--------|------|-----|-------------|
| GET | `/api/universes` | — | List universe keys + display names |
| GET | `/api/regime` | 15 min | Stage 0: market fragility |
| GET | `/api/macro` | 30 min | Stage 1: global macro signals |
| GET | `/api/sectors/{universe}` | 30 min | Stage 2: sector screener |
| POST | `/api/scan/start?universe=` | — | Launch background full pipeline scan |
| GET | `/api/scan/status/{job_id}` | — | Poll scan progress |
| GET | `/api/scan/stream/{job_id}` | — | SSE stream of scan progress |
| GET | `/api/rankings/{universe}` | 1 hr | Cached ranking results |
| GET | `/api/price/{ticker}` | 1 hr | OHLCV bars |
| GET | `/api/market-overview` | 5 min | Instrument prices + sparklines |
| GET | `/api/watchlist?tickers=` | 5 min | Quick price/change for watchlist |
| GET | `/api/ticker/profile/{ticker}` | 1 hr | Company fundamentals |
| GET | `/api/ticker/info/{ticker}` | 5 min | Price, volume, market cap |
| GET | `/api/backtest/infer-benchmark` | — | Auto-detect benchmark from ticker suffix |
| POST | `/api/backtest/run` | — | Normal walk-forward backtest |
| POST | `/api/backtest/run-mc` | — | MC integrated walk-forward backtest |
| GET | `/api/hmm-regime` | — | HMM regime series + stats |
| GET | `/api/health` | — | Health check |
| DELETE | `/api/cache` | — | Invalidate all caches |

---

## Strategy registry (`src/strategies/STRATEGY_MAP`)

| Key | Description |
|-----|-------------|
| `MomentumStrategy` | 12-1 month momentum, monthly rebalance, top quintile long |
| `MeanReversionStrategy` | Z-score of 20d return, long when z < -1.5 |
| `MovingAverageCrossStrategy` | Long when SMA(20) > SMA(50) |
| `EMACrossStrategy` | Long when EMA(12) > EMA(26) |
| `RSIStrategy` | Long when RSI(14) < 30 |
| `VolatilityBreakoutStrategy` | ATR breakout, supports short |
| `DRSIStrategy` | Dual RSI (stock vs benchmark), needs `benchmark_prices=` kwarg |

All inherit `TradingStrategy` ABC.
`generate_signals(prices: DataFrame, **kwargs) → DataFrame` — same shape as prices, values in {+1, 0, -1, NaN}.

---

## Optimizer registry (`src/backtesting/optimizers/OPTIMIZER_MAP`)

| Key | Description |
|-----|-------------|
| `EqualWeightOptimizer` | 1/N per long; default for single-ticker mode |
| `InverseVolatilityOptimizer` | weight ∝ 1/σ, 20d realized vol |
| `MeanVarianceOptimizer` | Max Sharpe, SLSQP, 60d history, L2 λ=0.1 |
| `RiskParityOptimizer` | Equal risk contribution, scipy solver |
| `KellyCriterionOptimizer` | Geometric growth, 25% Kelly fraction |

---

## Universe registry (`src/universes/UNIVERSE_MAP`)

| Key | Benchmark |
|-----|-----------|
| `SP500_SAMPLE` | SPY (10 US mega-caps) |
| `THAI_LARGE_CAP` | ^SET.BK (SET100 stocks, .BK suffix) |
| `CRYPTO_MAJORS` | BTC-USD |
| `GLOBAL_ETF` | SPY |
| `WATCHLIST_A` | SPY (44-stock custom watchlist) |

---

## Normal backtesting engine (`src/backtesting/engine.py`)

**Entry point:** `run_backtest(prices, benchmark_prices, strategy, optimizer, initial_capital, ...) → BacktestResult`

Fold structure: non-overlapping OOS windows — IS=252d, OOS=63d, step=OOS, min 3 folds.
Signals generated upfront on full history; stop-loss checked before optimizer weights.

**BacktestResult fields:** `equity_curve`, `benchmark_curve`, `trade_log`, `fold_returns`, `metrics`, `weights_history`

---

## MC Integrated backtesting engine (`src/backtesting/mc_engine.py`)

**Entry point:** `run_mc_walk_forward(prices, benchmark_prices, params: MCParams) → MCEngineResult`

**Key design:**
- Individual trade management (cash + mark-to-market), not portfolio weights
- GBM / Student-t path simulation → per-trade TP and SL prices
- SL always checked before TP before strategy signal (hard priority order)
- `np.random.default_rng(seed=seed_base + bar_index)` — reproducible per bar
- Lookahead guard: `assert returns.index.max() <= bar` in `estimate_vol_drift()`

**MCParams** covers 49 fields: strategies, universe, period, capital/risk, MC simulation, vol estimation, position controls, exit behaviour, EV filters, position sizing, correlation controls, walk-forward settings.

**sell_strategy values:**
- Named strategy → exit on signal reversal (SL still applied)
- `"TP_SL"` → only MC-derived SL and TP exits
- `"BOTH"` → MC exits + buy strategy signal reversal

**MCEngineResult** is a superset of BacktestResult; adds `mc_trade_details` and `mc_aggregate_stats`.

---

## BacktestWidget.tsx — UI flow

Two engine mode tabs:
1. **Normal** — Universe (multi-asset + optimizer) or Single-Stock sub-modes
2. **Monte Carlo Integrated** — MC config panel → MC backtest

Reused sub-components across both modes: `KpiCard`, `LabeledSelect`, `LabeledNumber`, `ChartTooltip`, `PositionsTooltip`, `BuyDot`, `SellDot`, `StopDot`, `buildChartData()`, format helpers.

---

## Frontend state (Zustand — `useTabStore.ts`)

Each **Tab**: id, name, activeTicker, layout (react-grid-layout), widgets[].
Widget types: `historical-price | market-overview | watchlist | price-target | ticker-profile | ticker-info | regime | macro | sectors | news | rankings | backtest | hmm-regime`

Default preset tabs: Overview · Quote · Ranking · Backtest (2× side-by-side).

---

## Data loading & caching

**Price cache:** `.cache/prices/<md5>.parquet`, TTL 24h — `load_prices(tickers, period_years, extra_tickers) → DataFrame`
**HMM cache:** `.cache/hmm/<md5>.parquet`
**API cache:** `TTLCache` in `cache.py`, per-endpoint TTLs (5 min – 1 hr)
**`_clean_floats(obj)`** — recursively replaces NaN/Inf with None before JSON serialisation; called on every response.

---

## Metrics (`src/backtesting/metrics.py`)

`compute_metrics(equity, trade_log, risk_free_rate=0.02) → dict`

Returns: total_return, cagr, sharpe_ratio, max_drawdown, calmar_ratio, volatility_ann, avg_trade_return, win_rate, avg_win, avg_loss, reward_to_risk, total_trades, long_trades, short_trades.
`trade_log` must have columns `return_pct` and `direction`.

---

## HMM Regime (`src/hmm_regime/`)

4-state HMM (bull, sideways, bear, crash). Walk-forward: train on 80% of history, test on last 20%.
Features: returns, realized vol, log-volume ratio.

---

## Key invariants (never violate)

1. **No lookahead in mc_engine:** `estimate_vol_drift()` slices to `[:bar]` and asserts `returns.index.max() <= bar`.
2. **SL priority:** In `check_exits_priority()`, SL is checked BEFORE TP BEFORE strategy signal. Do not reorder.
3. **purge_days ≥ holding_days:** Asserted at the start of `run_mc_walk_forward()`.
4. **Reproducible RNG:** Use `np.random.default_rng(seed=seed_base + bar_index)`. Never use `np.random.seed()` or global state.
5. **Normal mode unchanged:** Feature work must not touch existing Normal backtest code paths.
6. **Strategy interface:** `generate_signals()` returns DataFrame same shape as prices, values in {+1, 0, -1, NaN}. Never change this contract.
7. **BacktestResult compatibility:** MC engine must produce all fields consumed by the serialiser in `/api/backtest/run` (equity_curve, benchmark_curve, trade_log with asset/entry_date/exit_date/return_pct/pnl/equity_at_exit/stop_triggered, fold_returns, metrics, weights_history).
