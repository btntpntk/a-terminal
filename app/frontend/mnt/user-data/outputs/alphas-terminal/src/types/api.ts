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
