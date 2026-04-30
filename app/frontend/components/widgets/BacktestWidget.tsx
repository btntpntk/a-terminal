import { useState, useMemo, useEffect } from 'react';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ReferenceLine,
  ResponsiveContainer, Legend, BarChart, Bar,
} from 'recharts';
import { api } from '../../lib/api';
import type {
  BacktestRequest, BacktestResponse, BacktestMetrics,
  MCBacktestRequest, MCBacktestResponse, MCTradeDetail, MCAggregateStats,
} from '../../types/api';

// ── Local alias types ─────────────────────────────────────────────────────

type BacktestConfig = BacktestRequest;
type BacktestResult = BacktestResponse;

// ── Constants ─────────────────────────────────────────────────────────────

const STRATEGIES = [
  { value: 'MomentumStrategy',           label: 'Momentum (12-1)' },
  { value: 'MeanReversionStrategy',      label: 'Mean Reversion' },
  { value: 'MovingAverageCrossStrategy', label: 'MA Cross (20/50)' },
  { value: 'EMACrossStrategy',           label: 'EMA Cross (12/26)' },
  { value: 'RSIStrategy',                label: 'RSI (14)' },
  { value: 'VolatilityBreakoutStrategy', label: 'Volatility Breakout' },
  { value: 'DRSIStrategy',               label: 'DRSI (Dual RSI)' },
  { value: 'VADERStrategy',              label: 'VADER — Volatility-Adaptive Dual-Edge Regime' },
];

const UNIVERSES = [
  { value: 'SP500_SAMPLE',   label: 'S&P 500 Sample' },
  { value: 'SET100', label: 'Thai Large Cap' },
  { value: 'CRYPTO_MAJORS',  label: 'Crypto Majors' },
  { value: 'GLOBAL_ETF',     label: 'Global ETF' },
  { value: 'WATCHLIST_A',    label: 'Watchlist A (44 stocks)' },
];

const OPTIMIZERS = [
  { value: 'EqualWeightOptimizer',       label: 'Equal Weight' },
  { value: 'InverseVolatilityOptimizer', label: 'Inverse Volatility' },
  { value: 'MeanVarianceOptimizer',      label: 'Mean-Variance' },
  { value: 'RiskParityOptimizer',        label: 'Risk Parity' },
  { value: 'KellyCriterionOptimizer',    label: 'Kelly (25%)' },
];

const PERIODS = [
  { value: 1,  label: '1Y' },
  { value: 2,  label: '2Y' },
  { value: 3,  label: '3Y' },
  { value: 5,  label: '5Y' },
  { value: 10, label: '10Y' },
];

const DEFAULT_CONFIG: BacktestConfig = {
  strategy:          'MomentumStrategy',
  universe:          'SP500_SAMPLE',
  optimizer:         'EqualWeightOptimizer',
  max_stop_loss_pct: 5,
  initial_capital:   1_000_000,
  period_years:      3,
};

type BacktestMode = 'universe' | 'single';
type EngineMode = 'normal' | 'mc';

// ── Helpers ───────────────────────────────────────────────────────────────

function fmtPct(v: number | null | undefined, decimals = 1): string {
  if (v == null) return '—';
  return `${v >= 0 ? '+' : ''}${(v * 100).toFixed(decimals)}%`;
}

function fmtNum(v: number | null | undefined, decimals = 2): string {
  if (v == null) return '—';
  return v.toFixed(decimals);
}

function fmtCurrency(v: number | null | undefined): string {
  if (v == null) return '—';
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v);
}

function metricColor(value: number | null, type: 'return' | 'win_rate' | 'rr' | 'drawdown' | 'neutral'): string {
  if (value == null) return '#888';
  switch (type) {
    case 'return':   return value >= 0 ? '#4ade80' : '#f87171';
    case 'win_rate': return value >= 0.5 ? '#4ade80' : '#f87171';
    case 'rr':       return value >= 1 ? '#4ade80' : '#f87171';
    case 'drawdown': return value >= -0.1 ? '#4ade80' : value >= -0.2 ? '#facc15' : '#f87171';
    default:         return '#888';
  }
}

// ── Positions chart helpers ───────────────────────────────────────────────

const POSITION_COLORS = [
  '#818cf8', '#34d399', '#fb923c', '#f472b6', '#38bdf8',
  '#a78bfa', '#facc15', '#4ade80', '#e879f9', '#22d3ee',
  '#f97316', '#10b981', '#8b5cf6', '#06b6d4', '#ec4899',
  '#84cc16', '#6366f1', '#14b8a6', '#f59e0b', '#ef4444',
];

function PositionsTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  const entries = payload.filter((p: any) => p.value != null && Math.abs(p.value) > 1e-5);
  if (!entries.length) return null;
  return (
    <div style={{
      background: '#1a1a2e', border: '1px solid #2d2d4e', borderRadius: 6,
      padding: '8px 12px', fontSize: 11, maxWidth: 200,
    }}>
      <div style={{ color: '#888', marginBottom: 4 }}>{label}</div>
      {entries.map((p: any) => (
        <div key={p.dataKey} style={{ color: p.fill ?? p.color, display: 'flex', justifyContent: 'space-between', gap: 12 }}>
          <span>{p.name}</span>
          <span style={{ fontFamily: 'monospace' }}>{(p.value * 100).toFixed(1)}%</span>
        </div>
      ))}
    </div>
  );
}

// ── Chart data preparation ────────────────────────────────────────────────

function toReturnPct(curve: Record<string, number>): Record<string, number> {
  const dates = Object.keys(curve).sort();
  if (dates.length === 0) return {};
  const base = curve[dates[0]];
  if (!base) return {};
  const out: Record<string, number> = {};
  for (const d of dates) out[d] = (curve[d] / base - 1) * 100;
  return out;
}

function buildChartData(
  equity: Record<string, number>,
  benchmark: Record<string, number>,
  buyhold?: Record<string, number> | null,
  markers?: Array<{ date: string; type: 'buy' | 'sell' }>,
): Array<{ date: string; portfolio: number; benchmark: number; buyhold?: number; buySignal?: number; sellSignal?: number; stopSignal?: number }> {
  const pctEquity    = toReturnPct(equity);
  const pctBenchmark = toReturnPct(benchmark);
  const pctBuyhold   = buyhold ? toReturnPct(buyhold) : null;

  const buyDates  = new Set(markers?.filter(m => m.type === 'buy').map(m => m.date)  ?? []);
  const sellDates = new Set(markers?.filter(m => m.type === 'sell').map(m => m.date) ?? []);
  const stopDates = new Set(markers?.filter(m => m.type === 'stop').map(m => m.date) ?? []);

  const allDates = Array.from(new Set([
    ...Object.keys(pctEquity),
    ...Object.keys(pctBenchmark),
    ...(pctBuyhold ? Object.keys(pctBuyhold) : []),
  ])).sort();

  return allDates.map(date => {
    const portfolioPct = pctEquity[date] ?? NaN;
    return {
      date,
      portfolio: portfolioPct,
      benchmark: pctBenchmark[date] ?? NaN,
      ...(pctBuyhold  != null ? { buyhold:    pctBuyhold[date]  ?? NaN } : {}),
      ...(buyDates.has(date)  ? { buySignal:  pctBuyhold ? (pctBuyhold[date] ?? NaN) : portfolioPct } : {}),
      ...(sellDates.has(date) ? { sellSignal: pctBuyhold ? (pctBuyhold[date] ?? NaN) : portfolioPct } : {}),
      ...(stopDates.has(date) ? { stopSignal: pctBuyhold ? (pctBuyhold[date] ?? NaN) : portfolioPct } : {}),
    };
  }).filter(d => !isNaN(d.portfolio) || !isNaN(d.benchmark));
}

// ── Trade marker dot shapes ───────────────────────────────────────────────

function BuyDot(props: any) {
  const { cx, cy } = props;
  if (cx == null || cy == null) return null;
  const s = 3;
  return <polygon points={`${cx},${cy - s} ${cx - s},${cy + s} ${cx + s},${cy + s}`} fill="#4ade80" opacity={0.9} />;
}

function SellDot(props: any) {
  const { cx, cy } = props;
  if (cx == null || cy == null) return null;
  const s = 3;
  return <polygon points={`${cx},${cy + s} ${cx - s},${cy - s} ${cx + s},${cy - s}`} fill="#f87171" opacity={0.9} />;
}

function StopDot(props: any) {
  const { cx, cy } = props;
  if (cx == null || cy == null) return null;
  const s = 3;
  return <polygon points={`${cx},${cy + s} ${cx - s},${cy - s} ${cx + s},${cy - s}`} fill="#f87171" stroke="#7f1d1d" strokeWidth={1} opacity={0.9} />;
}

// ── Sub-components ────────────────────────────────────────────────────────

interface KpiCardProps {
  label: string;
  value: string;
  color: string;
  sub?: string;
}
function KpiCard({ label, value, color, sub }: KpiCardProps) {
  return (
    <div style={{
      background: '#1a1a2e', border: '1px solid #2d2d4e',
      borderRadius: 6, padding: '10px 14px', minWidth: 100,
    }}>
      <div style={{ fontSize: 10, color: '#888', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 18, fontWeight: 700, color, fontFamily: 'monospace' }}>{value}</div>
      {sub && <div style={{ fontSize: 10, color: '#666', marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

interface SelectProps {
  label: string;
  value: string | number;
  options: { value: string | number; label: string }[];
  onChange: (v: string) => void;
}
function LabeledSelect({ label, value, options, onChange }: SelectProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, flex: 1, minWidth: 120 }}>
      <label style={{ fontSize: 10, color: '#888', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</label>
      <select
        value={value}
        onChange={e => onChange(e.target.value)}
        style={{
          background: '#111128', color: '#e0e0f0', border: '1px solid #2d2d4e',
          borderRadius: 4, padding: '5px 8px', fontSize: 12, cursor: 'pointer',
        }}
      >
        {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  );
}

interface NumberInputProps {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (v: number) => void;
  suffix?: string;
}
function LabeledNumber({ label, value, min, max, step = 1, onChange, suffix }: NumberInputProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, flex: 1, minWidth: 100 }}>
      <label style={{ fontSize: 10, color: '#888', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        {label}{suffix ? ` (${suffix})` : ''}
      </label>
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={e => onChange(Number(e.target.value))}
        style={{
          background: '#111128', color: '#e0e0f0', border: '1px solid #2d2d4e',
          borderRadius: 4, padding: '5px 8px', fontSize: 12, width: '100%',
        }}
      />
    </div>
  );
}

// ── Custom Tooltip ────────────────────────────────────────────────────────

function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: '#1a1a2e', border: '1px solid #2d2d4e', borderRadius: 6,
      padding: '8px 12px', fontSize: 11,
    }}>
      <div style={{ color: '#888', marginBottom: 4 }}>{label}</div>
      {payload.map((p: any) => (
        <div key={p.dataKey} style={{ color: p.color }}>
          {p.name}: {p.value != null ? `${p.value >= 0 ? '+' : ''}${p.value.toFixed(1)}%` : '—'}
        </div>
      ))}
    </div>
  );
}

// ── EMA helpers ───────────────────────────────────────────────────────────

/** Matches pandas ewm(span, adjust=False): y_t = α*x_t + (1−α)*y_{t−1}, y_0 = x_0 */
function computeEWM(values: number[], span: number): number[] {
  const alpha = 2 / (span + 1);
  const out: number[] = [];
  let ema = values[0];
  for (let i = 0; i < values.length; i++) {
    ema = alpha * values[i] + (1 - alpha) * ema;
    out.push(ema);
  }
  return out;
}

type EmaPoint = { date: string; price: number; ema12: number; ema26: number; buySignal?: number; sellSignal?: number; stopSignal?: number };

function buildEmaChartData(
  bars: Array<{ time: string; close: number }>,
  markers: Array<{ date: string; type: string }>,
): EmaPoint[] {
  const sorted = bars.slice().sort((a, b) => a.time.localeCompare(b.time));
  const closes = sorted.map(b => b.close);
  const ema12 = computeEWM(closes, 12);
  const ema26 = computeEWM(closes, 26);

  const buyDates  = new Set(markers.filter(m => m.type === 'buy').map(m => m.date));
  const sellDates = new Set(markers.filter(m => m.type === 'sell').map(m => m.date));
  const stopDates = new Set(markers.filter(m => m.type === 'stop').map(m => m.date));

  return sorted.map((b, i) => ({
    date:  b.time,
    price: b.close,
    ema12: ema12[i],
    ema26: ema26[i],
    ...(buyDates.has(b.time)  ? { buySignal:  b.close } : {}),
    ...(sellDates.has(b.time) ? { sellSignal: b.close } : {}),
    ...(stopDates.has(b.time) ? { stopSignal: b.close } : {}),
  }));
}

// ── MC Constants ──────────────────────────────────────────────────────────

const SELL_STRATEGIES = [
  ...STRATEGIES,
  { value: 'TP_SL', label: 'TP/SL only (MC-derived)' },
  { value: 'BOTH',  label: 'Both: TP/SL + strategy signal' },
];

const SHOCK_DISTRIBUTIONS = [
  { value: 'student_t', label: 'Student-t (fat tails)' },
  { value: 'normal',    label: 'Normal' },
];
const VOL_METHODS    = [{ value: 'ewma', label: 'EWMA' }, { value: 'rolling_std', label: 'Rolling Std Dev' }];
const DRIFT_METHODS  = [{ value: 'zero', label: 'Zero (conservative)' }, { value: 'historical_mean', label: 'Historical mean' }];
const SIZING_METHODS = [{ value: 'risk_parity_sl', label: 'Risk parity (SL-based)' }, { value: 'kelly_mc', label: 'Kelly (MC-derived)' }];
const FILL_PRICES    = [{ value: 'open_next_day', label: 'Next-day open (safe)' }, { value: 'close', label: 'Same-day close (⚠ lookahead risk)' }];

function today(): string { return new Date().toISOString().slice(0, 10); }
function yearsAgo(n: number): string {
  const d = new Date(); d.setFullYear(d.getFullYear() - n); return d.toISOString().slice(0, 10);
}

const DEFAULT_MC_CONFIG: MCBacktestRequest = {
  buy_strategy: 'MomentumStrategy',
  sell_strategy: 'TP_SL',
  universe: 'SP500_SAMPLE',
  backtest_start: yearsAgo(3),
  backtest_end: today(),
  initial_capital: 1_000_000,
  max_stop_loss_pct: 0.08,
  acceptable_risk_pct: 0.01,
  n_simulations: 1000,
  holding_days: 10,
  tp_quantile: 0.80,
  sl_quantile: 0.10,
  shock_distribution: 'student_t',
  student_t_df: 6,
  vol_lookback_days: 20,
  vol_method: 'ewma',
  ewma_halflife_days: 10,
  vol_floor: 0.10,
  vol_cap: 1.50,
  drift_method: 'zero',
  max_open_positions: 10,
  max_position_pct: 0.15,
  cash_reserve_pct: 0.10,
  max_signals_per_bar: 5,
  signal_confirmation_bars: 1,
  cooloff_days: 5,
  breakeven_trail_enabled: true,
  max_holding_days: 20,
  partial_tp_pct: 1.0,
  min_ev_dollars: 0.0,
  min_rr_ratio: 1.5,
  min_p_tp: 0.50,
  sizing_method: 'risk_parity_sl',
  kelly_fraction: 0.25,
  correlation_penalty_enabled: true,
  correlation_threshold: 0.70,
  correlation_penalty_factor: 0.50,
  n_folds: 4,
  test_window_days: 63,
  purge_days: 10,
  optimise_mc_params_on_train: false,
  sl_quantile_grid: [0.05, 0.10, 0.15],
  tp_quantile_grid: [0.75, 0.80, 0.85, 0.90],
  fill_price: 'open_next_day',
  seed_base: 42,
  commission_bps: 10,
  sl_commission_bps: 5,
};

// ── MC config sub-components ──────────────────────────────────────────────

function SectionHeader({ title }: { title: string }) {
  return (
    <div style={{ fontSize: 10, color: '#4f46e5', textTransform: 'uppercase', letterSpacing: '0.08em',
      fontWeight: 700, borderBottom: '1px solid #1e1e3f', paddingBottom: 4, marginTop: 4 }}>
      {title}
    </div>
  );
}

function Toggle({ label, value, onChange }: { label: string; value: boolean; onChange: (v: boolean) => void }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
      <button
        onClick={() => onChange(!value)}
        style={{
          background: value ? '#3730a3' : '#1a1a2e', border: '1px solid #2d2d4e',
          borderRadius: 12, padding: '2px 10px', fontSize: 11, cursor: 'pointer',
          color: value ? '#e0e0ff' : '#666', fontWeight: value ? 600 : 400, whiteSpace: 'nowrap',
        }}
      >
        {value ? 'ON' : 'OFF'}
      </button>
      <span style={{ fontSize: 11, color: '#888' }}>{label}</span>
    </div>
  );
}

function DateInput({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, flex: 1, minWidth: 120 }}>
      <label style={{ fontSize: 10, color: '#888', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</label>
      <input
        type="date"
        value={value}
        onChange={e => onChange(e.target.value)}
        style={{
          background: '#111128', color: '#e0e0f0', border: '1px solid #2d2d4e',
          borderRadius: 4, padding: '5px 8px', fontSize: 12, width: '100%',
        }}
      />
    </div>
  );
}

type MCMode = 'universe' | 'single';

interface MCConfigPanelProps {
  cfg: MCBacktestRequest;
  onChange: (patch: Partial<MCBacktestRequest>) => void;
}
function MCConfigPanel({ cfg, onChange }: MCConfigPanelProps) {
  const [mcMode, setMcMode] = useState<MCMode>(cfg.single_ticker ? 'single' : 'universe');
  const set = <K extends keyof MCBacktestRequest>(key: K, val: MCBacktestRequest[K]) =>
    onChange({ [key]: val } as Partial<MCBacktestRequest>);
  const numSet = (key: keyof MCBacktestRequest) => (v: number) => set(key, v as any);

  const switchMode = (m: MCMode) => {
    setMcMode(m);
    if (m === 'universe') {
      onChange({ single_ticker: undefined, benchmark_ticker: undefined });
    } else {
      onChange({ single_ticker: '', benchmark_ticker: '' });
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>

      {/* ── Strategies ── */}
      <SectionHeader title="Strategies" />
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <LabeledSelect label="Buy Strategy" value={cfg.buy_strategy}
          options={STRATEGIES} onChange={v => set('buy_strategy', v)} />
        <LabeledSelect label="Sell Strategy" value={cfg.sell_strategy}
          options={SELL_STRATEGIES} onChange={v => set('sell_strategy', v)} />
      </div>

      {/* ── Universe & Period ── */}
      <SectionHeader title="Universe & Period" />

      {/* Mode toggle */}
      <div style={{ display: 'flex', gap: 0, background: '#0d0d1a', border: '1px solid #2d2d4e', borderRadius: 6, overflow: 'hidden', alignSelf: 'flex-start' }}>
        {(['universe', 'single'] as MCMode[]).map(m => (
          <button key={m} onClick={() => switchMode(m)} style={{
            padding: '5px 14px', fontSize: 11, fontWeight: 600, cursor: 'pointer', border: 'none',
            background: mcMode === m ? '#3730a3' : 'transparent',
            color: mcMode === m ? '#e0e0ff' : '#666',
          }}>
            {m === 'universe' ? 'Universe' : 'Single Stock'}
          </button>
        ))}
      </div>

      {mcMode === 'universe' ? (
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <LabeledSelect label="Universe" value={cfg.universe}
            options={UNIVERSES} onChange={v => set('universe', v)} />
        </div>
      ) : (
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, flex: 1, minWidth: 120 }}>
            <label style={{ fontSize: 10, color: '#888', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Ticker</label>
            <input
              type="text"
              value={cfg.single_ticker ?? ''}
              onChange={e => set('single_ticker', e.target.value.toUpperCase())}
              placeholder="e.g. AAPL"
              style={{ background: '#111128', color: '#e0e0f0', border: '1px solid #2d2d4e', borderRadius: 4, padding: '5px 8px', fontSize: 12, width: '100%' }}
            />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, flex: 1, minWidth: 120 }}>
            <label style={{ fontSize: 10, color: '#888', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Benchmark (optional)</label>
            <input
              type="text"
              value={cfg.benchmark_ticker ?? ''}
              onChange={e => set('benchmark_ticker', e.target.value.toUpperCase())}
              placeholder="e.g. SPY (auto-detected)"
              style={{ background: '#111128', color: '#e0e0f0', border: '1px solid #2d2d4e', borderRadius: 4, padding: '5px 8px', fontSize: 12, width: '100%' }}
            />
          </div>
        </div>
      )}

      {mcMode === 'single' && (
        <div style={{ background: '#0d1a0d', border: '1px solid #14532d', borderRadius: 4,
          padding: '6px 10px', fontSize: 11, color: '#86efac' }}>
          Single-stock mode: set Max open positions to 1 and consider disabling correlation controls.
        </div>
      )}

      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <DateInput label="Backtest Start" value={cfg.backtest_start} onChange={v => set('backtest_start', v)} />
        <DateInput label="Backtest End"   value={cfg.backtest_end}   onChange={v => set('backtest_end', v)} />
      </div>

      {/* ── Capital & Risk ── */}
      <SectionHeader title="Capital & Risk" />
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <LabeledNumber label="Initial Capital" value={cfg.initial_capital}
          min={1000} max={100_000_000} step={10000} onChange={numSet('initial_capital')} suffix="USD" />
        <LabeledNumber label="Max stop loss (% from entry)" value={cfg.max_stop_loss_pct}
          min={0.01} max={0.30} step={0.01} onChange={numSet('max_stop_loss_pct')} suffix="%" />
        <LabeledNumber label="Risk per trade (% of portfolio)" value={cfg.acceptable_risk_pct}
          min={0.001} max={0.05} step={0.001} onChange={numSet('acceptable_risk_pct')} suffix="%" />
      </div>

      {/* ── MC Simulation ── */}
      <SectionHeader title="Monte Carlo Simulation" />
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <LabeledNumber label="Simulations per signal" value={cfg.n_simulations}
          min={200} max={10000} step={100} onChange={numSet('n_simulations')} />
        <LabeledNumber label="Holding period (days)" value={cfg.holding_days}
          min={1} max={60} step={1} onChange={numSet('holding_days')} />
        <LabeledNumber label="Take-profit quantile" value={cfg.tp_quantile}
          min={0.60} max={0.99} step={0.01} onChange={numSet('tp_quantile')} />
        <LabeledNumber label="Stop-loss quantile" value={cfg.sl_quantile}
          min={0.01} max={0.30} step={0.01} onChange={numSet('sl_quantile')} />
      </div>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <LabeledSelect label="Return distribution" value={cfg.shock_distribution}
          options={SHOCK_DISTRIBUTIONS} onChange={v => set('shock_distribution', v)} />
        {cfg.shock_distribution === 'student_t' && (
          <LabeledNumber label="Degrees of freedom" value={cfg.student_t_df}
            min={2} max={30} step={1} onChange={numSet('student_t_df')} />
        )}
        <LabeledSelect label="Fill price" value={cfg.fill_price}
          options={FILL_PRICES} onChange={v => set('fill_price', v)} />
      </div>
      {cfg.fill_price === 'close' && (
        <div style={{ background: '#2a1a00', border: '1px solid #854d0e', borderRadius: 4,
          padding: '6px 10px', fontSize: 11, color: '#fbbf24' }}>
          ⚠ Using close price may introduce lookahead bias. Prefer "next-day open" for realistic simulation.
        </div>
      )}

      {/* ── Volatility Estimation ── */}
      <SectionHeader title="Volatility Estimation" />
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <LabeledNumber label="Vol lookback (days)" value={cfg.vol_lookback_days}
          min={5} max={120} step={1} onChange={numSet('vol_lookback_days')} />
        <LabeledSelect label="Vol estimation method" value={cfg.vol_method}
          options={VOL_METHODS} onChange={v => set('vol_method', v)} />
        {cfg.vol_method === 'ewma' && (
          <LabeledNumber label="EWMA half-life (days)" value={cfg.ewma_halflife_days}
            min={2} max={60} step={1} onChange={numSet('ewma_halflife_days')} />
        )}
      </div>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <LabeledNumber label="Annual vol floor" value={cfg.vol_floor}
          min={0.01} max={0.50} step={0.01} onChange={numSet('vol_floor')} />
        <LabeledNumber label="Annual vol cap" value={cfg.vol_cap}
          min={0.50} max={5.00} step={0.10} onChange={numSet('vol_cap')} />
        <LabeledSelect label="Drift assumption" value={cfg.drift_method}
          options={DRIFT_METHODS} onChange={v => set('drift_method', v)} />
      </div>

      {/* ── Position & Portfolio Controls ── */}
      <SectionHeader title="Position & Portfolio Controls" />
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <LabeledNumber label="Max open positions" value={cfg.max_open_positions}
          min={1} max={50} step={1} onChange={numSet('max_open_positions')} />
        <LabeledNumber label="Max position size (% of portfolio)" value={cfg.max_position_pct}
          min={0.01} max={0.50} step={0.01} onChange={numSet('max_position_pct')} />
        <LabeledNumber label="Cash reserve (% of portfolio)" value={cfg.cash_reserve_pct}
          min={0.00} max={0.30} step={0.01} onChange={numSet('cash_reserve_pct')} />
      </div>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <LabeledNumber label="Max new entries per day" value={cfg.max_signals_per_bar}
          min={1} max={20} step={1} onChange={numSet('max_signals_per_bar')} />
        <LabeledNumber label="Signal confirmation bars" value={cfg.signal_confirmation_bars}
          min={1} max={5} step={1} onChange={numSet('signal_confirmation_bars')} />
        <LabeledNumber label="Cooloff after stop-loss (days)" value={cfg.cooloff_days}
          min={0} max={60} step={1} onChange={numSet('cooloff_days')} />
      </div>

      {/* ── Exit Behaviour ── */}
      <SectionHeader title="Exit Behaviour" />
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
        <Toggle label="Move SL to breakeven after 1R profit"
          value={cfg.breakeven_trail_enabled}
          onChange={v => set('breakeven_trail_enabled', v)} />
      </div>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <LabeledNumber label="Max holding days (time exit)" value={cfg.max_holding_days}
          min={1} max={252} step={1} onChange={numSet('max_holding_days')} />
        <LabeledNumber label="Exit fraction at TP" value={cfg.partial_tp_pct}
          min={0.1} max={1.0} step={0.1} onChange={numSet('partial_tp_pct')} />
      </div>

      {/* ── EV Filter ── */}
      <SectionHeader title="EV Filter Thresholds" />
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <LabeledNumber label="Min EV per share ($)" value={cfg.min_ev_dollars}
          min={0} max={100} step={0.1} onChange={numSet('min_ev_dollars')} />
        <LabeledNumber label="Min reward:risk ratio" value={cfg.min_rr_ratio}
          min={0.5} max={10} step={0.1} onChange={numSet('min_rr_ratio')} />
        <LabeledNumber label="Min P(TP hit)" value={cfg.min_p_tp}
          min={0.30} max={0.80} step={0.01} onChange={numSet('min_p_tp')} />
      </div>

      {/* ── Position Sizing ── */}
      <SectionHeader title="Position Sizing" />
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <LabeledSelect label="Position sizing method" value={cfg.sizing_method}
          options={SIZING_METHODS} onChange={v => set('sizing_method', v)} />
        {cfg.sizing_method === 'kelly_mc' && (
          <LabeledNumber label="Kelly fraction" value={cfg.kelly_fraction}
            min={0.10} max={1.00} step={0.05} onChange={numSet('kelly_fraction')} />
        )}
      </div>

      {/* ── Correlation Controls ── */}
      <SectionHeader title="Correlation Controls" />
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
        <Toggle label="Reduce size for correlated entries"
          value={cfg.correlation_penalty_enabled}
          onChange={v => set('correlation_penalty_enabled', v)} />
      </div>
      {cfg.correlation_penalty_enabled && (
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <LabeledNumber label="Correlation threshold" value={cfg.correlation_threshold}
            min={0.40} max={0.95} step={0.05} onChange={numSet('correlation_threshold')} />
          <LabeledNumber label="Size reduction factor" value={cfg.correlation_penalty_factor}
            min={0.10} max={0.90} step={0.05} onChange={numSet('correlation_penalty_factor')} />
        </div>
      )}

      {/* ── Walk-Forward Settings ── */}
      <SectionHeader title="Walk-Forward Settings" />
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <LabeledNumber label="Number of folds" value={cfg.n_folds}
          min={2} max={20} step={1} onChange={numSet('n_folds')} />
        <LabeledNumber label="Test window (trading days)" value={cfg.test_window_days}
          min={10} max={504} step={1} onChange={numSet('test_window_days')} />
        <LabeledNumber label="Purge days between train/test" value={cfg.purge_days}
          min={0} max={120} step={1} onChange={numSet('purge_days')} />
      </div>
      {cfg.purge_days < cfg.holding_days && (
        <div style={{ background: '#2a1515', border: '1px solid #7f1d1d', borderRadius: 4,
          padding: '6px 10px', fontSize: 11, color: '#fca5a5' }}>
          ⚠ purge_days ({cfg.purge_days}) &lt; holding_days ({cfg.holding_days}).
          This will raise an assertion error. Purge days must be ≥ holding period.
        </div>
      )}
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
        <Toggle label="Optimise MC quantiles on training window"
          value={cfg.optimise_mc_params_on_train}
          onChange={v => set('optimise_mc_params_on_train', v)} />
      </div>
      {cfg.optimise_mc_params_on_train && (
        <div style={{ fontSize: 11, color: '#888', background: '#0d0d1a', borderRadius: 4, padding: '6px 10px' }}>
          SL grid: [{cfg.sl_quantile_grid.join(', ')}] · TP grid: [{cfg.tp_quantile_grid.join(', ')}]
          <br />
          <span style={{ color: '#555', fontSize: 10 }}>
            Edit sl_quantile_grid / tp_quantile_grid via API for custom search values.
          </span>
        </div>
      )}
    </div>
  );
}

// ── MC results extras section ─────────────────────────────────────────────

function MCDetailsSection({
  mcTradeDetails, mcAggStats,
}: {
  mcTradeDetails: MCTradeDetail[];
  mcAggStats: MCAggregateStats;
}) {
  const [open, setOpen] = useState(false);
  const pct = (v: number | null) => v == null ? '—' : `${(v * 100).toFixed(1)}%`;
  const num = (v: number | null, d = 3) => v == null ? '—' : v.toFixed(d);

  return (
    <div style={{ marginTop: 16 }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          background: open ? '#1e1e3f' : 'none', border: '1px solid #2d2d4e',
          color: open ? '#818cf8' : '#666', borderRadius: 4,
          padding: '4px 12px', fontSize: 11, cursor: 'pointer', marginBottom: open ? 12 : 0,
        }}
      >
        {open ? '▲ Hide Monte Carlo Details' : '▼ Show Monte Carlo Details'}
      </button>

      {open && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {/* Aggregate stats */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 8 }}>
            {[
              ['Mean P(TP hit)',       pct(mcAggStats.mean_p_tp)],
              ['Mean σ at entry',      pct(mcAggStats.mean_sigma_at_entry)],
              ['Filtered (EV gate)',   pct(mcAggStats.fraction_filtered_ev)],
              ['Filtered (RR gate)',   pct(mcAggStats.fraction_filtered_rr)],
              ['Filtered (P(TP) gate)',pct(mcAggStats.fraction_filtered_p_tp)],
              ['BE trail activations', String(mcAggStats.breakeven_trail_activations ?? 0)],
              ['Candidates evaluated', String(mcAggStats.total_candidates_evaluated ?? 0)],
              ['Trades entered',       String(mcAggStats.total_trades_entered ?? 0)],
            ].map(([label, val]) => (
              <div key={label} style={{
                background: '#1a1a2e', border: '1px solid #2d2d4e', borderRadius: 6,
                padding: '8px 12px',
              }}>
                <div style={{ fontSize: 10, color: '#555', textTransform: 'uppercase', marginBottom: 2 }}>{label}</div>
                <div style={{ fontSize: 14, fontWeight: 600, color: '#a5b4fc', fontFamily: 'monospace' }}>{val}</div>
              </div>
            ))}
          </div>

          {/* Per-trade MC table */}
          {mcTradeDetails.length > 0 && (
            <div>
              <div style={{ fontSize: 10, color: '#666', marginBottom: 6 }}>
                Per-trade Monte Carlo details · {mcTradeDetails.length} trades
              </div>
              <div style={{ overflowX: 'auto', maxHeight: 300, overflowY: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10, fontFamily: 'monospace' }}>
                  <thead style={{ position: 'sticky', top: 0, background: '#0d0d1a' }}>
                    <tr style={{ borderBottom: '1px solid #2d2d4e' }}>
                      {['Ticker', 'Entry', 'SL raw', 'SL applied', 'TP', 'R:R', 'P(TP)', 'EV', 'σ ann', 'Exit'].map(h => (
                        <th key={h} style={{ padding: '4px 8px', color: '#555', fontWeight: 500, textAlign: 'right', whiteSpace: 'nowrap' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {mcTradeDetails.map((t, i) => (
                      <tr key={i} style={{ borderBottom: '1px solid #1a1a2e', background: i % 2 === 0 ? 'transparent' : '#0a0a18' }}>
                        <td style={{ padding: '3px 8px', color: '#a0a0c0', textAlign: 'right' }}>{t.ticker}</td>
                        <td style={{ padding: '3px 8px', color: '#666',    textAlign: 'right' }}>{t.entry_date}</td>
                        <td style={{ padding: '3px 8px', color: '#888',    textAlign: 'right' }}>{num(t.sl_raw, 2)}</td>
                        <td style={{ padding: '3px 8px', color: '#888',    textAlign: 'right' }}>{num(t.sl_applied, 2)}</td>
                        <td style={{ padding: '3px 8px', color: '#888',    textAlign: 'right' }}>{num(t.tp, 2)}</td>
                        <td style={{ padding: '3px 8px', color: '#a5b4fc', textAlign: 'right' }}>{num(t.rr, 2)}</td>
                        <td style={{ padding: '3px 8px', color: (t.p_tp ?? 0) >= 0.5 ? '#4ade80' : '#f87171', textAlign: 'right' }}>{pct(t.p_tp)}</td>
                        <td style={{ padding: '3px 8px', color: (t.ev ?? 0) >= 0 ? '#4ade80' : '#f87171', textAlign: 'right' }}>{num(t.ev, 3)}</td>
                        <td style={{ padding: '3px 8px', color: '#888',    textAlign: 'right' }}>{pct(t.sigma_annual)}</td>
                        <td style={{ padding: '3px 8px', color: t.exit_reason === 'STOP_LOSS' ? '#f87171' : t.exit_reason === 'TAKE_PROFIT' ? '#4ade80' : '#888', textAlign: 'right', whiteSpace: 'nowrap' }}>
                          {t.exit_reason}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── EMA price chart component ─────────────────────────────────────────────

function EmaChart({ data, ticker, startDate, endDate }: { data: EmaPoint[]; ticker: string; startDate?: string; endDate?: string }) {
  // Clip to the equity curve date range so both axes share the same x domain
  const clipped = (startDate && endDate)
    ? data.filter(d => d.date >= startDate && d.date <= endDate)
    : data;

  const step = Math.max(1, Math.floor(clipped.length / 500));
  const sampled = clipped.filter((d, i) =>
    i % step === 0 || i === clipped.length - 1 ||
    d.buySignal != null || d.sellSignal != null || d.stopSignal != null
  );
  const xTickFmt = (d: string) => d?.slice(0, 4) ?? '';

  // Y-axis domain with 2% padding
  const prices = clipped.map(d => d.price);
  const minP = Math.min(...prices);
  const maxP = Math.max(...prices);
  const pad = (maxP - minP) * 0.02;
  const yDomain: [number, number] = [minP - pad, maxP + pad];

  return (
    <div style={{ height: 180, marginBottom: 16 }}>
      <div style={{ fontSize: 10, color: '#4f46e5', textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 700, marginBottom: 6 }}>
        {ticker} Price · EMA 12 · EMA 26
      </div>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={sampled} syncId="backtest-charts" margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <XAxis dataKey="date" tickFormatter={xTickFmt} tick={{ fontSize: 10, fill: '#666' }} minTickGap={40} />
          <YAxis domain={yDomain} tickFormatter={v => v.toFixed(0)} tick={{ fontSize: 10, fill: '#666' }} width={52} />
          <Tooltip
            content={({ active, payload, label }: any) => {
              if (!active || !payload?.length) return null;
              return (
                <div style={{ background: '#1a1a2e', border: '1px solid #2d2d4e', borderRadius: 6, padding: '8px 12px', fontSize: 11 }}>
                  <div style={{ color: '#888', marginBottom: 4 }}>{label}</div>
                  {payload.filter((p: any) => p.value != null && !['buySignal','sellSignal','stopSignal'].includes(p.dataKey)).map((p: any) => (
                    <div key={p.dataKey} style={{ color: p.color, display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                      <span>{p.name}</span>
                      <span style={{ fontFamily: 'monospace' }}>{Number(p.value).toFixed(2)}</span>
                    </div>
                  ))}
                </div>
              );
            }}
          />
          <Legend wrapperStyle={{ fontSize: 10, paddingTop: 4 }} />
          <Line type="monotone" dataKey="price" name="Price" stroke="#6b7280" strokeWidth={2} dot={false} connectNulls />
          <Line type="monotone" dataKey="ema12" name="EMA 12" stroke="#34d399" strokeWidth={1} dot={false} connectNulls />
          <Line type="monotone" dataKey="ema26" name="EMA 26" stroke="#f59e0b" strokeWidth={1} dot={false} connectNulls />
          <Line dataKey="buySignal"  stroke="none" strokeWidth={0} dot={<BuyDot />}  activeDot={false} legendType="none" isAnimationActive={false} />
          <Line dataKey="sellSignal" stroke="none" strokeWidth={0} dot={<SellDot />} activeDot={false} legendType="none" isAnimationActive={false} />
          <Line dataKey="stopSignal" stroke="none" strokeWidth={0} dot={<StopDot />} activeDot={false} legendType="none" isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Main Widget ───────────────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-unused-vars
interface Props { tabId: string }

// Client-side benchmark inference (mirrors server logic) for instant UI feedback
function inferBenchmarkLocal(ticker: string): string {
  const t = ticker.toUpperCase();
  if (t.endsWith('-USD') || t.endsWith('-USDT') || t.endsWith('-BTC')) return 'BTC-USD';
  if (t.endsWith('.BK'))  return '^SET.BK';
  if (t.endsWith('.L'))   return '^FTSE';
  if (t.endsWith('.T'))   return '^N225';
  if (t.endsWith('.AX'))  return '^AXJO';
  if (t.endsWith('.HK'))  return '^HSI';
  if (t.endsWith('.DE'))  return '^GDAXI';
  if (t.endsWith('.TO'))  return '^GSPTSE';
  return 'SPY';
}

export function BacktestWidget({ tabId: _ }: Props) {
  // ── Top-level engine mode ─────────────────────────────────────
  const [engineMode, setEngineMode] = useState<EngineMode>('normal');

  // ── Normal mode state ─────────────────────────────────────────
  const [mode, setMode]                 = useState<BacktestMode>('universe');
  const [singleTicker, setSingleTicker] = useState('AAPL');
  const [benchmark, setBenchmark]       = useState('SPY');
  const [benchmarkEdited, setBenchmarkEdited] = useState(false);
  const [config, setConfig]             = useState<BacktestConfig>(DEFAULT_CONFIG);
  const [running, setRunning]     = useState(false);
  const [result, setResult]       = useState<BacktestResult | null>(null);
  const [error, setError]         = useState<string | null>(null);
  const [phase, setPhase]         = useState<'config' | 'results'>('config');
  const [showPositions, setShowPositions] = useState(false);

  // ── MC mode state ─────────────────────────────────────────────
  const [mcConfig, setMcConfig]   = useState<MCBacktestRequest>(DEFAULT_MC_CONFIG);
  const [mcRunning, setMcRunning] = useState(false);
  const [mcResult, setMcResult]   = useState<MCBacktestResponse | null>(null);
  const [mcError, setMcError]     = useState<string | null>(null);
  const [mcPhase, setMcPhase]     = useState<'config' | 'results'>('config');
  const [showMcPositions, setShowMcPositions] = useState(false);

  // ── EMA chart state — separate per mode to avoid cross-clearing ──────────
  const [emaChartDataNormal, setEmaChartDataNormal] = useState<EmaPoint[] | null>(null);
  const [emaChartDataMC,     setEmaChartDataMC]     = useState<EmaPoint[] | null>(null);

  // Normal mode: fetch price + compute EMAs when EMA Cross result is shown in single-stock mode
  useEffect(() => {
    if (phase !== 'results' || !result || mode !== 'single' || config.strategy !== 'EMACrossStrategy') {
      setEmaChartDataNormal(null);
      return;
    }
    let cancelled = false;
    api.price(singleTicker.toUpperCase().trim(), '5y').then(data => {
      if (cancelled) return;
      setEmaChartDataNormal(buildEmaChartData(data.bars, result.trade_markers));
    }).catch(() => setEmaChartDataNormal(null));
    return () => { cancelled = true; };
  }, [phase, result, mode, singleTicker, config.strategy]);

  // MC mode: fetch price + compute EMAs when EMA Cross result is shown in single-stock mode
  useEffect(() => {
    if (mcPhase !== 'results' || !mcResult || !mcConfig.single_ticker || mcConfig.buy_strategy !== 'EMACrossStrategy') {
      setEmaChartDataMC(null);
      return;
    }
    let cancelled = false;
    api.price(mcConfig.single_ticker.trim().toUpperCase(), '5y').then(data => {
      if (cancelled) return;
      setEmaChartDataMC(buildEmaChartData(data.bars, mcResult.trade_markers));
    }).catch(() => setEmaChartDataMC(null));
    return () => { cancelled = true; };
  }, [mcPhase, mcResult, mcConfig.single_ticker, mcConfig.buy_strategy]);

  const update = (key: keyof BacktestConfig) => (v: string | number) =>
    setConfig(c => ({ ...c, [key]: typeof v === 'string' && key !== 'strategy' && key !== 'universe' && key !== 'optimizer' ? Number(v) : v }));

  const handleRun = async () => {
    setRunning(true);
    setError(null);
    try {
      const req: BacktestConfig = mode === 'single'
        ? { ...config, single_ticker: singleTicker.toUpperCase().trim(), benchmark_ticker: benchmark.toUpperCase().trim() || undefined }
        : { ...config, single_ticker: undefined, benchmark_ticker: undefined };
      const data = await api.runBacktest(req);
      setResult(data);
      setPhase('results');
    } catch (e: any) {
      setError(e.message ?? 'Unknown error');
    } finally {
      setRunning(false);
    }
  };

  const handleMcRun = async () => {
    // Validate single-stock mode
    if (mcConfig.single_ticker !== undefined && mcConfig.single_ticker !== null) {
      if (!mcConfig.single_ticker.trim()) {
        setMcError('Please enter a ticker symbol for Single Stock mode.');
        return;
      }
    }
    setMcRunning(true);
    setMcError(null);
    try {
      // Send undefined fields as absent (not empty string)
      const payload: MCBacktestRequest = {
        ...mcConfig,
        single_ticker:    mcConfig.single_ticker?.trim() || undefined,
        benchmark_ticker: mcConfig.benchmark_ticker?.trim() || undefined,
      };
      const data = await api.runMCBacktest(payload);
      setMcResult(data);
      setMcPhase('results');
    } catch (e: any) {
      setMcError(e.message ?? 'Unknown error');
    } finally {
      setMcRunning(false);
    }
  };

  // Extract unique tickers across all positions_chart rows (must be before any early return)
  const positionTickers = useMemo(() => {
    if (!result) return [];
    const tickerSet = new Set<string>();
    for (const row of result.positions_chart) {
      for (const key of Object.keys(row)) {
        if (key !== 'date') tickerSet.add(key);
      }
    }
    return Array.from(tickerSet).sort();
  }, [result]);

  const mcPositionTickers = useMemo(() => {
    if (!mcResult) return [];
    const tickerSet = new Set<string>();
    for (const row of mcResult.positions_chart) {
      for (const key of Object.keys(row)) {
        if (key !== 'date') tickerSet.add(key);
      }
    }
    return Array.from(tickerSet).sort();
  }, [mcResult]);

  // ── Engine mode selector (shared) ─────────────────────────────
  const engineModeSelector = (
    <div style={{ display: 'flex', gap: 0, alignSelf: 'flex-start', border: '1px solid #2d2d4e', borderRadius: 6, overflow: 'hidden', marginBottom: 4 }}>
      {(['normal', 'mc'] as EngineMode[]).map(em => (
        <button key={em} onClick={() => setEngineMode(em)}
          style={{
            padding: '5px 14px', fontSize: 11, cursor: 'pointer', border: 'none',
            background: engineMode === em ? '#4f46e5' : '#111128',
            color: engineMode === em ? '#fff' : '#555',
            fontWeight: engineMode === em ? 700 : 400,
          }}
        >
          {em === 'normal' ? 'Normal' : 'Monte Carlo Integrated'}
        </button>
      ))}
    </div>
  );

  // ── MC mode: config phase ─────────────────────────────────────
  if (engineMode === 'mc' && mcPhase === 'config') {
    return (
      <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12, height: '100%', overflowY: 'auto' }}>
        {engineModeSelector}
        <MCConfigPanel cfg={mcConfig} onChange={patch => setMcConfig(c => ({ ...c, ...patch }))} />
        {mcError && (
          <div style={{ background: '#2a1515', border: '1px solid #7f1d1d', borderRadius: 4, padding: '8px 12px', fontSize: 11, color: '#fca5a5' }}>
            {mcError}
          </div>
        )}
        <button onClick={handleMcRun} disabled={mcRunning} style={{
          background: mcRunning ? '#1d1d3a' : '#4f46e5', color: mcRunning ? '#555' : '#fff',
          border: 'none', borderRadius: 6, padding: '10px 24px', fontSize: 13, fontWeight: 600,
          cursor: mcRunning ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', gap: 8, alignSelf: 'flex-start',
        }}>
          {mcRunning && <span style={{ display: 'inline-block', width: 14, height: 14, border: '2px solid #666', borderTopColor: '#aaa', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />}
          {mcRunning ? 'Running MC…' : 'Run MC Backtest'}
        </button>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  // ── MC mode: results phase ─────────────────────────────────────
  if (engineMode === 'mc' && mcPhase === 'results') {
    if (!mcResult) return null;
    const m = mcResult.metrics;
    const isMcSingle = Boolean(mcConfig.single_ticker);
    const chartData = buildChartData(mcResult.equity_curve, mcResult.benchmark_curve, isMcSingle ? (mcResult.buyhold_curve ?? null) : null, mcResult.trade_markers);
    const step = Math.max(1, Math.floor(chartData.length / 500));
    const sampledData = chartData.filter((d, i) =>
      i % step === 0 || i === chartData.length - 1 ||
      d.buySignal != null || d.sellSignal != null || d.stopSignal != null
    );
    const xTickFmt = (d: string) => d?.slice(0, 4) ?? '';
    const mcSubtitle = isMcSingle
      ? `MC · ${mcConfig.buy_strategy} · ${mcConfig.single_ticker}`
      : `MC · ${mcConfig.buy_strategy} · ${UNIVERSES.find(u => u.value === mcConfig.universe)?.label}`;
    return (
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 12px', borderBottom: '1px solid #2d2d4e', flexShrink: 0 }}>
          <button onClick={() => setMcPhase('config')} style={{ background: 'none', border: '1px solid #2d2d4e', color: '#888', borderRadius: 4, padding: '3px 10px', fontSize: 11, cursor: 'pointer' }}>← Reconfigure</button>
          <span style={{ fontSize: 11, color: '#888' }}>{mcSubtitle}</span>
          <span style={{ fontSize: 10, background: '#2d1f5e', color: '#a78bfa', borderRadius: 3, padding: '1px 6px' }}>Monte Carlo Integrated</span>
          {mcError && <span style={{ fontSize: 11, color: '#f87171', marginLeft: 'auto' }}>{mcError}</span>}
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: '12px 12px 16px' }}>
          <div style={{ height: 220, marginBottom: 16 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={sampledData} syncId="backtest-charts" margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                <XAxis dataKey="date" tickFormatter={xTickFmt} tick={{ fontSize: 10, fill: '#666' }} minTickGap={40} />
                <YAxis tickFormatter={v => `${v >= 0 ? '+' : ''}${v.toFixed(0)}%`} tick={{ fontSize: 10, fill: '#666' }} width={52} />
                <Tooltip content={<ChartTooltip />} />
                <Legend wrapperStyle={{ fontSize: 10, paddingTop: 4 }} />
                {mcResult.fold_boundaries.map((d, i) => <ReferenceLine key={i} x={d} stroke="#2d2d4e" strokeDasharray="3 3" />)}
                <Line type="monotone" dataKey="benchmark" name="Benchmark" stroke="#374151" strokeWidth={1} dot={false} strokeDasharray="4 2" connectNulls />
                {isMcSingle && mcResult.buyhold_curve && (
                  <Line type="monotone" dataKey="buyhold" name={`Buy & Hold ${mcConfig.single_ticker}`} stroke="#f59e0b" strokeWidth={1} dot={false} strokeDasharray="4 2" connectNulls />
                )}
                <Line type="monotone" dataKey="portfolio" name="Portfolio (MC)" stroke="#a78bfa" strokeWidth={1.5} dot={false} connectNulls />
                <Line dataKey="buySignal"  stroke="none" strokeWidth={0} dot={<BuyDot />}  activeDot={false} legendType="none" isAnimationActive={false} />
                <Line dataKey="sellSignal" stroke="none" strokeWidth={0} dot={<SellDot />} activeDot={false} legendType="none" isAnimationActive={false} />
                <Line dataKey="stopSignal" stroke="none" strokeWidth={0} dot={<StopDot />} activeDot={false} legendType="none" isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* EMA price chart — shown when EMA Cross strategy is used in MC single-stock mode */}
          {emaChartDataMC && isMcSingle && mcConfig.buy_strategy === 'EMACrossStrategy' && (
            <EmaChart
              data={emaChartDataMC}
              ticker={mcConfig.single_ticker!.toUpperCase()}
              startDate={chartData[0]?.date}
              endDate={chartData[chartData.length - 1]?.date}
            />
          )}

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(110px, 1fr))', gap: 8 }}>
            <KpiCard label="Total Return"    value={fmtPct(m.total_return)}    color={metricColor(m.total_return,    'return')} />
            <KpiCard label="CAGR"            value={fmtPct(m.cagr)}            color={metricColor(m.cagr,            'return')} />
            <KpiCard label="Sharpe Ratio"    value={fmtNum(m.sharpe_ratio)}    color={m.sharpe_ratio != null ? (m.sharpe_ratio >= 1 ? '#4ade80' : m.sharpe_ratio >= 0 ? '#facc15' : '#f87171') : '#888'} />
            <KpiCard label="Max Drawdown"    value={fmtPct(m.max_drawdown)}    color={metricColor(m.max_drawdown,    'drawdown')} />
            <KpiCard label="Calmar Ratio"    value={fmtNum(m.calmar_ratio)}    color={m.calmar_ratio != null ? (m.calmar_ratio >= 1 ? '#4ade80' : '#facc15') : '#888'} />
            <KpiCard label="Ann. Volatility" value={fmtPct(m.volatility_ann)}  color="#888" />
            <KpiCard label="Avg Trade Ret"   value={fmtPct(m.avg_trade_return)} color={metricColor(m.avg_trade_return, 'return')} />
            <KpiCard label="Win Rate"        value={fmtPct(m.win_rate, 0)}     color={metricColor(m.win_rate,        'win_rate')} />
            <KpiCard label="Avg Win"         value={fmtPct(m.avg_win)}         color="#4ade80" />
            <KpiCard label="Avg Loss"        value={fmtPct(m.avg_loss)}        color="#f87171" />
            <KpiCard label="Reward / Risk"   value={fmtNum(m.reward_to_risk)}  color={metricColor(m.reward_to_risk, 'rr')} />
            <KpiCard label="Total Trades"    value={String(m.total_trades)}    color="#888" sub={`${m.long_trades}L / ${m.short_trades}S`} />
          </div>
          {(mcResult.positions_chart.length > 0 || mcResult.trade_log.length > 0) && (
            <div style={{ marginTop: 16 }}>
              <button onClick={() => setShowMcPositions(v => !v)} style={{
                background: showMcPositions ? '#1e1e3f' : 'none', border: '1px solid #2d2d4e',
                color: showMcPositions ? '#818cf8' : '#666', borderRadius: 4,
                padding: '4px 12px', fontSize: 11, cursor: 'pointer', marginBottom: showMcPositions ? 12 : 0,
              }}>
                {showMcPositions ? '▲ Hide Positions' : '▼ Show Positions'}
              </button>
              {showMcPositions && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                  {mcResult.positions_chart.length > 0 && (
                    <div>
                      <div style={{ fontSize: 10, color: '#666', marginBottom: 8 }}>Open positions by weight</div>
                      <div style={{ height: 180 }}>
                        <ResponsiveContainer width="100%" height="100%">
                          <BarChart data={mcResult.positions_chart} margin={{ top: 4, right: 8, bottom: 0, left: 0 }} stackOffset="sign">
                            <XAxis dataKey="date" tickFormatter={(d: string) => d?.slice(0, 4) ?? ''} tick={{ fontSize: 10, fill: '#666' }} minTickGap={40} />
                            <YAxis tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`} tick={{ fontSize: 10, fill: '#666' }} width={42} />
                            <Tooltip content={<PositionsTooltip />} />
                            {mcPositionTickers.map((ticker, i) => (
                              <Bar key={ticker} dataKey={ticker} name={ticker} stackId="pos" fill={POSITION_COLORS[i % POSITION_COLORS.length]} isAnimationActive={false} />
                            ))}
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                  )}
                  {mcResult.trade_log.length > 0 && (
                    <div>
                      <div style={{ fontSize: 10, color: '#666', marginBottom: 6 }}>Trade history · {mcResult.trade_log.length} trades</div>
                      <div style={{ overflowX: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11, fontFamily: 'monospace' }}>
                          <thead>
                            <tr style={{ borderBottom: '1px solid #2d2d4e' }}>
                              {['Asset', 'Buy Date', 'Sell Date', 'Buy Price', 'Sell Price', 'Position $', 'PnL %', 'PnL', 'Balance', 'Exit'].map(h => (
                                <th key={h} style={{ padding: '4px 8px', color: '#666', fontWeight: 500, textAlign: 'right', whiteSpace: 'nowrap' }}>{h}</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {mcResult.trade_log.map((t: any, i: number) => {
                              const win = (t.pnl ?? 0) >= 0;
                              return (
                                <tr key={i} style={{ borderBottom: '1px solid #1a1a2e', background: i % 2 === 0 ? 'transparent' : '#0d0d1a' }}>
                                  <td style={{ padding: '3px 8px', color: '#a0a0c0', textAlign: 'right' }}>{t.asset}</td>
                                  <td style={{ padding: '3px 8px', color: '#666', textAlign: 'right' }}>{t.entry_date}</td>
                                  <td style={{ padding: '3px 8px', color: '#666', textAlign: 'right' }}>{t.exit_date}</td>
                                  <td style={{ padding: '3px 8px', color: '#888', textAlign: 'right' }}>{(t.entry_price ?? 0).toFixed(2)}</td>
                                  <td style={{ padding: '3px 8px', color: '#888', textAlign: 'right' }}>{(t.exit_price ?? 0).toFixed(2)}</td>
                                  <td style={{ padding: '3px 8px', color: '#a0a0c0', textAlign: 'right' }}>
                                    {(() => {
                                      const rp = t.return_pct ?? 0;
                                      const pos = Math.abs(rp) > 1e-9 ? Math.abs((t.pnl ?? 0) / rp) : null;
                                      return pos != null ? pos.toLocaleString('en-US', { maximumFractionDigits: 0 }) : '—';
                                    })()}
                                  </td>
                                  <td style={{ padding: '3px 8px', color: win ? '#4ade80' : '#f87171', textAlign: 'right' }}>
                                    {(t.return_pct ?? 0) >= 0 ? '+' : ''}{((t.return_pct ?? 0) * 100).toFixed(2)}%
                                  </td>
                                  <td style={{ padding: '3px 8px', color: win ? '#4ade80' : '#f87171', textAlign: 'right' }}>
                                    {(t.pnl ?? 0) >= 0 ? '+' : ''}{(t.pnl ?? 0).toLocaleString('en-US', { maximumFractionDigits: 0 })}
                                  </td>
                                  <td style={{ padding: '3px 8px', color: '#e0e0f0', textAlign: 'right' }}>
                                    {(t.balance ?? 0).toLocaleString('en-US', { maximumFractionDigits: 0 })}
                                  </td>
                                  <td style={{ padding: '3px 8px', color: t.exit_reason === 'STOP_LOSS' ? '#f87171' : t.exit_reason === 'TAKE_PROFIT' ? '#4ade80' : '#888', textAlign: 'right', whiteSpace: 'nowrap' }}>
                                    {t.exit_reason ?? (t.stop_triggered ? 'STOP_LOSS' : '—')}
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
          {mcResult.mc_trade_details && mcResult.mc_aggregate_stats && (
            <MCDetailsSection mcTradeDetails={mcResult.mc_trade_details} mcAggStats={mcResult.mc_aggregate_stats} />
          )}
        </div>
      </div>
    );
  }

  // ── Normal mode: config phase ─────────────────────────────────
  if (phase === 'config') {
    return (
      <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 16, height: '100%', overflowY: 'auto' }}>
        {engineModeSelector}
        {/* Mode toggle */}
        <div style={{ display: 'flex', gap: 0, alignSelf: 'flex-start', border: '1px solid #2d2d4e', borderRadius: 6, overflow: 'hidden' }}>
          {(['universe', 'single'] as BacktestMode[]).map(m => (
            <button
              key={m}
              onClick={() => setMode(m)}
              style={{
                padding: '5px 14px', fontSize: 11, cursor: 'pointer', border: 'none',
                background: mode === m ? '#3730a3' : '#111128',
                color: mode === m ? '#e0e0ff' : '#666',
                fontWeight: mode === m ? 600 : 400,
              }}
            >
              {m === 'universe' ? 'Universe' : 'Single Stock'}
            </button>
          ))}
        </div>

        {/* Strategy row (always shown) */}
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <LabeledSelect
            label="Trading Strategy"
            value={config.strategy}
            options={STRATEGIES}
            onChange={update('strategy')}
          />

          {/* Universe mode: universe + optimizer selectors */}
          {mode === 'universe' && (
            <LabeledSelect
              label="Universe"
              value={config.universe}
              options={UNIVERSES}
              onChange={update('universe')}
            />
          )}

          {/* Single stock mode: ticker + benchmark inputs */}
          {mode === 'single' && (
            <>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4, flex: 1, minWidth: 120 }}>
                <label style={{ fontSize: 10, color: '#888', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Ticker
                </label>
                <input
                  type="text"
                  value={singleTicker}
                  onChange={e => {
                    const t = e.target.value.toUpperCase();
                    setSingleTicker(t);
                    if (!benchmarkEdited) setBenchmark(inferBenchmarkLocal(t));
                  }}
                  placeholder="e.g. AAPL"
                  style={{
                    background: '#111128', color: '#e0e0f0', border: '1px solid #2d2d4e',
                    borderRadius: 4, padding: '5px 8px', fontSize: 12, width: '100%',
                  }}
                />
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4, flex: 1, minWidth: 120 }}>
                <label style={{ fontSize: 10, color: '#888', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Benchmark
                </label>
                <input
                  type="text"
                  value={benchmark}
                  onChange={e => {
                    setBenchmark(e.target.value.toUpperCase());
                    setBenchmarkEdited(true);
                  }}
                  onBlur={e => { if (!e.target.value.trim()) { setBenchmark(inferBenchmarkLocal(singleTicker)); setBenchmarkEdited(false); } }}
                  placeholder="e.g. SPY"
                  style={{
                    background: '#111128', color: benchmarkEdited ? '#e0e0f0' : '#a0a0c0',
                    border: `1px solid ${benchmarkEdited ? '#4f46e5' : '#2d2d4e'}`,
                    borderRadius: 4, padding: '5px 8px', fontSize: 12, width: '100%',
                  }}
                />
                <div style={{ fontSize: 9, color: '#555' }}>
                  {benchmarkEdited ? 'custom' : 'auto-detected'} · full allocation · no optimizer
                </div>
              </div>
            </>
          )}
        </div>

        {/* Optimizer row — only shown in universe mode */}
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          {mode === 'universe' && (
            <LabeledSelect
              label="Portfolio Optimization"
              value={config.optimizer}
              options={OPTIMIZERS}
              onChange={update('optimizer')}
            />
          )}
          <LabeledSelect
            label="Backtest Period"
            value={config.period_years}
            options={PERIODS}
            onChange={v => setConfig(c => ({ ...c, period_years: Number(v) }))}
          />
        </div>

        {/* Capital & stop-loss */}
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <LabeledNumber
            label="Initial Capital"
            value={config.initial_capital}
            min={1000}
            max={100_000_000}
            step={10000}
            onChange={update('initial_capital')}
            suffix="USD"
          />
          <LabeledNumber
            label="Max Stop-Loss"
            value={config.max_stop_loss_pct}
            min={0.5}
            max={50}
            step={0.5}
            onChange={update('max_stop_loss_pct')}
            suffix="%"
          />
        </div>

        {error && (
          <div style={{ background: '#2a1515', border: '1px solid #7f1d1d', borderRadius: 4, padding: '8px 12px', fontSize: 11, color: '#fca5a5' }}>
            {error}
          </div>
        )}

        <button
          onClick={handleRun}
          disabled={running}
          style={{
            background: running ? '#1d1d3a' : '#3730a3',
            color: running ? '#555' : '#e0e0ff',
            border: 'none', borderRadius: 6, padding: '10px 24px',
            fontSize: 13, fontWeight: 600, cursor: running ? 'not-allowed' : 'pointer',
            display: 'flex', alignItems: 'center', gap: 8, alignSelf: 'flex-start',
          }}
        >
          {running && (
            <span style={{ display: 'inline-block', width: 14, height: 14, border: '2px solid #666', borderTopColor: '#aaa', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
          )}
          {running ? 'Running…' : 'Run Backtest'}
        </button>

        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  // ── Normal mode: results phase ────────────────────────────────
  if (!result) return null;

  const m = result.metrics;
  const chartData = buildChartData(result.equity_curve, result.benchmark_curve, result.buyhold_curve, result.trade_markers);
  const stratLabel = STRATEGIES.find(s => s.value === config.strategy)?.label ?? config.strategy;
  const scopeLabel = mode === 'single'
    ? `${singleTicker.toUpperCase()} vs ${benchmark.toUpperCase()}`
    : (UNIVERSES.find(u => u.value === config.universe)?.label ?? config.universe);

  // Sample chart data to reduce rendering (max 500 points), but always keep marker dates
  const step = Math.max(1, Math.floor(chartData.length / 500));
  const sampledData = chartData.filter((d, i) =>
    i % step === 0 || i === chartData.length - 1 ||
    d.buySignal != null || d.sellSignal != null || d.stopSignal != null
  );


  // X-axis tick formatter — show year only
  const xTickFmt = (d: string) => d?.slice(0, 4) ?? '';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* Header bar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 12px', borderBottom: '1px solid #2d2d4e', flexShrink: 0, flexWrap: 'wrap' }}>
        <button
          onClick={() => setPhase('config')}
          style={{ background: 'none', border: '1px solid #2d2d4e', color: '#888', borderRadius: 4, padding: '3px 10px', fontSize: 11, cursor: 'pointer' }}
        >← Reconfigure</button>
        <span style={{ fontSize: 11, color: '#888' }}>{stratLabel} · {scopeLabel} · {config.period_years}Y</span>
        {error && <span style={{ fontSize: 11, color: '#f87171', marginLeft: 'auto' }}>{error}</span>}
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 12px 16px' }}>
        {/* Equity chart */}
        <div style={{ height: 220, marginBottom: 16 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={sampledData} syncId="backtest-charts" margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
              <XAxis dataKey="date" tickFormatter={xTickFmt} tick={{ fontSize: 10, fill: '#666' }} minTickGap={40} />
              <YAxis tickFormatter={v => `${v >= 0 ? '+' : ''}${v.toFixed(0)}%`} tick={{ fontSize: 10, fill: '#666' }} width={52} />
              <Tooltip content={<ChartTooltip />} />
              <Legend wrapperStyle={{ fontSize: 10, paddingTop: 4 }} />
              {result.fold_boundaries.map((d, i) => (
                <ReferenceLine key={i} x={d} stroke="#2d2d4e" strokeDasharray="3 3" />
              ))}
              {result.buyhold_curve && (
                <Line type="monotone" dataKey="buyhold" name="Buy & Hold" stroke="#4b5563" strokeWidth={1} dot={false} connectNulls />
              )}
              <Line type="monotone" dataKey="benchmark" name="Benchmark" stroke="#374151" strokeWidth={1} dot={false} strokeDasharray="4 2" connectNulls />
              <Line type="monotone" dataKey="portfolio" name="Portfolio" stroke="#818cf8" strokeWidth={1.5} dot={false} connectNulls />
              <Line dataKey="buySignal"  name="Buy"  stroke="none" strokeWidth={0} dot={<BuyDot />}  activeDot={false} legendType="none" isAnimationActive={false} />
              <Line dataKey="sellSignal" name="Sell" stroke="none" strokeWidth={0} dot={<SellDot />} activeDot={false} legendType="none" isAnimationActive={false} />
              <Line dataKey="stopSignal" name="Stop" stroke="none" strokeWidth={0} dot={<StopDot />} activeDot={false} legendType="none" isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* EMA price chart — shown when EMA Cross strategy is used in single-stock mode */}
        {emaChartDataNormal && mode === 'single' && config.strategy === 'EMACrossStrategy' && (
          <EmaChart
            data={emaChartDataNormal}
            ticker={singleTicker.toUpperCase()}
            startDate={chartData[0]?.date}
            endDate={chartData[chartData.length - 1]?.date}
          />
        )}

        {/* KPI cards — 10 metrics */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(110px, 1fr))', gap: 8 }}>
          <KpiCard
            label="Total Return"
            value={fmtPct(m.total_return)}
            color={metricColor(m.total_return, 'return')}
          />
          <KpiCard
            label="CAGR"
            value={fmtPct(m.cagr)}
            color={metricColor(m.cagr, 'return')}
          />
          <KpiCard
            label="Sharpe Ratio"
            value={fmtNum(m.sharpe_ratio)}
            color={m.sharpe_ratio != null ? (m.sharpe_ratio >= 1 ? '#4ade80' : m.sharpe_ratio >= 0 ? '#facc15' : '#f87171') : '#888'}
          />
          <KpiCard
            label="Max Drawdown"
            value={fmtPct(m.max_drawdown)}
            color={metricColor(m.max_drawdown, 'drawdown')}
          />
          <KpiCard
            label="Calmar Ratio"
            value={fmtNum(m.calmar_ratio)}
            color={m.calmar_ratio != null ? (m.calmar_ratio >= 1 ? '#4ade80' : '#facc15') : '#888'}
          />
          <KpiCard
            label="Ann. Volatility"
            value={fmtPct(m.volatility_ann)}
            color="#888"
          />
          <KpiCard
            label="Avg Trade Ret"
            value={fmtPct(m.avg_trade_return)}
            color={metricColor(m.avg_trade_return, 'return')}
          />
          <KpiCard
            label="Win Rate"
            value={fmtPct(m.win_rate, 0)}
            color={metricColor(m.win_rate, 'win_rate')}
          />
          <KpiCard
            label="Avg Win"
            value={fmtPct(m.avg_win)}
            color="#4ade80"
          />
          <KpiCard
            label="Avg Loss"
            value={fmtPct(m.avg_loss)}
            color="#f87171"
          />
          <KpiCard
            label="Reward / Risk"
            value={fmtNum(m.reward_to_risk)}
            color={metricColor(m.reward_to_risk, 'rr')}
          />
          <KpiCard
            label="Total Trades"
            value={String(m.total_trades)}
            color="#888"
            sub={`${m.long_trades}L / ${m.short_trades}S`}
          />
        </div>

        {/* Positions toggle */}
        {(result.positions_chart.length > 0 || result.trade_log.length > 0) && (
          <div style={{ marginTop: 16 }}>
            <button
              onClick={() => setShowPositions(v => !v)}
              style={{
                background: showPositions ? '#1e1e3f' : 'none',
                border: '1px solid #2d2d4e',
                color: showPositions ? '#818cf8' : '#666',
                borderRadius: 4,
                padding: '4px 12px',
                fontSize: 11,
                cursor: 'pointer',
                marginBottom: showPositions ? 12 : 0,
              }}
            >
              {showPositions ? '▲ Hide Positions' : '▼ Show Positions'}
            </button>

            {showPositions && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

                {/* Weight bar chart */}
                {result.positions_chart.length > 0 && (
                  <div>
                    <div style={{ fontSize: 10, color: '#666', marginBottom: 8 }}>
                      Open positions by weight · positive = long · negative = short
                    </div>
                    <div style={{ height: 180 }}>
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart
                          data={result.positions_chart}
                          margin={{ top: 4, right: 8, bottom: 0, left: 0 }}
                          stackOffset="sign"
                        >
                          <XAxis
                            dataKey="date"
                            tickFormatter={(d: string) => d?.slice(0, 4) ?? ''}
                            tick={{ fontSize: 10, fill: '#666' }}
                            minTickGap={40}
                          />
                          <YAxis
                            tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`}
                            tick={{ fontSize: 10, fill: '#666' }}
                            width={42}
                          />
                          <Tooltip content={<PositionsTooltip />} />
                          {positionTickers.map((ticker, i) => (
                            <Bar
                              key={ticker}
                              dataKey={ticker}
                              name={ticker}
                              stackId="pos"
                              fill={POSITION_COLORS[i % POSITION_COLORS.length]}
                              isAnimationActive={false}
                            />
                          ))}
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                )}

                {/* Trade log table */}
                {result.trade_log.length > 0 && (
                  <div>
                    <div style={{ fontSize: 10, color: '#666', marginBottom: 6 }}>
                      Trade history · {result.trade_log.length} trades
                    </div>
                    <div style={{ overflowX: 'auto' }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11, fontFamily: 'monospace' }}>
                        <thead>
                          <tr style={{ borderBottom: '1px solid #2d2d4e' }}>
                            {['Asset', 'Buy Date', 'Sell Date', 'Buy Price', 'Sell Price', 'Position $', 'PnL %', 'PnL', 'Balance'].map(h => (
                              <th key={h} style={{ padding: '4px 8px', color: '#666', fontWeight: 500, textAlign: 'right', whiteSpace: 'nowrap' }}>
                                {h}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {result.trade_log.map((t, i) => {
                            const win = t.pnl >= 0;
                            return (
                              <tr key={i} style={{ borderBottom: '1px solid #1a1a2e', background: i % 2 === 0 ? 'transparent' : '#0d0d1a' }}>
                                <td style={{ padding: '3px 8px', color: '#a0a0c0', textAlign: 'right' }}>{t.asset}</td>
                                <td style={{ padding: '3px 8px', color: '#666',    textAlign: 'right' }}>{t.entry_date}</td>
                                <td style={{ padding: '3px 8px', color: '#666',    textAlign: 'right' }}>{t.exit_date}{t.stop_triggered ? ' ⊗' : ''}</td>
                                <td style={{ padding: '3px 8px', color: '#888',    textAlign: 'right' }}>{t.entry_price.toFixed(2)}</td>
                                <td style={{ padding: '3px 8px', color: '#888',    textAlign: 'right' }}>{t.exit_price.toFixed(2)}</td>
                                <td style={{ padding: '3px 8px', color: '#a0a0c0', textAlign: 'right' }}>
                                  {Math.abs(t.return_pct) > 1e-9
                                    ? Math.abs(t.pnl / t.return_pct).toLocaleString('en-US', { maximumFractionDigits: 0 })
                                    : '—'}
                                </td>
                                <td style={{ padding: '3px 8px', color: win ? '#4ade80' : '#f87171', textAlign: 'right' }}>
                                  {t.return_pct >= 0 ? '+' : ''}{(t.return_pct * 100).toFixed(2)}%
                                </td>
                                <td style={{ padding: '3px 8px', color: win ? '#4ade80' : '#f87171', textAlign: 'right' }}>
                                  {t.pnl >= 0 ? '+' : ''}{t.pnl.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                                </td>
                                <td style={{ padding: '3px 8px', color: '#e0e0f0', textAlign: 'right' }}>
                                  {t.balance.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
