// Stage 0
export interface LayerScores { regime: number; fragility: number; trigger: number }
export interface RegimeResponse {
  composite_risk: number;
  regime_label: string;
  layer_scores: LayerScores;
  confidence: number;
  confidence_signal: string;
  position_scale: string;
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
export interface MacroSignalDetail {
  ticker: string;
  current_price: number | null;
  mom_20d_pct: number | null;
  mom_60d_pct: number | null;
  z_score_60d: number | null;
  signal: string;
  risk_score: number;
  macro_bias: string;
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
export interface MacroResponse {
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
  cycle_quadrant: string;
  quadrant_advice: string;
  copper_gold_ratio: number;
  macro_bias_summary: string;
  sector_adjustments: Record<string, number>;
  raw_scores: Record<string, number>;
  signal_weights: Record<string, number>;
  timestamp: string;
}

// Stage 2
export interface SectorItem {
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
export interface SectorsResponse {
  universe: string;
  sector_gate: boolean;
  sector_rotation: string;
  top_sectors: string[];
  avoid_sectors: string[];
  ranked_sectors: SectorItem[];
  timestamp: string;
}

// Stages 3+4
export interface TickerRow {
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
export interface RankingsResponse {
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
export interface ScanProgress {
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
export interface ScanResult extends ScanProgress {
  rankings: RankingsResponse | null;
}

export interface ScanStreamEvent {
  job_id: string;
  status: string;
  progress_pct: number;
  completed: number;
  total: number;
  current_ticker: string | null;
}

export interface FilterState {
  verdictFilter: 'ALL' | 'BUY' | 'FUND_ONLY' | 'TECH_ONLY' | 'FAIL';
  sectorFilter: string;
  tickerSearch: string;
}

export interface UniverseInfo {
  key: string;
  display_name: string;
  ticker_count: number;
  sector_count: number;
  benchmark: string;
}

// Backtesting
export interface BacktestMetrics {
  total_return:     number | null;
  cagr:             number | null;
  sharpe_ratio:     number | null;
  max_drawdown:     number | null;
  calmar_ratio:     number | null;
  volatility_ann:   number | null;
  avg_trade_return: number | null;
  win_rate:         number | null;
  avg_win:          number | null;
  avg_loss:         number | null;
  reward_to_risk:   number | null;
  total_trades:     number;
  long_trades:      number;
  short_trades:     number;
}

export interface BacktestResponse {
  equity_curve:      Record<string, number>;
  benchmark_curve:   Record<string, number>;
  /** Only present in single-ticker mode. Asset price rebased to initial_capital from day one. */
  buyhold_curve?:    Record<string, number> | null;
  fold_boundaries:   string[];
  metrics:           BacktestMetrics;
  trade_log_summary: { total_trades: number; long_trades: number; short_trades: number };
  trade_markers:     Array<{ date: string; type: 'buy' | 'sell' | 'stop' }>;
  trade_log:         Array<{
    asset:          string;
    entry_date:     string;
    exit_date:      string;
    entry_price:    number;
    exit_price:     number;
    return_pct:     number;
    pnl:            number;
    balance:        number;
    stop_triggered: boolean;
  }>;
  /** Sampled daily weights: each entry is {date, ticker: weight, ...}. Positive = long, negative = short. */
  positions_chart:   Array<Record<string, number | string>>;
}

// HMM Regime
export interface HMMRegimeStat {
  frequency_pct: number;
  avg_duration_days: number;
  ann_return_pct: number;
  ann_vol_pct: number;
}

export interface HMMRegimePoint {
  date: string;
  regime: 'bull' | 'sideways' | 'bear' | 'crash';
  p_bear: number;
  p_sideways: number;
  p_bull: number;
  p_crash: number;
  close: number | null;
}

// Hurst Exponent
export interface HurstPoint {
  date: string;
  h: number;
}

export interface HurstResponse {
  ticker: string;
  window: number;
  current_h: number;
  regime: 'sideways' | 'random' | 'trending';
  series: HurstPoint[];
  timestamp: string;
}

export interface HMMRegimeResponse {
  ticker: string;
  current_regime: 'bull' | 'sideways' | 'bear' | 'crash';
  current_p_bull: number;
  current_p_side: number;
  current_p_bear: number;
  current_p_crash: number;
  train_end: string;
  test_start: string;
  n_observations: number;
  regime_stats: { bull: HMMRegimeStat; sideways: HMMRegimeStat; bear: HMMRegimeStat; crash: HMMRegimeStat };
  series: HMMRegimePoint[];
}

export interface BacktestRequest {
  strategy:          string;
  universe:          string;
  optimizer:         string;
  max_stop_loss_pct: number;
  initial_capital:   number;
  period_years:      number;
  /** Single-ticker mode: when set, ignores universe/optimizer and tests one asset vs benchmark. */
  single_ticker?:    string;
  /** Explicit benchmark for single-ticker mode. If omitted, auto-inferred server-side from ticker suffix. */
  benchmark_ticker?: string;
}

// Monte Carlo Integrated Backtest
export interface MCBacktestRequest {
  // Strategies
  buy_strategy:  string;
  sell_strategy: string;  // strategy name | "TP_SL" | "BOTH"
  // Universe / single-stock mode
  universe: string;
  /** Single-ticker mode: when set, ignores universe and tests one asset. */
  single_ticker?:    string;
  /** Explicit benchmark for single-ticker mode. Auto-inferred if omitted. */
  benchmark_ticker?: string;
  // Backtest period
  backtest_start: string;
  backtest_end:   string;
  // Capital & risk
  initial_capital:      number;
  max_stop_loss_pct:    number;
  acceptable_risk_pct:  number;
  // MC simulation
  n_simulations:      number;
  holding_days:       number;
  tp_quantile:        number;
  sl_quantile:        number;
  shock_distribution: string;
  student_t_df:       number;
  // Volatility estimation
  vol_lookback_days:  number;
  vol_method:         string;
  ewma_halflife_days: number;
  vol_floor:          number;
  vol_cap:            number;
  drift_method:       string;
  // Position & portfolio controls
  max_open_positions:       number;
  max_position_pct:         number;
  cash_reserve_pct:         number;
  max_signals_per_bar:      number;
  signal_confirmation_bars: number;
  cooloff_days:             number;
  // Exit behaviour
  breakeven_trail_enabled: boolean;
  max_holding_days:        number;
  partial_tp_pct:          number;
  // EV filter
  min_ev_dollars: number;
  min_rr_ratio:   number;
  min_p_tp:       number;
  // Position sizing
  sizing_method:  string;
  kelly_fraction: number;
  // Correlation controls
  correlation_penalty_enabled: boolean;
  correlation_threshold:       number;
  correlation_penalty_factor:  number;
  // Walk-forward
  n_folds:                     number;
  test_window_days:            number;
  purge_days:                  number;
  optimise_mc_params_on_train: boolean;
  sl_quantile_grid:            number[];
  tp_quantile_grid:            number[];
  // Fill price
  fill_price: string;
  // Misc
  seed_base:         number;
  commission_bps:    number;
  sl_commission_bps: number;
}

export interface MCTradeDetail {
  ticker:       string;
  entry_date:   string;
  sl_raw:       number | null;
  sl_applied:   number | null;
  tp:           number | null;
  rr:           number | null;
  p_tp:         number | null;
  ev:           number | null;
  sigma_annual: number | null;
  exit_reason:  string;
}

export interface MCAggregateStats {
  mean_p_tp:                  number | null;
  fraction_filtered_ev:       number | null;
  fraction_filtered_rr:       number | null;
  fraction_filtered_p_tp:     number | null;
  mean_sigma_at_entry:        number | null;
  breakeven_trail_activations: number;
  total_candidates_evaluated: number;
  total_trades_entered:       number;
}

export interface MCBacktestResponse extends BacktestResponse {
  mc_trade_details:   MCTradeDetail[];
  mc_aggregate_stats: MCAggregateStats;
}

// Shannon Entropy — /api/market/entropy
export interface EntropyPoint {
  date:       string;
  entropy:    number;
  normalized: number;
}
export interface EntropyResponse {
  ticker:             string;
  current_entropy:    number;
  normalized_entropy: number;
  max_entropy:        number;
  regime:             'LOW NOISE' | 'MODERATE' | 'HIGH NOISE';
  interpretation:     string;
  window_days:        number;
  series:             EntropyPoint[];
  timestamp:          string;
}

// Macro Correlation Matrix — /api/macro/correlation-matrix
export type CorrSignal =
  | 'STRONG_POS'
  | 'MILD_POS'
  | 'DECOUPLED'
  | 'MILD_NEG'
  | 'STRONG_NEG'
  | 'DATA_MISSING'
  | 'INSUFFICIENT_DATA';

export interface CorrPoint {
  date: string;
  corr: number;
}
export interface DriverCorrelation {
  ticker:       string;
  signal:       CorrSignal;
  current_corr: number | null;
  corr_30d:     number | null;
  corr_60d:     number | null;
  series:       CorrPoint[];
}
export interface CorrelationMatrixResponse {
  benchmark:    string;
  window:       number;
  correlations: Record<string, DriverCorrelation>;
  timestamp:    string;
}

// Transfer Entropy — /api/analysis/transfer-entropy
export type LeakageSignal = 'HIGH' | 'MODERATE' | 'REVERSE' | 'NONE';

export interface TEPoint { date: string; te: number }

export interface TransferEntropyResponse {
  source:         string;
  target:         string;
  te_x_to_y:      number;
  te_y_to_x:      number;
  net_flow:       number;
  normalized_te:  number;
  h_target:       number;
  leakage_signal: LeakageSignal;
  interpretation: string;
  lag_x:          number;
  lag_y:          number;
  bins:           number;
  window:         number;
  n_obs:          number;
  series:         TEPoint[];
  timestamp:      string;
}

// Ticker Fundamentals — /api/ticker/fundamentals/{ticker}
export type FundamentalSignal = 'STRONG_BUY' | 'BUY' | 'NEUTRAL' | 'SELL' | 'STRONG_SELL';
export type MoatRating        = 'WIDE' | 'NARROW' | 'MARGINAL' | 'NONE';
export type AltmanZone        = 'SAFE' | 'GREY' | 'DISTRESS';

export interface TickerFundamentalsResponse {
  ticker:                string;
  alpha_score:           number;
  signal:                FundamentalSignal;
  roic:                  number | null;
  wacc:                  number | null;
  roic_wacc_spread:      number | null;
  moat:                  MoatRating;
  sloan_ratio:           number | null;
  fcf_quality:           number | null;
  altman_z:              number | null;
  altman_zone:           AltmanZone;
  asset_turnover:        number | null;
  cash_conversion_cycle: number | null;
  sortino:               number | null;
  beta:                  number | null;
}

// Sector TE Matrix — /api/analysis/sector-te-matrix
export interface SectorTEMatrixResponse {
  sectors:   string[];
  tickers:   Record<string, string>;
  matrix:    Record<string, Record<string, number | null>>;
  lag:       number;
  bins:      number;
  window:    number;
  timestamp: string;
}
