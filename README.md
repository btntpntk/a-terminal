# Alpha-Stream — AI-Powered Quantitative Trading Dashboard

A research platform that runs a five-stage fundamental + macro + technical ranking pipeline on equity universes and pairs it with a walk-forward backtesting suite (Normal and Monte Carlo Integrated modes), presented in a Bloomberg Terminal-style web dashboard.

---

## Overview

Alpha-Stream solves the problem of manually synthesising market regime, macroeconomic signals, sector rotation, fundamental quality scoring, and technical entry signals into a single actionable rank. Each stock in the selected universe passes through five sequential filter/scoring stages. Only stocks that clear fundamental and technical gates receive a **BUY** verdict; everything else is labelled `FUND_ONLY`, `TECH_ONLY`, or `FAIL`.

Separately, the backtesting engine lets you validate any strategy or optimizer against historical data using walk-forward methodology, with an optional Monte Carlo layer that derives Take-Profit and Stop-Loss levels from simulated price paths.

---

## Quick Start

### Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.11+ |
| Node.js | 18+ |
| Poetry | Latest |

### Install

```bash
# 1. Clone the repository
git clone <repo-url>
cd alphas

# 2. Python dependencies
poetry install

# 3. Frontend dependencies
cd app/frontend
npm install
cd ../..
```

### Environment variables

No `.env` file is required for basic operation. yfinance fetches public market data. If you add LLM agents that call Anthropic's Claude API, set:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

### Run

```bash
# Backend — from app/backend/
poetry run uvicorn main:app --reload --port 8000

# Frontend — from app/frontend/ (separate terminal)
npm run dev
# → http://localhost:5173  (proxies /api → localhost:8000)
```

### Quick API test

```bash
# Check health
curl http://localhost:8000/api/health

# Get market regime score (Stage 0)
curl http://localhost:8000/api/regime

# Launch a full pipeline scan on the S&P 500 sample universe
curl -X POST "http://localhost:8000/api/scan/start?universe=SP500_SAMPLE"
# → {"job_id": "abc123"}

# Poll progress
curl http://localhost:8000/api/scan/status/abc123

# Retrieve ranked results
curl http://localhost:8000/api/rankings/SP500_SAMPLE
```

---

## Project Structure

```
alphas/
├── app/
│   ├── backend/
│   │   ├── main.py          # All FastAPI routes (~2200 lines)
│   │   ├── pipeline.py      # Stage adapters (pure functions)
│   │   ├── schemas.py       # Pydantic v2 response models
│   │   └── cache.py         # Thread-safe in-memory TTL cache
│   └── frontend/
│       ├── App.tsx           # Root layout
│       ├── components/widgets/
│       │   ├── BacktestWidget.tsx       # Normal + MC backtest UI
│       │   ├── HMMRegimeWidget.tsx      # HMM regime chart
│       │   ├── RankingsWidget.tsx       # Screener table + grouped header
│       │   └── ...                      # 15 other widgets
│       ├── components/ranking/
│       │   ├── RankingsTable.tsx
│       │   ├── TickerDrawer.tsx
│       │   ├── PriceChart.tsx
│       │   └── WeightsConfig.tsx        # ⚙ Configurable score weights modal
│       ├── store/
│       │   ├── useTabStore.ts           # Tab/widget layout (Zustand, persisted)
│       │   └── useAppStore.ts           # Filters + score weights (Zustand, persisted)
│       ├── lib/
│       │   ├── api.ts                   # All fetch calls
│       │   ├── format.ts
│       │   ├── calculateHurst.ts        # Client-side Hurst exponent
│       │   └── alphaScore.ts            # Client-side AlphaScore + Rank Score recompute
│       └── types/api.ts                 # TypeScript interfaces
├── src/
│   ├── agents/
│   │   ├── market_risk.py      # Stage 0 — Market regime (3-layer composite)
│   │   ├── global_macro.py     # Stage 1 — 8 cross-asset macro signals
│   │   ├── sector_screener.py  # Stage 2 — Sector momentum/breadth/volume
│   │   ├── calculator.py       # Stage 3 — ROIC, WACC, Altman Z, Sortino, CVaR
│   │   └── technical.py        # Stage 4 — Strategy selection, entry/TP/SL
│   ├── backtesting/
│   │   ├── engine.py           # Normal walk-forward engine
│   │   ├── mc_engine.py        # Monte Carlo integrated engine
│   │   ├── metrics.py          # compute_metrics() → KPI dict
│   │   ├── data_loader.py      # load_prices() with .parquet cache
│   │   ├── interfaces.py       # TradingStrategy + PortfolioOptimizer ABCs
│   │   └── optimizers/         # 5 optimizers (equal_weight, inverse_vol, mean_variance, risk_parity, kelly)
│   ├── strategies/             # 18 trading strategies + STRATEGY_MAP
│   ├── hmm_regime/             # 4-state Gaussian HMM (bull/sideways/bear/crash)
│   ├── universes/              # 5 universe definitions
│   └── data/
│       ├── providers.py        # yfinance data access layer
│       └── yfinance_cache.py   # Disk-backed TTL cache for ticker data
├── .cache/
│   ├── prices/                 # Backtesting price cache (parquet)
│   ├── hmm/                    # HMM fit cache
│   └── ticker/                 # Per-ticker scan cache (history + fundamentals)
└── pyproject.toml
```

---

## API Reference

Base URL: `http://localhost:8000`

| Method | Endpoint | TTL | Description |
|--------|----------|-----|-------------|
| GET | `/api/universes` | — | List registered universes |
| GET | `/api/regime` | 15 min | Stage 0: composite risk, layer scores, position scale |
| GET | `/api/macro` | 30 min | Stage 1: 8 signals, quadrant, sector adjustments |
| GET | `/api/sectors/{universe}` | 30 min | Stage 2: ranked sectors, rotation phase |
| POST | `/api/scan/start?universe=` | — | Launch background full pipeline scan |
| GET | `/api/scan/status/{job_id}` | — | Poll scan progress |
| GET | `/api/scan/stream/{job_id}` | — | SSE stream of live scan progress |
| GET | `/api/rankings/{universe}` | 1 hr | Cached ranking results from last scan |
| GET | `/api/price/{ticker}` | 1 hr | OHLCV bars |
| GET | `/api/market-overview` | 5 min | Multi-instrument prices + sparklines |
| GET | `/api/backtest/infer-benchmark` | — | Auto-detect benchmark from ticker suffix |
| POST | `/api/backtest/run` | — | Normal walk-forward backtest |
| POST | `/api/backtest/run-mc` | — | Monte Carlo integrated backtest |
| GET | `/api/hmm-regime` | — | HMM regime series + state probabilities |
| GET | `/api/health` | — | Health check |
| DELETE | `/api/cache` | — | Invalidate in-memory TTL caches; pass `?include_ticker_cache=true` to also wipe the on-disk per-ticker cache |

---

## Rankings UI

The Rankings widget includes:

- **Grouped header band** above the column row — columns ALPHA · MOAT · Z · SLOAN · FCF are tagged **FUNDAMENTAL** (orange, matching the FUND verdict pill); SORT · β · STRAT · SS · R:R · ENTRY · TP · SL are tagged **TECHNICAL** (cyan, matching the TECH verdict pill).
- **⚙ Weights button** in the toolbar — opens a modal to adjust the five AlphaScore indicator weights (Moat / Sloan / FCF / Altman / Sortino) and the four Rank Score component weights (AlphaScore / Signal Strength / Sector Score / R:R). Weights apply **live** via client-side recomputation — no rescan needed. Verdict pills update when adjusted alpha crosses the gate threshold. Weights persist across reloads via localStorage. See [`app/frontend/lib/alphaScore.ts`](app/frontend/lib/alphaScore.ts) for the TypeScript port of the tiered scoring logic.

---

## Caching Layers

| Layer | Location | TTL | Purpose |
|-------|----------|-----|---------|
| API response cache | In-memory (`cache.py`) | 5 min – 1 hr per endpoint | Stage 0/1/2 responses, final rankings, market-overview, news, etc. |
| Per-ticker yfinance cache | `.cache/ticker/<ticker>/` | 4 h prices, 24 h fundamentals | Eliminates redundant Yahoo round-trips on re-scans |
| Backtesting price cache | `.cache/prices/<md5>.parquet` | 24 h | Used by `load_prices()` in the backtesting engine |
| HMM cache | `.cache/hmm/<md5>.parquet` | — | HMM regime detection results |
| Frontend score weights | `localStorage` | Until cleared | User-customised AlphaScore / Rank Score weights |

**First scan** of a universe: cold cache, ~30-60 s on SET100 depending on Yahoo throttling.
**Re-scan within 4 h:** prices and fundamentals served from disk → CPU-bound, ~5-10× faster.
**Re-scan after 4 h, within 24 h:** prices re-fetched (small), fundamentals from disk.

Clear caches manually: `rm -rf .cache/ticker/` or `curl -X DELETE "http://localhost:8000/api/cache?include_ticker_cache=true"`.

---

## Tech Stack

### Python (Backend)

| Package | Purpose |
|---------|---------|
| `fastapi` | REST API + Server-Sent Events |
| `pydantic v2` | Request/response validation |
| `yfinance` | Market data (prices, financials) |
| `pandas` / `numpy` | Time-series and numerical computation |
| `scipy` | Portfolio optimization (SLSQP) |
| `hmmlearn` | Gaussian HMM for regime detection |
| `langchain` / `langchain-anthropic` | LLM agent orchestration (Claude) |

### Node.js (Frontend)

| Package | Purpose |
|---------|---------|
| `react` 18 | UI library |
| `vite` | Dev server and bundler |
| `tailwindcss` | Utility-first CSS |
| `zustand` | Lightweight global state |
| `@tanstack/react-query` | Server state, caching, polling |
| `@tanstack/react-virtual` | Virtualised table rendering |
| `recharts` | Equity curve and sparkline charts |
| `ibm-plex-mono` | Terminal-style monospace font |
