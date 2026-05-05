# Alphas — Quantitative Trading Terminal

An institutional-grade quantitative pipeline for Thai equity markets. Stages 0–4 produce a ranked leaderboard of stocks from fundamental quality scoring through technical entry signals, presented in a Bloomberg Terminal-style web dashboard.

---

## Architecture

```
alphas/
├── src/
│   ├── agents/
│   │   ├── market_risk.py       # Stage 0 — 3-layer market fragility framework
│   │   ├── global_macro.py      # Stage 1 — 8 cross-asset macro signals
│   │   ├── sector_screener.py   # Stage 2 — sector rotation & ranking
│   │   ├── calculator.py        # Stage 3 — all fundamental metrics (ROIC, WACC, Z, etc.)
│   │   ├── technical.py         # Stage 4 — strategy selection, entry/TP/SL
│   │   └── risk_manager.py      # Stage 5 — Kelly sizing, CVaR, correlation checks
│   └── cli/
│       ├── cli4.py              # Interactive single-ticker CLI
│       └── cli_ranking.py       # Full-universe batch scan → ranked table
├── app/
│   ├── backend/                 # FastAPI server
│   │   ├── main.py              # REST + SSE endpoints, TTL cache, scan jobs
│   │   ├── pipeline.py          # Pure-function adapter for each stage
│   │   ├── schemas.py           # Pydantic v2 response models
│   │   └── cache.py             # Thread-safe in-memory TTL cache
│   └── frontend/                # React + Vite dashboard
│       ├── App.tsx              # 3-panel resizable shell
│       ├── components/
│       │   ├── panels/          # RegimePanel, MacroPanel, SectorPanel
│       │   ├── rankings/        # RankingsTable (virtualised)
│       │   ├── ranking/         # TickerDrawer
│       │   └── scan/            # ScanProgressOverlay (SSE)
│       ├── hooks/               # useQueries, useScanStream
│       ├── lib/                 # api.ts, format.ts
│       ├── store/               # Zustand app store
│       └── types/               # TypeScript API interfaces
└── pyproject.toml
```

---

## Pipeline

Each stage builds on the previous. Stages 0–2 are market-wide; Stages 3–4 run per-ticker.

### Stage 0 — Market Regime (`market_risk.py`)

Three independent layers are scored 0–100 and combined into a **composite risk** score that drives position scaling.

| Layer | Indicators | Weight |
|-------|-----------|--------|
| Regime | SPX vs 200DMA, Yield Curve (2Y/10Y), HY Credit OAS | 45% |
| Fragility | Breadth (% above 50DMA), RSP/SPY ratio | 35% |
| Trigger | VIX level, VIX term structure | 20% |

**Position scale output:**

| Composite Risk | Sizing |
|---------------|--------|
| ≤ 30 | 100% — Full Kelly |
| ≤ 45 | 80% |
| ≤ 60 | 60% |
| ≤ 74 | 40% |
| > 74 | 25% — Capital Preservation |

---

### Stage 1 — Global Macro (`global_macro.py`)

Eight cross-asset signals with fixed weights produce a **composite macro risk** score, a **growth/inflation quadrant**, and per-sector adjustments applied to every alpha score downstream.

| Signal | Ticker | Weight | Rationale |
|--------|--------|--------|-----------|
| Real Yield | ^TNX + TIP | 20% | Equity valuation regime |
| DXY | DX-Y.NYB | 20% | EM capital flow pressure |
| EM Flows | EEM vs SPY | 15% | Foreign fund direction |
| Copper | HG=F | 15% | Global growth barometer |
| Crude Oil | CL=F | 12% | Inflation / cost-push |
| China Pulse | MCHI + KWEB | 10% | Thailand's largest trading partner |
| USD/THB | USDTHB=X | 5% | Direct Thai FX signal |
| Gold | GC=F | 3% | Risk-off hedge |

**Growth/Inflation quadrants:**

| Quadrant | Conditions | Posture |
|----------|-----------|---------|
| GOLDILOCKS | Growth ↑, Inflation ↓ | Max risk, overweight equities |
| OVERHEAT | Growth ↑, Inflation ↑ | Trim duration, add commodities |
| STAGFLATION | Growth ↓, Inflation ↑ | Defensive, gold, short EM |
| RECESSION_RISK | Growth ↓, Inflation ↓ | Capital preservation |

---

### Stage 2 — Sector Screener (`sector_screener.py`)

Each sector is scored on four dimensions against the SET benchmark. Sectors below the gate threshold are flagged as *avoid*.

| Component | Metric | Weight |
|-----------|--------|--------|
| Momentum | 20d return vs ^SET.BK | 35% |
| Relative Strength | z-score vs 60d mean | 25% |
| Breadth | % of members above 50DMA | 20% |
| Volume Flow | OBV-style accumulation | 20% |

Stage 1 macro adjustments (±8 pts) are then added to the raw sector score.

---

### Stage 3 — Fundamentals (`calculator.py`)

All metrics are pre-computed in a single pass over yfinance data. No re-computation in downstream agents.

| Metric | Formula | Threshold |
|--------|---------|-----------|
| ROIC | NOPAT / Invested Capital | — |
| WACC | CAPM + debt cost (Rf=4.3%, ERP=5.0%) | — |
| Moat | ROIC − WACC | > 10% = wide moat |
| Sloan Ratio | (NI − CFO) / Total Assets | > 0.10 = red flag |
| FCF Quality | FCF / Net Income | < 0.60 = concern |
| Altman Z | Classic 5-factor model | < 1.81 = distress |
| CVaR 95% | Expected tail loss | — |
| Rolling Sortino | Excess return / downside std | — |
| Beta | Cov(stock, market) / Var(market) | Winsorised [−1, 4] |
| CCC | DIO + DSO − DPO | — |

**Alpha Score (0–100):**

| Dimension | Weight |
|-----------|--------|
| Economic Value (ROIC − WACC) | 30% |
| Earnings Quality (Sloan) | 20% |
| Survival (Altman Z) | 20% |
| Risk-Adjusted Return (Sortino) | 20% |
| FCF Quality | 10% |

High-beta stocks receive a regime penalty when composite risk > 60.

---

### Stage 4 — Technical Analysis (`technical.py`)

The strategy with the highest rolling Sharpe over recent history is selected per ticker.

| Family | Conditions | Entry logic |
|--------|-----------|-------------|
| MOMENTUM | RSI > 60, MACD +, price above upper BB | Buy pullback to 20MA |
| MEAN_REVERSION | RSI < 35, MACD −, price below lower BB | Fade to mid BB |
| BREAKOUT | ATR expansion, volume spike, range break | Buy confirmed break |

Each strategy outputs: entry price, take-profit, stop-loss, ATR-14, risk:reward ratio (gate ≥ 1.5×), and signal strength (0–100, gate ≥ 40).

---

### Ranking Score

```
Rank Score = Alpha × 0.45 + Signal Strength × 0.30 + Sector Score × 0.15 + R:R Score × 0.10
```

**Verdict:**

| Gate 3 (Fund) | Gate 4 (Tech) | Verdict |
|:---:|:---:|---------|
| ✓ | ✓ | **BUY** |
| ✓ | ✗ | FUND_ONLY |
| ✗ | ✓ | TECH_ONLY |
| ✗ | ✗ | FAIL |

---

## Universes

Two stock universes are registered in `sector_screener.py`. Each has its own sector map, member list, and benchmark.

| Key | Display Name | Benchmark | Approx. Tickers |
|-----|-------------|-----------|-----------------|
| `SET100` | SET100 Thailand | ^SET.BK | ~60 across 11 sectors |
| `WATCHLIST` | Personal Watchlist | ^SET.BK | ~45 curated names |

Sectors in SET100: ENERGY · FINANCIALS · TECH · CONSUMER_DISC · CONSUMER_STAP · HEALTH · MATERIALS · INDUSTRIALS · UTILITIES · REIT · TRANSPORT

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- [Poetry](https://python-poetry.org/)

### Install

```bash
# Python dependencies
poetry install

# Frontend dependencies
cd app/frontend
npm install
```

### Run

**Backend** (from `app/backend/`):
```bash
cd app/backend
poetry run uvicorn main:app --reload --port 8000
```

**Frontend** (from `app/frontend/`):
```bash
cd app/frontend
npm run dev
# → http://localhost:3000
```

---

## API Reference

Base URL: `http://localhost:8000`

| Method | Endpoint | TTL | Description |
|--------|----------|-----|-------------|
| GET | `/api/universes` | — | List registered universes |
| GET | `/api/regime` | 15 min | Stage 0: composite risk, layer scores, position scale |
| GET | `/api/macro` | 30 min | Stage 1: 8 signals, quadrant, sector adjustments |
| GET | `/api/sectors/{universe}` | 30 min | Stage 2: ranked sectors, rotation phase, gate pass/fail |
| POST | `/api/scan/start?universe=SET100` | — | Launch background full scan → returns `job_id` |
| GET | `/api/scan/status/{job_id}` | — | Poll scan progress |
| GET | `/api/scan/stream/{job_id}` | — | SSE stream of live scan progress |
| GET | `/api/rankings/{universe}` | 1 hr | Cached ranking results from last scan |
| DELETE | `/api/cache` | — | Invalidate all caches |
| GET | `/api/health` | — | Health check |

---

## Frontend

The dashboard is a Bloomberg Terminal-style single-page app with three resizable panels. All panel borders are draggable.

```
┌─────────────────┬──────────────────────────────────────────┐
│                 │  Stage 2 · Sectors                       │
│  Stage 0        ├──────────────────────────────────────────┤
│  Market Regime  │                                          │
│                 │  Stage 3+4 · Rankings                    │
│  Stage 1        │  (virtualised table, 19 columns)         │
│  Global Macro   │                                          │
│                 │                                          │
└─────────────────┴──────────────────────────────────────────┘
```

**Stack:** React 18 · Vite · Tailwind CSS · TanStack Query v5 · TanStack Virtual · Zustand · IBM Plex Mono

---

## Key Dependencies

**Python**

| Package | Purpose |
|---------|---------|
| fastapi | REST API + SSE |
| pydantic v2 | Response models and validation |
| yfinance | Market data (prices, financials) |
| pandas / numpy | Timeseries and numerical computation |
| langchain / langgraph | LLM agent orchestration |
| langchain-anthropic | Claude API integration |
| rich | Terminal UI tables and progress bars |
| questionary | Interactive CLI prompts |

**Node**

| Package | Purpose |
|---------|---------|
| react + react-dom | UI library |
| @tanstack/react-query | Server state, caching, polling |
| @tanstack/react-virtual | Virtual scrolling for large tables |
| zustand | Lightweight global state |
| vite | Dev server and bundler |
| tailwindcss | Utility-first CSS |
