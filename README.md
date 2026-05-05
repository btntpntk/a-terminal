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
│   │   ├── main.py          # All FastAPI routes (~1250 lines)
│   │   ├── pipeline.py      # Stage adapters (pure functions)
│   │   ├── schemas.py       # Pydantic v2 response models
│   │   └── cache.py         # Thread-safe in-memory TTL cache
│   └── frontend/
│       ├── App.tsx           # Root layout
│       ├── components/widgets/
│       │   ├── BacktestWidget.tsx       # Normal + MC backtest UI
│       │   ├── HMMRegimeWidget.tsx      # HMM regime chart
│       │   ├── RankingsWidget.tsx       # Screener table
│       │   └── ...                      # 11 other widgets
│       ├── store/
│       │   ├── useTabStore.ts           # Tab/widget layout (Zustand)
│       │   └── useAppStore.ts
│       ├── lib/api.ts                   # All fetch calls
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
│       └── providers.py        # yfinance data access layer
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
| DELETE | `/api/cache` | — | Invalidate all TTL caches |

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
