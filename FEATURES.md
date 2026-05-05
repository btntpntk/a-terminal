# FEATURES.md — Alpha-Stream Feature Reference

This document covers every user-facing feature and core functional module, including the exact formulas and algorithms extracted from the implementation.

---

## Table of Contents

1. [Multi-Stage Stock Ranking Pipeline](#1-multi-stage-stock-ranking-pipeline)
   - [Stage 0 — Market Regime Detection](#stage-0--market-regime-detection)
   - [Stage 1 — Global Macro Analysis](#stage-1--global-macro-analysis)
   - [Stage 2 — Sector Screening](#stage-2--sector-screening)
   - [Stage 3 — Fundamental Scoring](#stage-3--fundamental-scoring)
   - [Stage 4 — Technical Strategy Selection](#stage-4--technical-strategy-selection)
   - [Composite Ranking Score](#composite-ranking-score)
2. [Normal Walk-Forward Backtesting](#2-normal-walk-forward-backtesting)
3. [Monte Carlo Integrated Backtesting](#3-monte-carlo-integrated-backtesting)
4. [Portfolio Optimizers](#4-portfolio-optimizers)
5. [Trading Strategies](#5-trading-strategies)
6. [HMM Regime Detection](#6-hmm-regime-detection)
7. [Performance Metrics](#7-performance-metrics)

---

## 1. Multi-Stage Stock Ranking Pipeline

**Usage:** Launch from the frontend Rankings tab, or via API:

```bash
# Start an async scan job
curl -X POST "http://localhost:8000/api/scan/start?universe=SP500_SAMPLE"
# → {"job_id": "abc123"}

# Stream live progress
curl "http://localhost:8000/api/scan/stream/abc123"

# Fetch final ranked results
curl "http://localhost:8000/api/rankings/SP500_SAMPLE"
```

**Implementation:** [`app/backend/pipeline.py`](app/backend/pipeline.py), [`app/backend/main.py`](app/backend/main.py)

---

### Stage 0 — Market Regime Detection

**File:** [`src/agents/market_risk.py`](src/agents/market_risk.py)

**API:** `GET /api/regime` (TTL 15 min)

#### Logic

Three independent layers are each scored 0–100 and combined into a single composite risk score.

**Layer 1 — Regime (weight 45%)**

| Indicator | Signal |
|-----------|--------|
| SPX vs 200-DMA | Risk rises when price is below its long-term trend |
| 2Y/10Y yield curve | Inverted curve (2Y > 10Y) signals recession risk |
| HY Credit OAS | Wider spread = elevated credit stress |

**Layer 2 — Fragility (weight 35%)**

| Indicator | Signal |
|-----------|--------|
| Breadth: % of S&P 500 stocks above 50-DMA | Narrow breadth signals underlying weakness |
| RSP/SPY ratio | Equal-weight / cap-weight divergence indicates participation |

**Layer 3 — Trigger (weight 20%)**

| Indicator | Signal |
|-----------|--------|
| VIX level | Absolute fear gauge |
| VIX term structure | Backwardation (short > long) = elevated near-term fear |

**Composite score formula:**

$$\text{Composite Risk} = 0.45 \times L_{\text{regime}} + 0.35 \times L_{\text{fragility}} + 0.20 \times L_{\text{trigger}}$$

**Position scale output:**

| Composite Risk | Position Scale |
|---------------|---------------|
| $\leq 30$ | 100% — Full Kelly |
| $\leq 45$ | 80% |
| $\leq 60$ | 60% |
| $\leq 74$ | 40% |
| $> 74$ | 25% — Capital Preservation |

---

### Stage 1 — Global Macro Analysis

**File:** [`src/agents/global_macro.py`](src/agents/global_macro.py)

**API:** `GET /api/macro` (TTL 30 min)

#### Logic

Eight cross-asset signals are scored individually (0–100) and combined into a **composite macro risk** score plus a **Growth/Inflation quadrant**.

**Weighted signal formula:**

$$\text{Macro Risk} = \sum_{i=1}^{8} w_i \times S_i$$

| Signal | Ticker | Weight $w_i$ | Rationale |
|--------|--------|-------------|-----------|
| Real Yield | ^TNX + TIP | 20% | Equity valuation regime |
| DXY | DX-Y.NYB | 20% | EM capital flow pressure |
| EM Flows | EEM vs SPY | 15% | Foreign fund direction |
| Copper | HG=F | 15% | Global growth barometer |
| Crude Oil | CL=F | 12% | Inflation / cost-push |
| China Pulse | MCHI + KWEB | 10% | Thailand's largest trading partner |
| USD/THB | USDTHB=X | 5% | Direct Thai FX signal |
| Gold | GC=F | 3% | Risk-off hedge |

**Growth/Inflation Quadrant:**

| Quadrant | Conditions | Portfolio Posture |
|----------|-----------|-------------------|
| GOLDILOCKS | Growth ↑, Inflation ↓ | Max risk, overweight equities |
| OVERHEAT | Growth ↑, Inflation ↑ | Trim duration, add commodities |
| STAGFLATION | Growth ↓, Inflation ↑ | Defensive, gold, short EM |
| RECESSION_RISK | Growth ↓, Inflation ↓ | Capital preservation |

Macro sector adjustments of ±8 pts are applied to every downstream alpha score.

---

### Stage 2 — Sector Screening

**File:** [`src/agents/sector_screener.py`](src/agents/sector_screener.py)

**API:** `GET /api/sectors/{universe}` (TTL 30 min)

#### Logic

Each sector is scored across four dimensions against the benchmark. Sectors below the gate threshold are flagged *avoid*.

**Sector score formula:**

$$\text{SectorScore} = 0.35 \times M + 0.25 \times RS + 0.20 \times B + 0.20 \times V + \Delta_{\text{macro}}$$

Where:

| Component | Variable | Description |
|-----------|----------|-------------|
| Momentum | $M$ | 20-day sector return vs benchmark return |
| Relative Strength | $RS$ | Z-score of sector RS vs its 60-day rolling mean |
| Breadth | $B$ | % of sector members with price above 50-DMA |
| Volume Flow | $V$ | OBV-style accumulation (close × volume direction) |
| Macro Adjustment | $\Delta_{\text{macro}}$ | ±8 pts from Stage 1 quadrant output |

---

### Stage 3 — Fundamental Scoring

**File:** [`src/agents/calculator.py`](src/agents/calculator.py)

#### Logic

All metrics are computed in a single pass over yfinance financial data. The **Alpha Score** (0–100) is a weighted composite of five fundamental dimensions.

**Fundamental metrics:**

| Metric | Formula | Threshold |
|--------|---------|-----------|
| ROIC | $\frac{\text{NOPAT}}{\text{Invested Capital}}$ | — |
| WACC | CAPM + debt cost ($R_f = 4.3\%$, $ERP = 5.0\%$) | — |
| Economic Moat | $\text{ROIC} - \text{WACC}$ | $> 10\%$ = wide moat |
| Sloan Ratio | $\frac{\text{NI} - \text{CFO}}{\text{Total Assets}}$ | $> 0.10$ = earnings quality red flag |
| FCF Quality | $\frac{\text{FCF}}{\text{Net Income}}$ | $< 0.60$ = concern |
| Altman Z-Score | $1.2X_1 + 1.4X_2 + 3.3X_3 + 0.6X_4 + 1.0X_5$ | $< 1.81$ = distress |
| CVaR 95% | Expected tail loss at 95th percentile | — |
| Rolling Sortino | $\frac{\bar{r} - r_f}{\sigma_{\text{downside}}}$ | — |
| Beta | $\frac{\text{Cov}(r_i, r_m)}{\text{Var}(r_m)}$ | Winsorised to $[-1, 4]$ |
| Cash Conversion Cycle | $DIO + DSO - DPO$ | — |

**Altman Z-Score variables:**

$$Z = 1.2 X_1 + 1.4 X_2 + 3.3 X_3 + 0.6 X_4 + 1.0 X_5$$

| Variable | Formula |
|----------|---------|
| $X_1$ | Working Capital / Total Assets |
| $X_2$ | Retained Earnings / Total Assets |
| $X_3$ | EBIT / Total Assets |
| $X_4$ | Market Cap / Total Liabilities |
| $X_5$ | Revenue / Total Assets |

**Alpha Score:**

$$\text{AlphaScore} = 0.30 \times E + 0.20 \times Q + 0.20 \times S + 0.20 \times R + 0.10 \times F$$

| Dimension | Variable | Metric |
|-----------|----------|--------|
| Economic Value | $E$ | ROIC − WACC (moat score) |
| Earnings Quality | $Q$ | Inverse Sloan Ratio |
| Survival | $S$ | Altman Z (normalised) |
| Risk-Adjusted Return | $R$ | Rolling Sortino |
| FCF Quality | $F$ | FCF / Net Income |

High-beta stocks ($\beta > 1.5$) receive a regime penalty when composite risk $> 60$.

---

### Stage 4 — Technical Strategy Selection

**File:** [`src/agents/technical.py`](src/agents/technical.py)

#### Logic

The strategy with the highest rolling Sharpe ratio over recent history is selected per ticker.

**Strategy families:**

| Family | Conditions | Entry logic |
|--------|-----------|-------------|
| MOMENTUM | RSI > 60, MACD +, price above upper BB | Buy pullback to 20-MA |
| MEAN_REVERSION | RSI < 35, MACD −, price below lower BB | Fade to mid-BB |
| BREAKOUT | ATR expansion, volume spike, range break | Buy confirmed break |

**Outputs per ticker:**
- Entry price
- Take-profit price
- Stop-loss price
- ATR-14
- Risk:Reward ratio (gate: $\geq 1.5\times$)
- Signal strength score 0–100 (gate: $\geq 40$)

---

### Composite Ranking Score

$$\text{RankScore} = 0.45 \times \text{Alpha} + 0.30 \times \text{SignalStrength} + 0.15 \times \text{SectorScore} + 0.10 \times \text{RRScore}$$

**Verdict matrix:**

| Fund Gate (Stage 3) | Tech Gate (Stage 4) | Verdict |
|:---:|:---:|---------|
| ✓ | ✓ | **BUY** |
| ✓ | ✗ | FUND_ONLY |
| ✗ | ✓ | TECH_ONLY |
| ✗ | ✗ | FAIL |

---

## 2. Normal Walk-Forward Backtesting

**Files:** [`src/backtesting/engine.py`](src/backtesting/engine.py), [`src/backtesting/metrics.py`](src/backtesting/metrics.py)

**API:** `POST /api/backtest/run`

**UI:** BacktestWidget.tsx → Normal mode

### Usage

```bash
curl -X POST http://localhost:8000/api/backtest/run \
  -H "Content-Type: application/json" \
  -d '{
    "tickers": ["AAPL", "MSFT", "GOOGL"],
    "benchmark_ticker": "SPY",
    "strategy": "MomentumStrategy",
    "optimizer": "InverseVolatilityOptimizer",
    "initial_capital": 1000000,
    "in_sample_window": 252,
    "out_of_sample_window": 63,
    "max_stop_loss_pct": 0.05,
    "transaction_cost_pct": 0.001
  }'
```

### Fold Structure

The backtest uses non-overlapping out-of-sample (OOS) windows. Requires a minimum of **3 complete folds**.

```
Fold 1: train [0 : IS],        test [IS       : IS+OOS]
Fold 2: train [OOS : IS+OOS],  test [IS+OOS   : IS+2×OOS]
Fold 3: train [2×OOS : ...],   test [IS+2×OOS : IS+3×OOS]
```

**Minimum data requirement:**

$$N_{\min} = IS + 3 \times OOS$$

where $IS = 252$ trading days (default) and $OOS = 63$ trading days (default).

### Logic (bar-by-bar simulation)

1. **Signals are generated upfront** on the full price history using the chosen strategy (`generate_signals()` returns a DataFrame of values in $\{+1, 0, -1\}$).
2. Each test bar executes in this order:
   1. **Stop-loss check** — for every open position, compute PnL:
      $$\text{PnL\%} = \left(\frac{P_t}{P_{\text{entry}}} - 1\right) \times d$$
      where $d \in \{+1, -1\}$ is the position direction. If $\text{PnL\%} \leq -\text{MaxSL\%}$, the signal for that ticker is forced to 0 and the ticker is blocked from re-entry until its signal resets.
   2. **Compute target weights** via the selected optimizer.
   3. **Transaction costs** — proportional to portfolio turnover:
      $$\text{Cost} = \sum_i |w_i^{\text{new}} - w_i^{\text{old}}| \times c$$
      where $c$ is the cost rate (default 0.1%).
   4. **Daily P&L:**
      $$r_{\text{portfolio}} = \sum_i w_i \times r_i - \text{Cost}$$
      $$E_{t+1} = E_t \times (1 + r_{\text{portfolio}})$$

### Returns

`BacktestResult` contains:
- `equity_curve` — DatetimeIndex → portfolio value
- `benchmark_curve` — rebased to `initial_capital`
- `trade_log` — entry/exit/direction/return_pct/pnl/stop_triggered per trade
- `fold_returns` — per-fold equity series
- `metrics` — full KPI dict (see [Performance Metrics](#7-performance-metrics))
- `weights_history` — end-of-day target weights (DatetimeIndex × ticker)

---

## 3. Monte Carlo Integrated Backtesting

**Files:** [`src/backtesting/mc_engine.py`](src/backtesting/mc_engine.py)

**API:** `POST /api/backtest/run-mc`

**UI:** BacktestWidget.tsx → Monte Carlo Integrated mode

### Usage

```bash
curl -X POST http://localhost:8000/api/backtest/run-mc \
  -H "Content-Type: application/json" \
  -d '{
    "buy_strategy": "MomentumStrategy",
    "sell_strategy": "TP_SL",
    "tickers": ["AAPL", "MSFT"],
    "benchmark_ticker": "SPY",
    "initial_capital": 1000000,
    "n_simulations": 1000,
    "holding_days": 10,
    "tp_quantile": 0.80,
    "sl_quantile": 0.10,
    "shock_distribution": "student_t",
    "sizing_method": "risk_parity_sl",
    "n_folds": 4
  }'
```

### Volatility Estimation (no lookahead)

Called at each signal bar. Only data up to and including the current bar is used — enforced by a hard assertion.

**EWMA volatility (default):**

$$\hat{\sigma}^2_{\text{daily}} = \text{EWMA}(r_t^2,\; \text{halflife}=h)$$

**Rolling standard deviation (alternative):**

$$\hat{\sigma}_{\text{daily}} = \text{std}(r_t,\; \text{window}=L)$$

**Annualisation:**

$$\sigma_{\text{annual}} = \text{clip}\!\left(\hat{\sigma}_{\text{daily}} \times \sqrt{252},\; \sigma_{\text{floor}},\; \sigma_{\text{cap}}\right)$$

### GBM / Student-t Path Simulation

For each candidate entry, $N$ price paths of length $H$ (holding days) are simulated:

**GBM with Itô correction:**

$$\ln S_{t+1} = \ln S_t + \underbrace{\left(\mu - \frac{\sigma^2}{2}\right) \Delta t}_{\text{drift}} + \sigma \sqrt{\Delta t} \cdot z_t$$

where $\Delta t = \frac{1}{252}$ and $z_t$ is drawn from either $\mathcal{N}(0,1)$ or Student-$t(\nu)$.

**Take-Profit and Stop-Loss levels** are set from the distribution of simulated terminal prices:

$$\text{TP}_{\text{raw}} = Q_{q_{\text{tp}}}(\{S_H^{(k)}\}_{k=1}^N)$$

$$\text{SL}_{\text{raw}} = Q_{q_{\text{sl}}}(\{S_H^{(k)}\}_{k=1}^N)$$

$$\text{SL}_{\text{applied}} = \max\!\left(\text{SL}_{\text{raw}},\; S_0 \times (1 - \text{MaxSL\%})\right)$$

**Risk:Reward ratio:**

$$RR = \frac{TP - S_0}{S_0 - SL}$$

**Empirical probabilities** are computed from path extrema:

$$P(\text{TP}) = \frac{1}{N} \sum_{k=1}^{N} \mathbf{1}\!\left[\max_t S_t^{(k)} \geq TP\right]$$

$$P(\text{SL}) = \frac{1}{N} \sum_{k=1}^{N} \mathbf{1}\!\left[\min_t S_t^{(k)} \leq SL\right]$$

**Expected Value per share:**

$$EV = P(\text{TP}) \times (TP - S_0) - P(\text{SL}) \times (S_0 - SL)$$

### EV Filters (pre-entry gates)

A candidate entry is rejected unless all three conditions hold:

| Filter | Default |
|--------|---------|
| $RR \geq$ `min_rr_ratio` | 1.5 |
| $P(\text{TP}) \geq$ `min_p_tp` | 0.50 |
| $EV \times \text{shares} \geq$ `min_ev_dollars` | 0.0 |

### Position Sizing

**Method 1 — Risk Parity SL (default):**

$$\text{dollars} = \frac{\text{portfolio} \times \text{acceptable risk pct}}{S_0 - SL} \times S_0$$

**Method 2 — Kelly MC:**

$$f^* = \frac{P(\text{TP}) \times RR - P(\text{SL})}{RR}$$

$$\text{dollars} = f^* \times \text{kelly fraction} \times \text{portfolio}$$

Both methods apply hard caps:

$$\text{dollars} \leq \min\!\left(\text{portfolio} \times w_{\max},\; \text{cash} - \text{cash reserve}\right)$$

**Correlation penalty:** If the maximum absolute rolling correlation between the new ticker and any held position exceeds the threshold, position size is scaled down:

$$\text{dollars}_{\text{adj}} = \text{dollars} \times (1 - \text{penalty factor})$$

### Exit Priority (non-negotiable order)

Each bar, exits are evaluated in strict priority:

```
1. STOP_LOSS   — price ≤ SL price  (always checked first)
2. TAKE_PROFIT — price ≥ TP price  (only for sell_strategy ∈ {TP_SL, BOTH})
3. SELL_SIGNAL — strategy signal drops below +1
4. TIME_EXIT   — bars held ≥ max_holding_days
```

**Breakeven trail:** After the position moves $\geq 1R$ in profit, $SL$ is ratcheted up to entry price:

$$SL_{\text{new}} = \max(SL_{\text{current}},\; S_{\text{entry}})$$

### Walk-Forward Fold Structure

The backtest period is divided into $N$ equal-width folds. A purge gap of `purge_days` $\geq$ `holding_days` separates training from testing to prevent leakage through open positions.

**Optional in-fold MC param optimisation:** On each training window, a grid search over `sl_quantile_grid` × `tp_quantile_grid` selects the parameter combination with the highest Sharpe ratio before running the test fold.

### Returns

`MCEngineResult` (superset of `BacktestResult`) adds:
- `mc_trade_details` — per-trade MC fields (sl_raw, sl_applied, tp, rr, p_tp, ev, sigma_annual, exit_reason)
- `mc_aggregate_stats` — mean P(TP), filter fractions, mean σ at entry, breakeven trail activations
- `buyhold_curve` — buy-and-hold baseline (single-ticker mode only)

---

## 4. Portfolio Optimizers

**Files:** [`src/backtesting/optimizers/`](src/backtesting/optimizers/)

All optimizers implement the `PortfolioOptimizer` ABC: `compute_weights(signals, returns_history) → pd.Series`.

### Equal Weight

**File:** [`equal_weight.py`](src/backtesting/optimizers/equal_weight.py)

$$w_i = \frac{1}{N_{\text{long}}} \quad \text{for long signals}, \quad w_i = -\frac{1}{N_{\text{short}}} \quad \text{for short signals}$$

Default for single-ticker mode (full allocation to one asset).

---

### Inverse Volatility

**File:** [`inverse_vol.py`](src/backtesting/optimizers/inverse_vol.py)

Weights are proportional to $1/\sigma_i$ using 20-day realized volatility.

$$w_i = \frac{1/\sigma_i}{\sum_j 1/\sigma_j}$$

---

### Mean-Variance (Max Sharpe)

**File:** [`mean_variance.py`](src/backtesting/optimizers/mean_variance.py)

Maximises the portfolio Sharpe ratio subject to full investment, using 60 days of return history and L2 regularization ($\lambda = 0.1$).

**Objective:**

$$\max_w \frac{\mu^\top w}{\sqrt{w^\top \Sigma w + \epsilon}}$$

**Regularized covariance:**

$$\tilde{\Sigma} = \hat{\Sigma} + \lambda I$$

**Constraints:** $\sum w_i = 1$, $w_i \geq 0$ (long book), solved by SLSQP.

Long and short books are optimised separately.

---

### Risk Parity

**File:** [`risk_parity.py`](src/backtesting/optimizers/risk_parity.py)

Each asset contributes equally to total portfolio variance.

**Risk contribution of asset $i$:**

$$RC_i = w_i \times \frac{(\Sigma w)_i}{w^\top \Sigma w}$$

**Objective:** minimise $\sum_i \left(RC_i - \frac{1}{N}\right)^2$

Solved by SLSQP with regularized covariance ($+10^{-8} I$), 60-day history.

---

### Kelly Criterion (25% fractional)

**File:** [`kelly.py`](src/backtesting/optimizers/kelly.py)

The Kelly fraction per asset is estimated from trailing 60-day returns:

$$f_i^* = \frac{\mu_i}{\sigma_i^2}$$

Applied at 25% of full Kelly with a 40% per-position weight cap:

$$w_i = \min\!\left(0.25 \times f_i^*,\; 0.40\right)$$

The long book is normalised to $\leq 1$ if the sum exceeds 1.

---

## 5. Trading Strategies

**Files:** [`src/strategies/`](src/strategies/)

All strategies implement the `TradingStrategy` ABC: `generate_signals(prices, **kwargs) → DataFrame` with values in $\{+1, 0, -1, \text{NaN}\}$.

### Strategy Map

| Key | Class | Description |
|-----|-------|-------------|
| `MomentumStrategy` | Momentum (12-1) | 12-month minus 1-month return, top quintile long |
| `MeanReversionStrategy` | Mean Reversion | Z-score of 20d return, buy extreme oversold |
| `MovingAverageCrossStrategy` | MA Cross | Long when SMA(20) > SMA(50) |
| `EMACrossStrategy` | EMA Cross | Long when EMA(12) > EMA(26) |
| `RSIStrategy` | RSI | Long when RSI(14) < 30 |
| `VolatilityBreakoutStrategy` | Volatility Breakout | ATR breakout, supports short |
| `DRSIStrategy` | Dual RSI | RSI of stock vs RSI of benchmark |
| `VADERStrategy` | VADER Sentiment | News sentiment via VADER lexicon |
| `PivotPointSupertrendStrategy` | Pivot Point Supertrend | ATR bands anchored to confirmed pivots |
| `LaguerreRSIStrategy` | Laguerre RSI | 4-pole Laguerre filter RSI |
| `HurstChoppinessStrategy` | Hurst Choppiness | Trending vs mean-reverting regime filter |
| `MansfieldMinerviniStrategy` | Mansfield RS + Minervini | RS vs benchmark + Stage 2 trend template |
| `WVFConnorsRSIStrategy` | WVF + Connors RSI | Synthetic VIX + Connors RSI-2 bottom-fishing |
| `ChandelierExitStrategy` | Chandelier Exit | ATR trailing stop direction filter |
| `BankerFundFlowStrategy` | Banker Fund Flow | Institutional accumulation detection |
| `CPRCamarillaStrategy` | CPR + Camarilla | Central Pivot Range + Camarilla pivots |
| `PositionCostDistributionStrategy` | Position Cost Distribution | VWAP-based cost distribution analysis |
| `SETSwingDashboardStrategy` | SET Swing Dashboard | Multi-indicator swing composite for SET |

---

### Momentum (12-1)

**File:** [`src/strategies/momentum.py`](src/strategies/momentum.py)

**Signal:**

$$\text{Momentum}_t = R_{t-252}^{t} - R_{t-21}^{t}$$

where $R_a^b = \frac{P_b - P_a}{P_a}$ is the total return from day $a$ to day $b$.

Long the top quintile (top 20%) ranked by momentum score. Signals are updated on the first trading day of each month. For universes smaller than 5 tickers, the top half is used instead.

---

### Laguerre RSI (Ehlers DSP)

**File:** [`src/strategies/laguerre_rsi.py`](src/strategies/laguerre_rsi.py)

A 4-pole Laguerre filter smooths the price before computing an RSI-like oscillator. Translated from John Ehlers' PineScript implementation.

**Laguerre filter recursion:**

$$L_0 = (1 - \gamma) \cdot P + \gamma \cdot L_0^{\text{prev}}$$

$$L_1 = -\gamma \cdot L_0 + L_0^{\text{prev}} + \gamma \cdot L_1^{\text{prev}}$$

$$L_2 = -\gamma \cdot L_1 + L_1^{\text{prev}} + \gamma \cdot L_2^{\text{prev}}$$

$$L_3 = -\gamma \cdot L_2 + L_2^{\text{prev}} + \gamma \cdot L_3^{\text{prev}}$$

**Oscillator:**

$$CU = \max(L_0-L_1,0) + \max(L_1-L_2,0) + \max(L_2-L_3,0)$$

$$CD = \max(L_1-L_0,0) + \max(L_2-L_1,0) + \max(L_3-L_2,0)$$

$$\text{LaRSI} = \frac{CU}{CU + CD}$$

**Signal:** Long when LaRSI crosses above 0.25 (oversold); exit when it crosses below 0.75 (overbought). Default $\gamma = 0.6$.

---

### Hurst Exponent + Choppiness Index

**File:** [`src/strategies/hurst_choppiness.py`](src/strategies/hurst_choppiness.py)

Classifies the market as trending or mean-reverting using two complementary measures.

**Hurst Exponent via R/S analysis** (rolling window of 100 bars):

$$H = \frac{\log(R/S)}{\log(N)}$$

where $R$ = range of cumulative deviations from the mean, $S$ = standard deviation of the window.

- $H > 0.5$ → trending (persistent series)
- $H = 0.5$ → random walk
- $H < 0.5$ → mean-reverting

**Choppiness Index** (close-only approximation):

$$\text{CHOP} = \frac{100 \times \log_{10}\!\left(\frac{\sum_{i}|\Delta P_i|}{\max(P) - \min(P)}\right)}{\log_{10}(N)}$$

Range: 0–100. High ($> 61.8$) = choppy. Low ($< 38.2$) = trending.

**Signal:** Long when $H > 0.55$ AND $\text{CHOP} < 61.8$ AND $P > \text{MA}_{50}$.

---

### Williams Vix Fix + Connors RSI-2

**File:** [`src/strategies/wvf_connors_rsi.py`](src/strategies/wvf_connors_rsi.py)

A dual-confirmation bottom-fishing strategy.

**Williams Vix Fix (synthetic VIX):**

$$\text{WVF} = \frac{\max(\text{Close}, 22) - \text{Low}}{\max(\text{Close}, 22)} \times 100$$

Spikes when price drops to a multi-week low (fear proxy).

**WVF spike detection:** Spike is triggered when WVF exceeds either the upper Bollinger Band or 85th percentile of its 50-bar lookback:

$$\text{spike} = \text{WVF} \geq \text{BB}_{\text{upper}} \;\lor\; \text{WVF} \geq Q_{0.85}(\text{WVF}, 50)$$

**Connors RSI-2:**

$$\text{ConnorsRSI} = \frac{\text{RSI}(2) + \text{StreakRSI}(3) + \text{ROC}_{\text{Pct}}(100)}{3}$$

- $\text{StreakRSI}$: RSI applied to the signed consecutive up/down day streak
- $\text{ROC}_{\text{Pct}}$: percentile rank of 1-day ROC among last 100 bars

**Entry (dual-confirm):**
1. WVF spiked yesterday but not today (fired)
2. ConnorsRSI $< 10$ (extreme oversold)
3. Price $>$ MA(200) (structural uptrend intact)

**Exit:** ConnorsRSI $> 90$ OR price $<$ MA(200).

---

### Chandelier Exit

**File:** [`src/strategies/chandelier_exit.py`](src/strategies/chandelier_exit.py)

ATR-based trailing stops define trend direction.

**Filtered ATR (Wilder smoothing with circuit-breaker):** If daily price change $\geq 25\%$ (circuit-breaker threshold), that bar's True Range is replaced by the previous bar's TR — preventing SET limit-up/down days from inflating ATR.

$$\text{ATR} = \text{EWM}\!\left(\text{TR}_{\text{filtered}},\; \alpha = \frac{1}{\text{period}}\right)$$

**Long stop (ratchets upward only):**

$$\text{LongStop}_t = \max\!\left(\max(C, \text{period}) - \text{mult} \times \text{ATR},\; \text{LongStop}_{t-1}\right) \quad \text{if } C_{t-1} > \text{LongStop}_{t-1}$$

**Short stop (ratchets downward only):**

$$\text{ShortStop}_t = \min\!\left(\min(C, \text{period}) + \text{mult} \times \text{ATR},\; \text{ShortStop}_{t-1}\right) \quad \text{if } C_{t-1} < \text{ShortStop}_{t-1}$$

**Trend direction:**
- $+1$ when $C_t > \text{ShortStop}_{t-1}$
- $-1$ when $C_t < \text{LongStop}_{t-1}$

**Signal:** Long when direction = +1, flat when −1. Default: period = 22, mult = 3.

---

### Pivot Point Supertrend

**File:** [`src/strategies/pivot_point_supertrend.py`](src/strategies/pivot_point_supertrend.py)

ATR-based Supertrend bands anchored to confirmed pivot highs/lows rather than to a simple midprice.

**Pivot detection:** A high at bar $i$ is confirmed as a pivot high `prd` bars later when $H_i \geq \max(H_{i-\text{prd}:i}) \;\land\; H_i \geq \max(H_{i+1:i+\text{prd}+1})$.

**Band calculation** (pivot midpoint as anchor):

$$\text{pivot} = \frac{\text{PivotHigh} + \text{PivotLow}}{2}$$

$$TUp_t = \max\!\left(\text{pivot} - \text{factor} \times \text{ATR},\; TUp_{t-1}\right) \quad \text{if pivot} > TUp_{t-1}$$

$$TDown_t = \min\!\left(\text{pivot} + \text{factor} \times \text{ATR},\; TDown_{t-1}\right) \quad \text{if pivot} < TDown_{t-1}$$

**Trend:** Switches to +1 when pivot crosses above $TDown_{t-1}$; switches to −1 when pivot crosses below $TUp_{t-1}$.

---

## 6. HMM Regime Detection

**Files:** [`src/hmm_regime/`](src/hmm_regime/)

**API:** `GET /api/hmm-regime?ticker=&start=&train_end=&test_start=&refresh=`

**UI:** HMMRegimeWidget.tsx

### Usage

```bash
curl "http://localhost:8000/api/hmm-regime?ticker=AAPL&start=2020-01-01&train_end=2023-01-01&test_start=2023-01-01"
```

### Model

A 4-state **Gaussian Hidden Markov Model** (diagonal covariance) fitted with `hmmlearn`.

**States:** `bull`, `sideways`, `bear`, `crash`

### Features

Computed in [`src/hmm_regime/features.py`](src/hmm_regime/features.py):

| Feature | Formula |
|---------|---------|
| Log return | $r_t = \ln(P_t / P_{t-1})$ |
| Realized volatility | $\sigma_t = \text{std}(r_{t-20:t})$ |
| Log-volume ratio | $\ln(V_t / \bar{V}_{20})$ |

Features are standardised with `StandardScaler` before training.

### Training

**File:** [`src/hmm_regime/hmm_model.py`](src/hmm_regime/hmm_model.py)

- 15 random restarts; best model selected by log-likelihood.
- **Acceptability constraints:** any model is rejected if any state has $< 3\%$ of training samples, or if realized mean log returns across states are not spread by at least $2 \times 10^{-4}$ per day.
- Three-pass fallback: full constraints → relax spread → any fit.

### State Labelling

States are labelled using **realized** (unscaled) mean log returns — not the HMM's fitted means in scaled space:

1. Highest mean log return → `bull`
2. Lowest mean log return → `crash`
3. Of the two middle states: lower realized vol → `sideways`, higher → `bear`

### Walk-Forward Evaluation

**File:** [`src/hmm_regime/walk_forward.py`](src/hmm_regime/walk_forward.py)

Train on the first 80% of history; predict on the last 20%. Results include per-bar state labels, state probabilities ($p_{\text{bull}}, p_{\text{sideways}}, p_{\text{bear}}, p_{\text{crash}}$), and summary statistics per state.

---

## 7. Performance Metrics

**File:** [`src/backtesting/metrics.py`](src/backtesting/metrics.py)

**Function:** `compute_metrics(equity, trade_log, risk_free_rate=0.02) → dict`

| Metric | Formula |
|--------|---------|
| Total Return | $\frac{E_T - E_0}{E_0}$ |
| CAGR | $\left(\frac{E_T}{E_0}\right)^{1/n_{\text{years}}} - 1$ |
| Annualised Volatility | $\sigma_{\text{daily}} \times \sqrt{252}$ |
| Sharpe Ratio | $\frac{\bar{r}_{\text{daily}} - r_f/252}{\sigma_{\text{daily}}} \times \sqrt{252}$ |
| Max Drawdown | $\min_t \frac{E_t - \max_{s \leq t} E_s}{\max_{s \leq t} E_s}$ |
| Calmar Ratio | $\frac{\text{CAGR}}{|\text{Max Drawdown}|}$ |
| Win Rate | $\frac{\text{winning trades}}{\text{total trades}}$ |
| Avg Win | $\mathbb{E}[r \mid r > 0]$ |
| Avg Loss | $\mathbb{E}[r \mid r < 0]$ |
| Reward-to-Risk | $\left|\frac{\text{Avg Win}}{\text{Avg Loss}}\right|$ |
| Avg Trade Return | $\mathbb{E}[r]$ across all closed trades |

All NaN and Inf values are replaced with `None` before serialisation.

`n_years` is computed from calendar days: $n_{\text{years}} = \max\!\left(\frac{(T_{\text{end}} - T_{\text{start}})_{\text{days}}}{365.25},\; \frac{1}{365.25}\right)$

Daily risk-free rate: $r_f^{\text{daily}} = \frac{r_f}{252}$
