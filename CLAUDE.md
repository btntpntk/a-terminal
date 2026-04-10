# CLAUDE.md — Project Memory for Alpha-Stream

> Read this file at the start of every session. It replaces the need to re-explore the codebase from scratch.

---

## What this project is

An **AI-powered quantitative trading dashboard** — FastAPI backend + React/TypeScript frontend.  
It is NOT a live-trading system; it is a research and analysis platform with:
- Multi-stage fundamental + macro + technical stock ranking pipeline
- Walk-forward backtesting engine (Normal mode)
- Monte Carlo Integrated walk-forward backtesting engine (MC mode) — **added in last session**
- HMM regime detection
- Real-time market data via yfinance

---

## How to run

```bash
# Backend (from app/backend/)
uvicorn main:app --reload --port 8000

# Frontend (from app/frontend/)
npm run dev        # Vite dev server, proxies /api to localhost:8000
```

Backend adds project root to `sys.path` automatically (`_PROJECT_ROOT = Path(__file__).resolve().parents[2]`).  
So `from src.xxx import yyy` always works when running from `app/backend/`.

---

## Directory structure (key files only)

```
alphas/
├── app/
│   ├── backend/
│   │   ├── main.py          # ALL FastAPI routes (~1250 lines)
│   │   ├── schemas.py       # Pydantic response models
│   │   ├── pipeline.py      # Multi-stage ranking pipeline (Stages 0-4)
│   │   └── cache.py         # TTLCache
│   └── frontend/
│       ├── components/widgets/
│       │   ├── BacktestWidget.tsx      # ★ Main backtest UI (Normal + MC modes, 1360 lines)
│       │   ├── HMMRegimeWidget.tsx     # HMM regime chart
│       │   ├── RankingsWidget.tsx      # Stock screening table
│       │   ├── HistoricalPriceWidget.tsx
│       │   ├── MarketOverviewWidget.tsx
│       │   ├── RegimeWidget.tsx        # Stage 0 macro regime
│       │   ├── MacroWidget.tsx
│       │   ├── SectorsWidget.tsx
│       │   ├── NewsWidget.tsx
│       │   ├── WatchlistWidget.tsx
│       │   ├── TickerInfoWidget.tsx
│       │   ├── TickerProfileWidget.tsx
│       │   └── PriceTargetWidget.tsx
│       ├── store/
│       │   ├── useTabStore.ts   # Zustand store (tabs, widgets, layout)
│       │   └── useAppStore.ts
│       ├── lib/api.ts           # API client (all fetch calls)
│       └── types/api.ts         # TypeScript interfaces for all responses
├── src/
│   ├── backtesting/
│   │   ├── engine.py            # Normal walk-forward engine (BacktestResult)
│   │   ├── mc_engine.py         # ★ NEW: MC integrated engine (MCEngineResult)
│   │   ├── metrics.py           # compute_metrics(equity, trade_log) → dict
│   │   ├── data_loader.py       # load_prices(tickers, period_years, extra) → DataFrame
│   │   ├── interfaces.py        # TradingStrategy + PortfolioOptimizer ABCs
│   │   └── optimizers/          # 5 optimizers (see below)
│   ├── strategies/              # 7 strategies + STRATEGY_MAP (see below)
│   ├── universes/               # 5 universes + UNIVERSE_MAP (see below)
│   ├── hmm_regime/              # HMM regime detection
│   └── agents/                  # LLM-based analysis agents (fundamental, macro, etc.)
```

---

## API endpoints (all in app/backend/main.py)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/universes` | List universe keys + display names |
| GET | `/api/regime` | Stage 0: market fragility (TTL 15 min) |
| GET | `/api/macro` | Stage 1: global macro signals (TTL 30 min) |
| GET | `/api/sectors/{universe}` | Stage 2: sector screener (TTL 30 min) |
| POST | `/api/scan/start?universe=` | Launch background full pipeline scan |
| GET | `/api/scan/status/{job_id}` | Poll scan progress |
| GET | `/api/scan/stream/{job_id}` | SSE stream of scan progress |
| GET | `/api/rankings/{universe}` | Cached ranking results |
| GET | `/api/price/{ticker}` | OHLCV bars (TTL 1h) |
| GET | `/api/market-overview` | Instrument prices + sparklines (TTL 5 min) |
| GET | `/api/watchlist?tickers=` | Quick price/change for watchlist (TTL 5 min) |
| GET | `/api/ticker/profile/{ticker}` | Company fundamentals (TTL 1h) |
| GET | `/api/ticker/info/{ticker}` | Price, volume, market cap (TTL 5 min) |
| GET | `/api/backtest/infer-benchmark` | Auto-detect benchmark from ticker suffix |
| POST | `/api/backtest/run` | Normal walk-forward backtest |
| POST | `/api/backtest/run-mc` | ★ NEW: MC integrated walk-forward backtest |
| GET | `/api/hmm-regime` | HMM regime series + stats |
| GET | `/api/health` | Health check |
| GET | `/api/cache/stats` | Cache key count |
| DELETE | `/api/cache` | Invalidate all caches |

---

## Strategy registry (`src/strategies/STRATEGY_MAP`)

| Key | Class | Description |
|-----|-------|-------------|
| `MomentumStrategy` | MomentumStrategy | 12-1 month momentum, monthly rebalance, top quintile long |
| `MeanReversionStrategy` | MeanReversionStrategy | Z-score of 20d return, long when z < -1.5 |
| `MovingAverageCrossStrategy` | MovingAverageCrossStrategy | Long when SMA(20) > SMA(50) |
| `EMACrossStrategy` | EMACrossStrategy | Long when EMA(12) > EMA(26) |
| `RSIStrategy` | RSIStrategy | Long when RSI(14) < 30 |
| `VolatilityBreakoutStrategy` | VolatilityBreakoutStrategy | ATR breakout, supports short |
| `DRSIStrategy` | DRSIStrategy | Dual RSI (stock vs benchmark), needs `benchmark_prices=` kwarg |

All strategies inherit `TradingStrategy` ABC.  
`generate_signals(prices: DataFrame, **kwargs) → DataFrame` — same shape as prices, values in {+1, 0, -1, NaN}.

---

## Optimizer registry (`src/backtesting/optimizers/OPTIMIZER_MAP`)

| Key | Description |
|-----|-------------|
| `EqualWeightOptimizer` | 1/N per long, used in single-ticker mode |
| `InverseVolatilityOptimizer` | weight ∝ 1/σ, uses 20d realized vol |
| `MeanVarianceOptimizer` | Max Sharpe, SLSQP, 60d history, L2 λ=0.1 |
| `RiskParityOptimizer` | Equal risk contribution, scipy solver |
| `KellyCriterionOptimizer` | Geometric growth, 25% Kelly fraction |

---

## Universe registry (`src/universes/UNIVERSE_MAP`)

| Key | Tickers | Benchmark |
|-----|---------|-----------|
| `SP500_SAMPLE` | 10 US mega-caps (AAPL MSFT GOOGL AMZN META TSLA NVDA JPM JNJ XOM) | SPY |
| `THAI_LARGE_CAP` | SET100 stocks (.BK suffix) | ^SET.BK |
| `CRYPTO_MAJORS` | BTC ETH etc. | BTC-USD |
| `GLOBAL_ETF` | Multi-country ETFs | SPY |
| `WATCHLIST_A` | 44-stock custom watchlist | SPY |

---

## Normal backtesting engine (`src/backtesting/engine.py`)

**Entry point:** `run_backtest(prices, benchmark_prices, strategy, optimizer, initial_capital, ...) → BacktestResult`

**BacktestResult fields:**
- `equity_curve: pd.Series` — DatetimeIndex → portfolio value
- `benchmark_curve: pd.Series`
- `trade_log: pd.DataFrame` — columns: asset, entry_date, exit_date, direction, return_pct, pnl, equity_at_exit, stop_triggered
- `fold_returns: list[pd.Series]` — one per fold
- `metrics: dict` — from `compute_metrics()`
- `weights_history: pd.DataFrame` — DatetimeIndex × ticker weights

**Fold structure:** non-overlapping OOS windows, IS=252d, OOS=63d, step=OOS, min 3 folds.  
Signals generated upfront on full history; stop-loss checked before optimizer weights.

---

## MC Integrated backtesting engine (`src/backtesting/mc_engine.py`) ★ NEW

**Entry point:** `run_mc_walk_forward(prices, benchmark_prices, params: MCParams) → MCEngineResult`

**Key design:**
- Individual trade management (not portfolio weights) — cash + mark-to-market
- GBM / Student-t path simulation → per-trade TP and SL prices
- SL always checked before TP before strategy signal (hard priority order)
- `np.random.default_rng(seed=seed_base + bar_index)` — reproducible per bar
- Lookahead guard: `assert returns.index.max() <= bar` in `estimate_vol_drift()`
- `purge_days >= holding_days` enforced by assertion before fold loop

**MCEngineResult fields** (superset of BacktestResult):
- All BacktestResult fields (equity_curve, benchmark_curve, trade_log, fold_returns, metrics, weights_history)
- `mc_trade_details: list[dict]` — per-trade MC fields (sl_raw, sl_applied, tp, rr, p_tp, ev, sigma_annual, exit_reason)
- `mc_aggregate_stats: dict` — mean P(TP), filter fractions, σ at entry, BE trail activations

**Trade log extra columns:** mc_sl_raw, mc_sl_applied, mc_tp, rr, p_tp, p_sl, ev, sigma_annual, fold_id, exit_reason, signal_confirmation_count

**Exit reasons:** `STOP_LOSS | TAKE_PROFIT | PARTIAL_TP | SELL_SIGNAL | TIME_EXIT`

**MCParams** has 49 fields covering: strategies, universe, backtest period, capital/risk, MC simulation, vol estimation, position controls, exit behaviour, EV filters, position sizing, correlation controls, walk-forward settings.

**sell_strategy values:**
- Named strategy (e.g. `"MomentumStrategy"`) → exit on strategy signal reversal (SL still always applied)
- `"TP_SL"` → only MC-derived SL and TP exits
- `"BOTH"` → MC exits + buy strategy signal reversal (buy signal used as sell trigger)

---

## BacktestWidget.tsx — UI flow

**Two top-level engine modes** (toggle at top of widget):
1. **Normal** — existing Universe/Single-Stock flow, zero changes
2. **Monte Carlo Integrated** — new MC config panel → MC backtest

**Normal mode sub-modes:** Universe (multi-asset + optimizer) vs Single-Stock (one ticker, full allocation, EqualWeight).

**MC config sections:** Strategies → Universe & Period → Capital & Risk → MC Simulation → Vol Estimation → Position Controls → Exit Behaviour → EV Filters → Position Sizing → Correlation Controls → Walk-Forward Settings.

**MC results:** Same equity chart + KPI cards + positions toggle + trade log as Normal mode. Plus collapsible **"Monte Carlo Details"** section with aggregate stats cards and per-trade MC table.

**Reused sub-components across both modes:** `KpiCard`, `LabeledSelect`, `LabeledNumber`, `ChartTooltip`, `PositionsTooltip`, `BuyDot`, `SellDot`, `StopDot`, `buildChartData()`, `toReturnPct()`, `fmtPct()`, `fmtNum()`, `fmtCurrency()`.

---

## Frontend state management (Zustand — `useTabStore.ts`)

Each **Tab** has: id, name, activeTicker, layout (react-grid-layout), widgets[].  
Widget types (WidgetType): historical-price, market-overview, watchlist, price-target, ticker-profile, ticker-info, regime, macro, sectors, news, rankings, backtest, hmm-regime.

**Default preset tabs:**
1. Overview — market-overview, news, regime, macro
2. Quote — ticker-info, ticker-profile, sectors, price-target, watchlist
3. Ranking — rankings (full width)
4. Backtest — 2× backtest widgets side-by-side

---

## Data loading & caching

**Price data:** `load_prices(tickers, period_years, extra_tickers)` → DataFrame (DatetimeIndex × ticker).  
Cached in `.cache/prices/<md5>.parquet`, TTL = 24h.

**HMM data:** `.cache/hmm/<md5>.parquet`

**API-level cache:** `TTLCache` in `app/backend/cache.py`, per-endpoint TTLs (5 min to 1h).

**`_clean_floats(obj)`** — recursively replace NaN/Inf with None before JSON serialisation. Called on every response.

---

## Metrics (`src/backtesting/metrics.py`)

`compute_metrics(equity: pd.Series, trade_log: pd.DataFrame, risk_free_rate=0.02) → dict`

Returns: total_return, cagr, sharpe_ratio, max_drawdown, calmar_ratio, volatility_ann, avg_trade_return, win_rate, avg_win, avg_loss, reward_to_risk, total_trades, long_trades, short_trades.

**NaN/Inf are replaced with None by `_clean()` before returning.**  
`trade_log` must have columns `return_pct` and `direction` for trade-level metrics.

---

## HMM Regime (`src/hmm_regime/`)

4-state HMM: bull, sideways, bear, crash.  
Walk-forward: train on 80% of history, test on last 20%.  
Features: returns, realized vol, log-volume ratio.  
Exposed via `GET /api/hmm-regime?ticker=&start=&train_end=&test_start=&refresh=`.

---

## Deployment (Cloud Build)

- `cloudbuild.yaml` — root build
- `cloudbuild-backend.yaml` — backend container
- `cloudbuild-frontend.yaml` — frontend static

---

## Key invariants / constraints (never violate)

1. **No lookahead in mc_engine:** `estimate_vol_drift()` slices data to `[:bar]` and asserts `returns.index.max() <= bar`.
2. **SL priority:** In `check_exits_priority()`, SL is checked BEFORE TP BEFORE strategy signal. Do not reorder.
3. **purge_days ≥ holding_days:** Asserted at the start of `run_mc_walk_forward()`.
4. **Reproducible RNG:** `np.random.default_rng(seed=seed_base + bar_index)` — never use `np.random.seed()` or global state.
5. **Normal mode unchanged:** Any feature work must not touch the existing Normal backtest code paths.
6. **Strategy interface:** `generate_signals()` returns DataFrame same shape as prices, values in {+1, 0, -1, NaN}. Never change this contract.
7. **BacktestResult compatibility:** MC engine must produce fields consumed by the existing serialiser in `/api/backtest/run` (equity_curve, benchmark_curve, trade_log with asset/entry_date/exit_date/return_pct/pnl/equity_at_exit/stop_triggered, fold_returns, metrics, weights_history).

---

## Current git state (as of last session)

All MC work is **uncommitted** (working tree dirty).  
Last committed: `932145e backtest-singlestock-strategy, hmm-first commit`

Changed files:
- `app/backend/main.py` — added MCBacktestRequest + /api/backtest/run-mc endpoint
- `app/backend/schemas.py` — minor update
- `app/frontend/types/api.ts` — added MCBacktestRequest, MCTradeDetail, MCAggregateStats, MCBacktestResponse
- `app/frontend/lib/api.ts` — added `api.runMCBacktest()`
- `app/frontend/components/widgets/BacktestWidget.tsx` — extended with MC mode (1360 lines)
- `src/backtesting/mc_engine.py` — NEW FILE (~600 lines)
- `src/hmm_regime/` — various changes from previous HMM work

---

## What was done in the last session

**Task:** Add "Monte Carlo Integrated" mode to BacktestWidget alongside existing "Normal" mode.

**Completed:**
1. `src/backtesting/mc_engine.py` — Full MC engine: vol estimation, GBM/Student-t simulation, position sizing (risk-parity or Kelly), exit priority logic (SL→TP→signal→time), breakeven trail, partial TP, correlation penalty, walk-forward fold loop with optional MC param grid-search on training window, cooloff tracking after SL exits.
2. `app/backend/main.py` — `MCBacktestRequest` Pydantic model (49 params) + `POST /api/backtest/run-mc` endpoint.
3. `app/frontend/types/api.ts` — Full TypeScript types for MC request/response.
4. `app/frontend/lib/api.ts` — `api.runMCBacktest()`.
5. `app/frontend/components/widgets/BacktestWidget.tsx` — Engine mode toggle [Normal | Monte Carlo Integrated], MCConfigPanel with all parameter sections, MC results phase (same charts/KPIs + collapsible MCDetailsSection).

**Verified:**
- `mc_engine.py` parses cleanly (AST check)
- `main.py` parses cleanly (AST check)
- `estimate_vol_drift()` returns correct EWMA vol, mu=0 for drift_method=zero
- `run_mc_simulation()` returns valid TP/SL/RR/p_tp/ev
- `purge_days < holding_days` assertion fires correctly
- Full engine run with 3 synthetic tickers, 2 folds, 200 sims completes without error
- All 20 required trade log columns present
- Exit reasons are valid (STOP_LOSS, TAKE_PROFIT, SELL_SIGNAL, TIME_EXIT)
- MC aggregate stats populated

---

## Potential next steps / known gaps

- **Commit the MC work** — nothing has been committed since the MC session.
- **Real data smoke test** — engine tested only on synthetic prices; a real run against SP500_SAMPLE may surface yfinance data issues.
- **Frontend build check** — TypeScript compilation not verified (no `npm run build` was run).
- **`sl_quantile_grid` / `tp_quantile_grid` UI** — currently read-only display in the widget when `optimise_mc_params_on_train=true`; a proper multi-value input could be added.
- **`fill_price = open_next_day` realism** — implemented as "enter at next bar's close" since only close prices are available; comment in code notes this.
- **Benchmark auto-detection for MC mode** — currently derived from `UNIVERSE_MAP[universe].benchmark_ticker`; could expose as UI field.
- **Performance** — `_max_corr_with_open()` recomputes correlation matrix per candidate per bar; could be cached per bar for large universes.
