# Bloomberg Terminal-Style Frontend — Full Specification

> **Stack prompt for an AI engineer or frontend contractor.**
> Build this as a single-page application backed by the FastAPI server at `http://localhost:8000`.

package.json : 
"
{
  "name": "vite-react-flow-template",
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "lint": "eslint . --ext ts,tsx --report-unused-disable-directives --max-warnings 0",
    "preview": "vite preview"
  },
  "dependencies": {
    "@radix-ui/react-accordion": "^1.2.10",
    "@radix-ui/react-checkbox": "^1.3.2",
    "@radix-ui/react-dialog": "^1.1.13",
    "@radix-ui/react-icons": "^1.3.2",
    "@radix-ui/react-popover": "^1.1.13",
    "@radix-ui/react-separator": "^1.1.6",
    "@radix-ui/react-slot": "^1.2.0",
    "@radix-ui/react-tabs": "^1.1.11",
    "@radix-ui/react-tooltip": "^1.2.6",
    "@types/react-syntax-highlighter": "^15.5.13",
    "@xyflow/react": "^12.5.1",
    "class-variance-authority": "^0.7.1",
    "clsx": "^2.1.1",
    "cmdk": "^1.1.1",
    "lucide-react": "^0.507.0",
    "next-themes": "^0.4.6",
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-resizable-panels": "^3.0.1",
    "react-syntax-highlighter": "^15.6.1",
    "shadcn-ui": "^0.9.5",
    "sonner": "^2.0.5",
    "tailwind-merge": "^3.2.0"
  },
  "license": "MIT",
  "devDependencies": {
    "@tailwindcss/typography": "^0.5.16",
    "@types/node": "^22.15.3",
    "@types/react": "^18.2.53",
    "@types/react-dom": "^18.2.18",
    "@typescript-eslint/eslint-plugin": "^6.20.0",
    "@typescript-eslint/parser": "^6.20.0",
    "@vitejs/plugin-react": "^4.2.1",
    "autoprefixer": "^10.4.21",
    "eslint": "^8.56.0",
    "eslint-plugin-react-hooks": "^4.6.0",
    "eslint-plugin-react-refresh": "^0.4.5",
    "postcss": "^8.5.3",
    "tailwindcss": "^3.4.1",
    "tailwindcss-animate": "^1.0.7",
    "typescript": "^5.3.3",
    "vite": "^5.0.12"
  }
}
"

---

## 1. Aesthetic & Design System

### 1.1 Visual Identity
- **Inspiration**: Bloomberg Terminal — dense information, zero decoration, every pixel earns its place
- **Background**: `#0A0A0A` (near-black)
- **Surface / card**: `#111111` with `1px solid #1E1E1E` border
- **Elevated surface** (drawers, modals): `#161616`
- **Primary accent — Amber**: `#FF8C00` (labels, active states, live data)
- **Secondary accent — Cyan**: `#00B4D8` (positive momentum, buy signals)
- **Danger — Red**: `#FF3B30` (risk, sell, loss)
- **Warning — Yellow**: `#FFD60A`
- **Muted text**: `#6B6B6B`
- **Body text**: `#C8C8C8`
- **Font**: `IBM Plex Mono` (all weights); fallback `Courier New`, monospace
- **Font sizes**: 10px micro-labels · 11px table cells · 12px body · 14px section headers · 18px KPI values · 24px hero numbers
- **No rounded corners** — everything `border-radius: 0`
- **No shadows** — use borders and background contrast only
- **No animations except**: single-column progress fill (linear, 200ms)

### 1.2 Color Semantics
| Token | Hex | Usage |
|-------|-----|-------|
| `--col-buy` | `#00FF87` | BUY verdict, gate pass |
| `--col-fund` | `#FFD60A` | FUND_ONLY |
| `--col-tech` | `#00B4D8` | TECH_ONLY |
| `--col-fail` | `#FF3B30` | FAIL verdict, gate fail |
| `--col-amber` | `#FF8C00` | Amber accent — headers, active |
| `--col-green` | `#00C853` | Positive delta |
| `--col-red` | `#FF3B30` | Negative delta |
| `--col-dim` | `#6B6B6B` | Secondary text |
| `--col-border` | `#1E1E1E` | Dividers |
| `--col-surface` | `#111111` | Panel background |

### 1.3 Quadrant Colors
| Quadrant | Color |
|----------|-------|
| GOLDILOCKS | `#00FF87` |
| OVERHEAT | `#FF8C00` |
| STAGFLATION | `#FF3B30` |
| RECESSION_RISK | `#FFD60A` |

---

## 2. Layout

```
┌────────────────────────────────────────────────────────────────────┐
│  TOPBAR  — logo · universe selector · scan button · clock · health │
├──────────────┬──────────────────────────────────┬──────────────────┤
│              │                                  │                  │
│  LEFT PANEL  │       CENTER PANEL               │  RIGHT PANEL     │
│  Stage 0     │       Rankings Table             │  Sector Overview │
│  Regime      │       (Stages 3+4)               │  (Stage 2)       │
│  ──────────  │                                  │  ──────────────  │
│  Stage 1     │                                  │  Macro Signals   │
│  Macro       │                                  │  (Stage 1 cards) │
│              │                                  │                  │
├──────────────┴──────────────────────────────────┴──────────────────┤
│  STATUSBAR — last updated · cache TTL · scan progress              │
└────────────────────────────────────────────────────────────────────┘
```

- **Topbar**: `48px` fixed height
- **Left panel**: `320px` fixed width, full viewport height minus topbar + statusbar, scrollable
- **Center panel**: flex-grow `1`, minimum `640px`, scrollable
- **Right panel**: `280px` fixed width, scrollable
- **Statusbar**: `28px` fixed height at bottom

---

## 3. Technology Stack

| Layer | Choice |
|-------|--------|
| Framework | **Next.js 14** (App Router) |
| Styling | **Tailwind CSS** + CSS custom properties for the color tokens |
| State | **Zustand** — one store for regime, macro, sectors, rankings, scan job |
| Data fetching | **TanStack Query v5** (`useQuery` for polling, `useInfiniteQuery` if needed) |
| SSE streaming | Native `EventSource` API inside a custom React hook |
| Tables | **TanStack Table v8** — virtual rows for 100+ tickers |
| Charts | **Recharts** — sparklines only (mini bar charts for sector scores) |
| Icons | **Lucide React** |
| Fonts | Google Fonts — `IBM+Plex+Mono:wght@300;400;500;600` |
| Types | **TypeScript strict mode** |

---

## 4. API Endpoints (from `backend/main.py`)

Base URL: `http://localhost:8000`

| Method | Path | Purpose | Cache TTL |
|--------|------|---------|-----------|
| GET | `/api/universes` | List available universes | – |
| GET | `/api/regime` | Stage 0 market regime | 15 min |
| GET | `/api/macro` | Stage 1 global macro | 30 min |
| GET | `/api/sectors/{universe}` | Stage 2 sector screener | 30 min |
| POST | `/api/scan/start?universe={key}` | Launch background scan | – |
| GET | `/api/scan/status/{job_id}` | Poll scan job status | – |
| GET | `/api/scan/stream/{job_id}` | SSE real-time scan progress | stream |
| GET | `/api/rankings/{universe}` | Final ranking table | 1 hour |
| DELETE | `/api/cache` | Admin cache bust | – |
| GET | `/api/cache/stats` | Cache diagnostics | – |
| GET | `/api/health` | Health check | – |

### 4.1 TypeScript Response Types

```typescript
// Stage 0
interface LayerScores { regime: number; fragility: number; trigger: number }
interface RegimeResponse {
  composite_risk: number;      // 0–100
  regime_label: string;
  layer_scores: LayerScores;
  confidence: number;
  confidence_signal: string;
  position_scale: string;      // "100% — Full Kelly" … "25% — Capital Preservation"
  spx_distance_pct: number | null;
  spx_signal: string;
  spx_risk_score: number;
  yield_spread_bps: number | null;
  yield_signal: string;
  yield_risk_score: number;
  hy_oas_bps: number | null;
  hy_signal: string;
  hy_risk_score: number;
  breadth_pct: number | null;
  breadth_signal: string;
  breadth_risk_score: number;
  rsp_z_score: number | null;
  rsp_signal: string;
  rsp_risk_score: number;
  vix_level: number | null;
  vix_percentile: number | null;
  vix_signal: string;
  vix_risk_score: number;
  vix_roll_yield: number | null;
  vix_term_signal: string;
  vix_term_risk_score: number;
  timestamp: string;
}

// Stage 1
interface MacroSignalDetail {
  ticker: string;
  current_price: number | null;
  mom_20d_pct: number | null;
  mom_60d_pct: number | null;
  z_score_60d: number | null;
  signal: string;
  risk_score: number;           // 0–100
  macro_bias: string;
  // signal-specific
  yield_level: number | null;
  yield_chg_20d: number | null;
  real_yield_rising: boolean | null;
  tip_mom_20d: number | null;
  usdthb_rate: number | null;
  eem_mom_20d: number | null;
  spy_mom_20d: number | null;
  em_alpha_20d: number | null;
  thd_mom_20d: number | null;
  mchi_mom_60d: number | null;
  kweb_mom_20d: number | null;
  note: string | null;
}
interface MacroResponse {
  real_yield: MacroSignalDetail;
  dxy: MacroSignalDetail;
  thb: MacroSignalDetail;
  crude_oil: MacroSignalDetail;
  copper: MacroSignalDetail;
  gold: MacroSignalDetail;
  em_flows: MacroSignalDetail;
  china: MacroSignalDetail;
  composite_macro_risk: number;
  macro_regime: string;
  cycle_quadrant: string;       // GOLDILOCKS | OVERHEAT | STAGFLATION | RECESSION_RISK
  quadrant_advice: string;
  copper_gold_ratio: number;
  macro_bias_summary: string;
  sector_adjustments: Record<string, number>;
  raw_scores: Record<string, number>;
  signal_weights: Record<string, number>;
  timestamp: string;
}

// Stage 2
interface SectorItem {
  sector: string;
  etf: string;
  sector_score: number;
  mom_20d_pct: number;
  mom_60d_pct: number | null;
  rs_vs_index: number;
  breadth_pct: number;
  volume_flow: number;
  macro_adj: number;
  signal: string;
  gate_pass: boolean;
}
interface SectorsResponse {
  universe: string;
  sector_gate: boolean;
  sector_rotation: string;
  top_sectors: string[];
  avoid_sectors: string[];
  ranked_sectors: SectorItem[];
  timestamp: string;
}

// Stages 3+4
interface TickerRow {
  ticker: string;
  sector: string;
  price: number | null;
  alpha: number;
  roic: number | null;
  wacc: number | null;
  moat: number | null;
  z: number | null;
  sloan: number | null;
  fcf_q: number | null;
  beta: number | null;
  cvar: number | null;
  sortino: number | null;
  a_turn: number | null;
  ccc: number | null;
  sector_score: number;
  sector_adj: number;
  strategy: string;
  regime_fit: string | null;
  signal_str: number;
  rr: number;
  entry: number | null;
  tp: number | null;
  sl: number | null;
  atr: number | null;
  gate3: boolean;
  gate4: boolean;
  rank_score: number;
  verdict: 'BUY' | 'FUND_ONLY' | 'TECH_ONLY' | 'FAIL';
}
interface RankingsResponse {
  universe: string;
  total_scanned: number;
  buy_count: number;
  failed_count: number;
  composite_risk: number;
  macro_regime: string;
  cycle_quadrant: string;
  rows: TickerRow[];
  errors: { ticker: string; error: string }[];
  timestamp: string;
}

// Scan job
interface ScanProgress {
  job_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  universe: string;
  total: number;
  completed: number;
  progress_pct: number;
  started_at: string;
  completed_at: string | null;
  error: string | null;
}
interface ScanResult extends ScanProgress {
  rankings: RankingsResponse | null;
}

// SSE event payload
interface ScanStreamEvent {
  job_id: string;
  status: string;
  progress_pct: number;
  completed: number;
  total: number;
  current_ticker: string | null;
}
```

---

## 5. Component Specifications

### 5.1 `<Topbar />`
```
[ALPHAS]  [Universe ▾]  [▶ RUN SCAN]   ·   [12:34:56 UTC]  [● LIVE]
```
- **Logo**: amber text `ALPHAS` — 14px monospace, no icon
- **Universe selector**: styled `<select>` — amber border, black bg, lists all `/api/universes` items
- **RUN SCAN button**: amber border + amber text, 28px height; on click → POST `/api/scan/start`, store `job_id` in Zustand, open scan progress overlay
- **Clock**: live UTC clock updating every second
- **Health dot**: green `●` if `/api/health` returns 200, red `●` otherwise (poll every 30s)

### 5.2 `<RegimePanel />` (left panel, top half)
```
─── STAGE 0 · MARKET REGIME ─────────────────
  COMPOSITE RISK    67.4
  REGIME            ELEVATED
  POSITION SCALE    40%
  CONFIDENCE        HIGH (82%)
  ─────────────────────────────────────────
  INDICATOR         VAL       SIG    SCORE
  SPX vs 200DMA    +3.2%     NEUTRAL   45
  Yield Curve       -12bp     RISK      72
  HY Spread         412bp     RISK      68
  Breadth >50DMA    48%       CAUTION   58
  RSP/SPY Z         -1.2      CAUTION   62
  VIX Level         22.4      CAUTION   55
  VIX Term          -0.04     NEUTRAL   42
  ─────────────────────────────────────────
  Layer Scores
  Regime ████████░░  78    Fragility ██████░░░░  62
  Trigger ████░░░░░░  44
```
- **Composite risk number**: color-coded — `≤30` green · `≤45` cyan · `≤60` amber · `≤74` orange · `>74` red
- **Regime label**: amber uppercase
- **Position scale**: bright white, large (18px)
- **Each indicator row**: ticker-style monospace, `SIG` colored by value (NEUTRAL=dim, CAUTION=amber, RISK=red, SAFE=green)
- **Score bar**: inline `█` fill characters proportional to 0–100 (10 chars wide)
- Refresh button `↺` top-right — adds `?refresh=true` to query and invalidates TanStack cache

### 5.3 `<MacroPanel />` (left panel, bottom half)
```
─── STAGE 1 · GLOBAL MACRO ──────────────────
  MACRO RISK    54    REGIME  NEUTRAL
  CYCLE         GOLDILOCKS  ·  "Favor equities, reduce gold"
  Cu/Au Ratio   0.0031

  SIG       TICKER   PRICE   20d%   Z60   BIAS   WT   SCORE
  REAL YLD  TIP      89.2   +0.4%  -0.8  BULL   20%   35
  DXY       DX-Y.NYB 104.1  +0.8%  +1.1  BEAR   20%   65
  EM FLOWS  EEM      40.3   -1.2%  -1.4  BEAR   15%   70
  COPPER    HG=F     4.22   +2.1%  +0.9  BULL   15%   30
  OIL       CL=F     77.1   +1.3%  +0.3  BULL   12%   40
  CHINA     MCHI     25.4   -3.1%  -1.9  BEAR   10%   78
  THB       USDTHB   35.8   +0.6%  +0.4  BEAR    5%   55
  GOLD      GC=F    2310    +0.2%  +0.1  BULL    3%   28

  SECTOR ADJUSTMENTS
  ENERGY       +5 ▮▮▮▮▮
  TECH         -8 ▮▮▮▮▮▮▮▮
  HEALTH        0 ·
  ...
```
- **Cycle quadrant pill**: colored background matching quadrant color, black text, uppercase
- **Quadrant advice**: italic, dimmed, 10px
- **Signal table**: compact, 11px — `BIAS` column BULL=green, BEAR=red, NEUTRAL=dim
- **Sector adjustments**: mini horizontal bar, amber for positive, red for negative, muted for zero

### 5.4 `<SectorPanel />` (right panel, top)
```
─── STAGE 2 · SECTORS · SET100 ─────────────
  GATE: ✓ PASS   ROTATION: DEFENSIVE

  TOP     ENERGY · HEALTH · UTILITIES
  AVOID   TECH · CONSUMER_DISC

  RANK  SECTOR         ETF     SCORE   MOM20d  RS    GATE
   1    ENERGY         PTT.BK   72.4   +2.1%  +0.8   ✓
   2    HEALTH         BDMS.BK  68.1   +1.4%  +0.5   ✓
   3    UTILITIES      BGRIM.BK 61.2   +0.9%  +0.1   ✓
   4    FINANCIALS     KBANK.BK 54.3   -0.2%  -0.3   ✗
  ...
```
- **GATE pill**: `✓ PASS` in green, `✗ FAIL` in red
- **ROTATION tag**: colored — OFFENSIVE=cyan, DEFENSIVE=amber, NEUTRAL=dim
- **Top sectors**: comma-separated, bold green
- **Avoid sectors**: comma-separated, bold red
- **Ranked table**: score bar mini-fill in score column, gate `✓`=green `✗`=red

### 5.5 `<RankingsTable />` (center panel — main feature)
```
─── RANKINGS · SET100 · 87 tickers ─────────────────────────────────
  ▶ RUN SCAN to update  ·  Last: 2026-03-26 12:30 UTC  ·  BUY: 8
  [Filter: All ▾] [Verdict: All ▾] [Sector: All ▾]  🔍 _______

  #   TICKER  SECTOR    SCORE  ALPHA  MOAT   Z     SLOAN  FCF   SORT  β
  1   DELTA   TECH       78.4   82.1  +8.2  4.21  -0.04  0.91  1.82  0.9
  2   BDMS    HEALTH     74.1   76.3  +6.1  3.88  +0.02  0.85  1.54  0.7
  ...

       STRATEGY   SS  R:R  ENTRY    TP      SL     GATE  VERDICT
       BREAKOUT   82  2.4  89.50  110.00   80.00   ✓✓    BUY
       TREND_FLW  71  1.9  256.0  295.00  240.00   ✓✓    BUY
```

**Columns** (22 total, horizontally scrollable):

| # | Column | Width | Notes |
|---|--------|-------|-------|
| 1 | `#` | 32px | Rank, amber |
| 2 | `TICKER` | 80px | Amber, clickable → detail drawer |
| 3 | `SECTOR` | 100px | Muted |
| 4 | `SCORE` | 60px | Color-coded ≥70=green ≥50=amber <50=red |
| 5 | `ALPHA` | 56px | Fundamental score |
| 6 | `MOAT` | 52px | ROIC−WACC, +green −red |
| 7 | `Z` | 44px | Altman Z, <1.81=red |
| 8 | `SLOAN` | 56px | Accruals, >0.1=red |
| 9 | `FCF` | 44px | FCF quality |
| 10 | `SORT` | 48px | Rolling Sortino |
| 11 | `β` | 36px | Beta |
| 12 | `STRAT` | 88px | Strategy name |
| 13 | `SS` | 40px | Signal strength 0–100 |
| 14 | `R:R` | 44px | Risk/reward ratio |
| 15 | `ENTRY` | 64px | Entry price |
| 16 | `TP` | 64px | Take profit |
| 17 | `SL` | 64px | Stop loss |
| 18 | `GATE` | 44px | `✓✓` `✓✗` `✗✓` `✗✗` |
| 19 | `VERDICT` | 72px | Colored pill |

**Verdict pills**:
- `BUY` — bright green bg, black text
- `FUND` — yellow bg, black text
- `TECH` — cyan bg, black text
- `FAIL` — red bg, white text (only shown in "All" filter)

**Filters**:
- Verdict filter: All · BUY · FUND · TECH · FAIL
- Sector filter: All + each sector from current universe
- Text search: filters ticker and sector (client-side)

**Default sort**: `rank_score` descending. All columns are sortable (click header = asc toggle).

**Virtualization**: Use `@tanstack/virtual` — only render visible rows (100px each) for performance on 100+ ticker lists.

**Footer row** (fixed):
```
Total: 87   BUY: 8 (9%)   FUND: 14   TECH: 6   FAIL: 59   Errors: 2
```

### 5.6 `<TickerDrawer />` (right-side slide-in, 480px)
Triggered by clicking any ticker row. Shows full detail for one ticker.

```
┌────────────────────────────────────────────────────────┐
│  DELTA.BK                          [TECH]   [✕ close] │
│  ─────────────────────────────────────────────────────│
│  ██████████████████░░   Score 78.4   BUY               │
│                                                        │
│  FUNDAMENTALS                                          │
│  Alpha Score    82.1    ROIC         18.4%             │
│  WACC           10.2%   Moat          +8.2%            │
│  Altman Z        4.21   Sloan        -0.04             │
│  FCF Quality     0.91   CVaR         -2.3%             │
│  Sortino         1.82   Beta          0.9              │
│  Asset Turn      1.12   CCC (days)   14.2              │
│  Sector Adj       +3    Sector Score  68.1             │
│                                                        │
│  TECHNICAL                                             │
│  Strategy     BREAKOUT   Regime Fit   TREND            │
│  Signal Str.        82   R:R Ratio    2.4x             │
│  Entry           89.50   ATR          3.21             │
│  Take Profit    110.00   Stop Loss   80.00             │
│  Gate 3 (Fund)    ✓      Gate 4 (Tech)  ✓             │
└────────────────────────────────────────────────────────┘
```

- Score bar at top: 20-char wide `█` fill
- All numeric fields right-aligned, monospace
- Values with risk thresholds automatically colored (Z<1.81=red, Sloan>0.1=red, etc.)

### 5.7 `<ScanProgressOverlay />`
Shown as a full-screen modal when a scan is running. Uses SSE stream.

```
┌────────────────────────────────────────────────────────┐
│  SCANNING SET100 UNIVERSE                              │
│                                                        │
│  ██████████████████░░░░░░░░░░░░░░░░░░░  47 / 87       │
│                                                        │
│  Current: KBANK.BK                                     │
│  Elapsed: 01:23   ETA: ~01:45                          │
│                                                        │
│                    [✕ cancel]                          │
└────────────────────────────────────────────────────────┘
```

- Progress bar: amber fill, black bg, `1px solid #FF8C00` border
- **Do not** poll — use the SSE stream endpoint `/api/scan/stream/{job_id}`
- On `status = "completed"`: close overlay, invalidate `/api/rankings/{universe}` TanStack cache, auto-load results
- On `status = "failed"`: show error message in red, offer retry button

### 5.8 `<Statusbar />`
Fixed 28px bar at page bottom.
```
Last updated: 2026-03-26 12:30:15 UTC  ·  Regime TTL: 8m 42s  ·  Macro TTL: 24m 01s  ·  Rankings TTL: 52m 18s  ·  Cache: 4 keys alive
```
- All 10px, muted gray text
- TTL countdown updates every second (client-side, seeded from `timestamp` fields in responses)

---

## 6. State Management (Zustand)

```typescript
interface AppStore {
  // Universe
  selectedUniverse: string;            // "SET100" | "WATCHLIST"
  setUniverse: (key: string) => void;

  // Data slices (populated by TanStack Query, mirrored here for cross-component access)
  regime:   RegimeResponse | null;
  macro:    MacroResponse  | null;
  sectors:  SectorsResponse | null;
  rankings: RankingsResponse | null;

  // Scan job
  scanJobId:  string | null;
  scanStatus: ScanProgress | null;
  setScanJob: (id: string) => void;
  clearScan:  () => void;

  // UI
  selectedTicker: string | null;       // drives TickerDrawer
  setSelectedTicker: (t: string | null) => void;

  verdictFilter: 'ALL' | 'BUY' | 'FUND_ONLY' | 'TECH_ONLY' | 'FAIL';
  sectorFilter:  string;               // "" = all
  tickerSearch:  string;
  setFilters: (f: Partial<FilterState>) => void;
}
```

---

## 7. Data Fetching Strategy

| Data | Hook | Stale Time | Refetch |
|------|------|-----------|---------|
| Universes | `useQuery(['universes'])` | Infinity | Manual only |
| Regime | `useQuery(['regime'])` | 14 min | Auto every 15 min |
| Macro | `useQuery(['macro'])` | 28 min | Auto every 30 min |
| Sectors | `useQuery(['sectors', universe])` | 28 min | On universe change |
| Rankings | `useQuery(['rankings', universe])` | 58 min | After scan completes |
| Scan status | SSE stream (not polling) | N/A | Active during scan |

**Refresh button behavior**: call `queryClient.invalidateQueries(key)` then trigger fetch with `?refresh=true` for regime (only endpoint that supports server-side force-refresh).

---

## 8. Key Behaviors

### 8.1 Startup sequence
1. Fetch `/api/universes` → populate universe selector
2. Fetch `/api/regime`, `/api/macro`, `/api/sectors/{default}` in parallel
3. Try `/api/rankings/{default}` — if 200 → show table; if 404 → show empty state with "Run scan" CTA

### 8.2 Universe change
1. Update `selectedUniverse` in Zustand
2. Invalidate and re-fetch `/api/sectors/{new}` and `/api/rankings/{new}`
3. Clear `selectedTicker` (close drawer)

### 8.3 Scan flow
```
click RUN SCAN
  → POST /api/scan/start?universe={key}
  → receive { job_id }
  → store job_id, open ScanProgressOverlay
  → open EventSource("/api/scan/stream/{job_id}")
  → handle events:
      type="progress" → update progress bar and ticker label
      type="completed" → close overlay, invalidate rankings cache
      type="failed"   → show error, offer retry
  → close EventSource on cleanup
```

### 8.4 Number formatting helpers
```typescript
const fmt = {
  pct:   (v: number | null) => v == null ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`,
  float2:(v: number | null) => v == null ? '—' : v.toFixed(2),
  int:   (v: number | null) => v == null ? '—' : Math.round(v).toString(),
  price: (v: number | null) => v == null ? '—' : v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
  score: (v: number)        => v.toFixed(1),
  z:     (v: number | null) => v == null ? '—' : v.toFixed(2),
}
```

---

## 9. File Structure

```
frontend/
├── app/
│   ├── layout.tsx          # IBM Plex Mono font, global CSS vars, black bg
│   ├── page.tsx            # Main dashboard page
│   └── globals.css         # CSS custom properties + base reset
├── components/
│   ├── layout/
│   │   ├── Topbar.tsx
│   │   └── Statusbar.tsx
│   ├── panels/
│   │   ├── RegimePanel.tsx
│   │   ├── MacroPanel.tsx
│   │   └── SectorPanel.tsx
│   ├── rankings/
│   │   ├── RankingsTable.tsx
│   │   ├── RankingsFilters.tsx
│   │   └── TickerDrawer.tsx
│   └── scan/
│       └── ScanProgressOverlay.tsx
├── hooks/
│   ├── useRegime.ts         # TanStack Query wrappers
│   ├── useMacro.ts
│   ├── useSectors.ts
│   ├── useRankings.ts
│   └── useScanStream.ts     # EventSource SSE hook
├── lib/
│   ├── api.ts               # fetch helpers, base URL constant
│   └── format.ts            # fmt helpers
├── store/
│   └── useAppStore.ts       # Zustand store
├── types/
│   └── api.ts               # All TypeScript interfaces from section 4.1
└── tailwind.config.ts
```

---

## 10. Tailwind Config Extensions

```typescript
// tailwind.config.ts
module.exports = {
  theme: {
    extend: {
      fontFamily: {
        mono: ['"IBM Plex Mono"', 'Courier New', 'monospace'],
      },
      colors: {
        terminal: {
          bg:      '#0A0A0A',
          surface: '#111111',
          elevated:'#161616',
          border:  '#1E1E1E',
          amber:   '#FF8C00',
          cyan:    '#00B4D8',
          green:   '#00FF87',
          red:     '#FF3B30',
          yellow:  '#FFD60A',
          dim:     '#6B6B6B',
          body:    '#C8C8C8',
        },
      },
      borderRadius: { DEFAULT: '0', sm: '0', md: '0', lg: '0', xl: '0', full: '9999px' },
    },
  },
}
```

---

## 11. Accessibility & Performance Notes

- All interactive elements must have `tabIndex` and keyboard navigation
- Scan progress overlay must trap focus while open
- Use `aria-live="polite"` on the scan progress percentage
- `prefers-reduced-motion`: disable the progress bar fill animation
- `React.memo` all table rows — TanStack Virtual handles DOM recycling
- No `useEffect` data fetching — all data via TanStack Query
- SSE `EventSource` must be cleaned up in the hook's cleanup function to prevent memory leaks on unmount

---

## 12. `globals.css` Skeleton

```css
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500;600&display=swap');

:root {
  --col-bg:      #0A0A0A;
  --col-surface: #111111;
  --col-border:  #1E1E1E;
  --col-amber:   #FF8C00;
  --col-cyan:    #00B4D8;
  --col-buy:     #00FF87;
  --col-fund:    #FFD60A;
  --col-tech:    #00B4D8;
  --col-fail:    #FF3B30;
  --col-green:   #00C853;
  --col-red:     #FF3B30;
  --col-dim:     #6B6B6B;
  --col-body:    #C8C8C8;
}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html, body { background: var(--col-bg); color: var(--col-body); font-family: 'IBM Plex Mono', monospace; font-size: 12px; }

/* Section separator — amber rule */
.terminal-rule {
  border: none;
  border-top: 1px solid var(--col-amber);
  opacity: 0.4;
  margin: 8px 0;
}

/* Verdict pill */
.pill-buy  { background: var(--col-buy);  color: #000; padding: 1px 6px; font-size: 10px; font-weight: 600; }
.pill-fund { background: var(--col-fund); color: #000; padding: 1px 6px; font-size: 10px; font-weight: 600; }
.pill-tech { background: var(--col-tech); color: #000; padding: 1px 6px; font-size: 10px; font-weight: 600; }
.pill-fail { background: var(--col-fail); color: #fff; padding: 1px 6px; font-size: 10px; font-weight: 600; }

/* Table base */
table { border-collapse: collapse; width: 100%; }
th    { color: var(--col-amber); font-size: 10px; text-align: right; padding: 4px 6px; border-bottom: 1px solid var(--col-border); cursor: pointer; user-select: none; }
th:first-child, td:first-child { text-align: left; }
td    { font-size: 11px; padding: 3px 6px; text-align: right; border-bottom: 1px solid var(--col-border); white-space: nowrap; }
tr:hover td { background: #161616; }

/* Score bar (inline block chars) */
.score-bar { letter-spacing: -1px; }
```
