# Fundamental Data Adapter Contract

This document specifies every input the Alpha-Stream fundamentals pipeline consumes, exactly enough detail to swap the data source without touching the scoring math. Hand this to the agent that will implement the new adapter.

---

## 1. High-Level Flow

```
┌─────────────────────────────────────────────────────────────┐
│  app/backend/main.py  :  _run_scan(universe_key)            │
│  ─ Stage 0/1/2 once per scan (regime/macro/sectors)         │
│  ─ Fetch SPY history once  (fetch_spy_close_1y)             │
│  ─ asyncio.Semaphore(8) over tickers:                       │
│      analyze_ticker(ticker, composite_risk, macro,          │
│                     sector_scores, universe, spy_history)   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  app/backend/pipeline.py  :  analyze_ticker(...)            │
│  Calls 5 cached fetchers:                                   │
│    get_history(ticker, "1y")    → pd.DataFrame              │
│    get_financials(ticker)       → pd.DataFrame              │
│    get_balance_sheet(ticker)    → pd.DataFrame              │
│    get_cashflow(ticker)         → pd.DataFrame              │
│    get_info(ticker)             → dict[str, Any]            │
│  Then runs Stage 3 (fundamentals) + Stage 4 (technical).    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  src/data/yfinance_cache.py                                 │
│  ─ Disk-backed TTL cache for the 5 calls above              │
│  ─ TTL: 4h prices, 24h fundamentals                         │
│  ─ Storage: .cache/ticker/<safe-ticker>/<field>.{parquet|json}│
│  ─ Cache miss → currently calls yfinance.Ticker(t).<prop>   │
│   ↑↑↑  THIS IS THE LAYER YOU WILL REPLACE  ↑↑↑              │
└─────────────────────────────────────────────────────────────┘
```

**Replacement target:** the five getter functions in `src/data/yfinance_cache.py` (`get_history`, `get_financials`, `get_balance_sheet`, `get_cashflow`, `get_info`). Replace the yfinance call inside each; keep the disk-cache wrapper, the return shape, and the function signature.

---

## 2. The Five Data Objects — Required Shapes

### 2.1 `get_history(ticker, period="1y") → pandas.DataFrame`

**Purpose:** 1 year of daily OHLCV.

| Attribute | Requirement |
|-----------|-------------|
| Index | `DatetimeIndex`, daily frequency, ascending (oldest → newest). Timezone OK or naive — code never asserts. |
| Required columns | `Close`, `High`, `Low` (must exist) |
| Optional column | `Volume` (read defensively via `df.get("Volume", ...)` in one strategy) |
| Length | ≥ 60 rows for usable analysis. ≥ 30 rows minimum for SPY beta calc. Empty DF triggers `{"ok": False, "error": "No price history"}`. |
| Cell type | `float64` for OHLCV |
| NaN handling | The pipeline runs `dropna(subset=["Close","High","Low"])` before use. Producer may include NaN. |
| Units | Native price units (USD for `AAPL`, THB for `PTTEP.BK`, etc.). No splits/dividend adjustment assumed beyond what yfinance returns. |
| Period semantics | `period="1y"` = approximately last 252 trading days. Calendar 1Y is acceptable. |

**Consumers:**
- `analyze_ticker` reads `history["Close"]` for: current price, return series, returns → Sortino/CVaR.
- `_enrich_info` correlates `history["Close"].pct_change()` against SPY closes for `beta_vs_spy`.
- `run_technical_analysis(df=history)` reads `Close`, `High`, `Low`, and `Volume`.

---

### 2.2 `get_info(ticker) → dict[str, Any]`

**Purpose:** Single-snapshot key-value bag of equity metadata. This is the slowest call from Yahoo today, and the most "schema-loose" — many fields are missing for non-US tickers.

#### Keys actually consumed (exhaustive list — anything else can be omitted)

| Key | Type | Units | Read by | Notes |
|-----|------|-------|---------|-------|
| `marketCap` | float\|None | currency (native) | `calculate_wacc`, `calculate_altman_z`, `_enrich_info` | **Often missing for .BK/.HK** — code falls back to `sharesOutstanding × price` then `enterpriseValue`. |
| `sharesOutstanding` | float\|None | shares | `_enrich_info`, `_resolve_market_cap` | Fallback for market cap. |
| `impliedSharesOutstanding` | float\|None | shares | `_enrich_info`, `_resolve_market_cap` | Used if `sharesOutstanding` absent. |
| `currentPrice` | float\|None | price (native) | `_resolve_market_cap` | First price fallback. |
| `regularMarketPrice` | float\|None | price (native) | `_resolve_market_cap` | Second fallback. |
| `previousClose` | float\|None | price (native) | `_resolve_market_cap` | Third fallback. |
| `enterpriseValue` | float\|None | currency | `_resolve_market_cap`, `calculate_altman_z` | Last-resort market-cap proxy (overstates by net debt). |
| `beta` | float\|None | dimensionless | `analyze_ticker` (Stage 3 input), `calculate_wacc` | NaN handled — defaults to 1.0. For .BK tickers this is vs SET50 not SPY. |
| `forwardPE` | float\|None | dimensionless | `providers.fetch_all_data` (CLI/diagnostics only — not used by scan) | Display only. |
| `debtToEquity` | float\|None | percent or ratio | `providers.fetch_all_data` (CLI only) | Display only. |

#### Keys the code injects/writes back into `info`

These are computed by `_enrich_info` and stored in the dict so downstream code can read them:
- `marketCap` — overwritten when missing/zero
- `beta_vs_spy` — added, beta computed vs SPY returns (clipped to [-1, 4])

**For your adapter:** populate at least `marketCap` (or one of the fallbacks) and `beta`. Everything else is non-blocking.

---

### 2.3 `get_financials(ticker) → pandas.DataFrame` (Income Statement)

**Shape:** rows = metric names (strings), columns = reporting period dates, **most-recent column first** (`iloc[0]` is the latest annual period).

**How values are read** — every fundamental call goes through this helper:

```python
def get_fin_val(df, keys: list, default=0.0):
    # Tries each key in order.
    # 1. Exact match after stripping whitespace from df.index
    # 2. Case-insensitive + whitespace-collapsed match
    #    (e.g. "OperatingIncome" matches "Operating Income")
    # Returns float(df.loc[key].iloc[0])  — first column = latest period
```

So your DataFrame can use spaced or PascalCase row names interchangeably. The first matched key in the list wins.

#### Row names looked up (with fallback synonyms)

| Logical metric | Fallback key list (first match wins) | Units | Read by |
|----------------|--------------------------------------|-------|---------|
| Net Income | `'Net Income'`, `'Net Income Common Stockholders'`, `'NetIncome'`, `'NetIncomeCommonStockholders'` | currency | `calculate_sloan_ratio`, `calculate_fcf_quality` |
| EBIT | `'EBIT'`, `'Ebit'`, `'Operating Income'`, `'OperatingIncome'`, `'Income From Operations'`, `'IncomeFromOperations'`, `'Operating Profit'`, `'OperatingProfit'` | currency | `calculate_roic`, `calculate_altman_z` |
| Gross Profit (reconstruction fallback only) | `'Gross Profit'`, `'GrossProfit'` | currency | `calculate_roic` (only when EBIT missing) |
| Operating Expense (reconstruction fallback only) | `'Operating Expense'`, `'OperatingExpense'`, `'Total Operating Expenses'`, `'TotalOperatingExpenses'` | currency | `calculate_roic` (only when EBIT missing — EBIT ≈ Gross Profit − Operating Expense) |
| Pretax Income | `'Pretax Income'`, `'PretaxIncome'` | currency | `calculate_wacc`, `calculate_roic` (for tax-rate derivation) |
| Tax Provision | `'Tax Provision'`, `'TaxProvision'` | currency | `calculate_wacc`, `calculate_roic` |
| Interest Expense | `'Interest Expense'`, `'InterestExpense'` | currency, positive number (code takes `abs()`) | `calculate_wacc` |
| Total Revenue | `'Total Revenue'`, `'TotalRevenue'`, `'Revenue'`, `'Net Revenue'`, `'NetRevenue'` | currency | `calculate_altman_z`, `calculate_asset_turnover`, `calculate_ccc` |
| Cost of Revenue | `'Cost Of Revenue'`, `'CostOfRevenue'`, `'Cost Of Goods Sold'`, `'CostOfGoodsSold'` | currency | `calculate_ccc` |

**Tax-rate derivation logic:**
```
tax_rate = clip(tax_provision / pretax_income, 0, 0.35)  if pretax > 0
         = 0.21                                          otherwise
```

---

### 2.4 `get_balance_sheet(ticker) → pandas.DataFrame`

Same shape as financials. Rows = balance-sheet item names; columns = period dates, most-recent first.

| Logical metric | Fallback key list | Units | Read by |
|----------------|------------------|-------|---------|
| Total Assets | `'Total Assets'`, `'TotalAssets'` | currency | `calculate_sloan_ratio`, `calculate_altman_z`, `calculate_asset_turnover` |
| Total Debt | `'Total Debt'`, `'TotalDebt'`, `'Long Term Debt'`, `'LongTermDebt'` | currency | `calculate_roic`, `calculate_wacc` |
| Stockholders Equity | `'Stockholders Equity'`, `'StockholdersEquity'`, `'Total Stockholder Equity'`, `'TotalStockholderEquity'`, `'Total Equity Gross Minority Interest'`, `'TotalEquityGrossMinorityInterest'` | currency | `calculate_roic`, `calculate_altman_z` (when no `marketCap` available — book-equity proxy) |
| Cash & Equivalents | `'Cash And Cash Equivalents'`, `'CashAndCashEquivalents'`, `'Cash Cash Equivalents And Short Term Investments'`, `'CashCashEquivalentsAndShortTermInvestments'`, `'Cash'` | currency | `calculate_roic` (subtracted from invested capital) |
| Retained Earnings | `'Retained Earnings'`, `'RetainedEarnings'` | currency | `calculate_altman_z` (X2) |
| Working Capital | `'Working Capital'`, `'WorkingCapital'` | currency | `calculate_altman_z` (X1) — defaults to 0 if missing |
| Total Liabilities | `'Total Liabilities Net Minority Interest'`, `'TotalLiabilitiesNetMinorityInterest'`, `'Total Liabilities'`, `'TotalLiabilities'` | currency | `calculate_altman_z` (X4 denominator) |
| Inventory | `'Inventory'`, `'Inventories'` | currency | `calculate_ccc` |
| Accounts Receivable | `'Accounts Receivable'`, `'AccountsReceivable'`, `'Net Receivables'`, `'NetReceivables'` | currency | `calculate_ccc` |
| Accounts Payable | `'Accounts Payable'`, `'AccountsPayable'` | currency | `calculate_ccc` |

---

### 2.5 `get_cashflow(ticker) → pandas.DataFrame`

Same shape. Rows = cashflow line items; columns = period dates, most-recent first.

| Logical metric | Fallback key list | Units | Read by |
|----------------|------------------|-------|---------|
| Cash Flow from Operations (CFO) | `'Cash Flow From Continuing Operating Activities'`, `'Operating Cash Flow'`, `'CashFlowFromContinuingOperatingActivities'`, `'OperatingCashFlow'` | currency, signed (positive = inflow) | `calculate_sloan_ratio` (NI − CFO), `calculate_fcf_quality` (FCF = CFO − CapEx) |
| Capital Expenditure | `'Capital Expenditure'`, `'CapitalExpenditure'`, `'Purchase Of PPE'`, `'PurchaseOfPPE'`, `'Capital Expenditures'`, `'CapitalExpenditures'` | currency — code applies `abs()` so sign doesn't matter | `calculate_fcf_quality` |
| Interest Paid (fallback for income statement) | `'Interest Paid Supplementals'`, `'Interest Expense'`, `'InterestPaidSupplementals'` | currency, code takes `abs()` | `calculate_wacc` (only when income-statement Interest Expense missing) |

---

## 3. Per-Metric Data Dependency Map

For your adapter, this tells you exactly what to wire for each Alpha-Score input.

| Function | Inputs needed | Output |
|----------|--------------|--------|
| `calculate_roic(financials, balance_sheet)` | EBIT + (Pretax, Tax Provision) → tax rate; Total Debt, Stockholders Equity, Cash | ROIC (decimal, e.g. 0.142) |
| `calculate_wacc(info, financials, balance_sheet, cashflow)` | `info.marketCap` (with fallbacks), Total Debt, `info.beta`, Pretax, Tax Provision, Interest Expense | WACC (decimal) |
| `calculate_sloan_ratio(financials, cashflow, balance_sheet)` | Net Income, CFO, Total Assets | Sloan (decimal) |
| `calculate_altman_z(financials, balance_sheet, info)` | Total Revenue, EBIT, Total Assets, Retained Earnings, Working Capital, Total Liabilities, `info.marketCap` or `info.enterpriseValue` | Z-score (raw) |
| `calculate_fcf_quality(financials, cashflow)` | Net Income (from financials), CFO + CapEx (from cashflow) | FCF/NI ratio (decimal) |
| `calculate_asset_turnover(financials, balance_sheet)` | Revenue, Total Assets | Decimal |
| `calculate_ccc(financials, balance_sheet)` | Revenue, COGS, Inventory, A/R, A/P | Days (signed) |
| `calculate_rolling_sortino(returns)` | 1Y daily returns (from history Close) | Annualised ratio |
| `calculate_cvar_95(returns)` | Same | Daily expected shortfall (positive number = magnitude) |
| `calculate_beta(asset_returns, benchmark_returns)` | Returns vs benchmark | Decimal, clipped [-1, 4] |

---

## 4. The Cache Wrapper Contract — `src/data/yfinance_cache.py`

Five public getters, all idempotent, all safe to call concurrently on different tickers. The cache layer is **agnostic to the source** — only the inner fetch line changes.

```python
def get_history(ticker: str, period: str = "1y",
                ttl_seconds: int = 14400) -> pd.DataFrame: ...
def get_financials(ticker: str,
                   ttl_seconds: int = 86400) -> pd.DataFrame: ...
def get_balance_sheet(ticker: str,
                      ttl_seconds: int = 86400) -> pd.DataFrame: ...
def get_cashflow(ticker: str,
                 ttl_seconds: int = 86400) -> pd.DataFrame: ...
def get_info(ticker: str,
             ttl_seconds: int = 86400) -> dict: ...
```

**Contract for each:**
1. If `.cache/ticker/<safe>/<field>.{parquet|json}` exists AND `mtime < ttl_seconds` → load and return.
2. Else fetch from upstream source.
3. If the result is non-empty, atomically write to disk (parquet for DataFrames, JSON for dict).
4. Return the result (cached or fresh) — never raise on cache I/O errors.
5. **Empty / null upstream is allowed** — return `pd.DataFrame()` or `{}` respectively. The pipeline handles empty inputs (each metric defaults to 0 on missing rows).

`get_info` writes via a JSON sanitiser that converts numpy scalars and NaN/Inf to native types — your adapter only needs to return a plain `dict` of JSON-friendly primitives.

**Ticker name sanitisation** for the cache directory: `[^A-Za-z0-9._-]` → `_` (e.g. `^GSPC` → `_GSPC`). Tickers passed *into* your fetch can be in their native form.

---

## 5. The "Replacement Adapter" Checklist

To swap in a new source cleanly, the new agent must:

1. **Implement five fetchers** with the exact signatures above. Return shape must match §2.1–2.5.
2. **Match row-name expectations.** Either:
   - (a) Return DataFrames whose index strings match at least one of the fallback keys for each metric (e.g. `"Net Income"`, `"EBIT"`, `"Total Assets"`, `"Cash Flow From Continuing Operating Activities"`, etc.), OR
   - (b) Extend `get_fin_val` in `src/agents/calculator.py` with the new source's row names. The matcher is already case-insensitive and whitespace-collapsing — just append the new key to each fallback list.
3. **Match column convention.** Most-recent reporting period at column index 0 (`.iloc[0]`).
4. **Populate `info.marketCap`** (or `sharesOutstanding` + `currentPrice` so it can be reconstructed). Without one of these, WACC and Altman Z degrade to defaults.
5. **Populate `info.beta`** if available. Defaults to 1.0 otherwise — usable but less accurate.
6. **history DataFrame** must have `Close`, `High`, `Low` columns and a `DatetimeIndex`. Include `Volume` if the source provides it.
7. **Units consistency.** Financial statement values must be in the same currency as the share price (so `marketCap = shares × price` works as a fallback). If your source reports in millions or thousands while prices are in units, convert.
8. **Signed conventions:**
   - CFO: positive = cash inflow
   - CapEx: code takes `abs()`, so either sign works
   - Interest Expense: code takes `abs()`, either sign works
   - All other line items: standard accounting sign
9. **Currency.** The pipeline does no FX conversion — keep statements and prices in one consistent currency per ticker.
10. **TTLs.** Keep the 4h price / 24h fundamentals defaults unless the new source has different freshness semantics.

---

## 6. Things You Do NOT Need to Reproduce

These are yfinance-specific or already cached/computed elsewhere:

- `stock.history(period="3y")` — only used by the (unused) CLI path in `providers.fetch_all_data`.
- yfinance's lazy property caching within a single `Ticker` instance — irrelevant once you control the fetch layer.
- `info.forwardPE`, `info.debtToEquity` — read only in `providers.fetch_all_data` (display, not scoring).
- `info.shortName` / `info.longName` — never read by the scan path.
- Sector mapping — that comes from `src/universes/` (`get_sector_for_ticker`), not from `info.sector`.

---

## 7. Quick Verification After Swap

After wiring the new source, run a one-ticker smoke test:

```python
import pandas as pd
from src.data.yfinance_cache import (
    get_history, get_financials, get_balance_sheet, get_cashflow, get_info,
)
t = "AAPL"  # or your test ticker
h  = get_history(t, "1y")
fi = get_financials(t)
bs = get_balance_sheet(t)
cf = get_cashflow(t)
nf = get_info(t)

assert {"Close", "High", "Low"}.issubset(h.columns)
assert isinstance(h.index, pd.DatetimeIndex)
assert len(h) >= 60

from src.agents.calculator import (
    calculate_roic, calculate_wacc, calculate_sloan_ratio,
    calculate_altman_z, calculate_fcf_quality, calculate_rolling_sortino,
)
roic  = calculate_roic(fi, bs)
wacc  = calculate_wacc(nf, fi, bs, cf)
sloan = calculate_sloan_ratio(fi, cf, bs)
fcfq  = calculate_fcf_quality(fi, cf)
z     = calculate_altman_z(fi, bs, nf)
sort  = calculate_rolling_sortino(h["Close"].pct_change().dropna())
print(roic, wacc, sloan, fcfq, z, sort)
# None of these should silently return 0.0 — if they do, a required row is missing.
```

Then run a full scan: `POST /api/scan/start?universe=SP500_SAMPLE` and inspect a few rows. If the AlphaScore distribution looks plausibly similar to yfinance-sourced results, the adapter is correct.

---

This is everything that touches fundamental data. The math layer (`calculator.py`, `generate_alpha_score`, the scoring tiers in both Python and TypeScript) is fully insulated from the data source — once your adapter speaks the schema above, no downstream code needs to change.
