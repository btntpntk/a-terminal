import { useState, useMemo } from 'react';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ReferenceLine,
  ResponsiveContainer, Legend, BarChart, Bar,
} from 'recharts';
import { api } from '../../lib/api';
import type { BacktestRequest, BacktestResponse, BacktestMetrics } from '../../types/api';

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
];

const UNIVERSES = [
  { value: 'SP500_SAMPLE',   label: 'S&P 500 Sample' },
  { value: 'THAI_LARGE_CAP', label: 'Thai Large Cap' },
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

  // ── Config phase ─────────────────────────────────────────────
  if (phase === 'config') {
    return (
      <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 16, height: '100%', overflowY: 'auto' }}>

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

  // ── Results phase ─────────────────────────────────────────────
  if (!result) return null;

  const m = result.metrics;
  const chartData = buildChartData(result.equity_curve, result.benchmark_curve, result.buyhold_curve, result.trade_markers);
  const stratLabel = STRATEGIES.find(s => s.value === config.strategy)?.label ?? config.strategy;
  const scopeLabel = mode === 'single'
    ? `${singleTicker.toUpperCase()} vs ${benchmark.toUpperCase()}`
    : (UNIVERSES.find(u => u.value === config.universe)?.label ?? config.universe);

  // Sample chart data to reduce rendering (max 500 points)
  const step = Math.max(1, Math.floor(chartData.length / 500));
  const sampledData = chartData.filter((_, i) => i % step === 0 || i === chartData.length - 1);


  // X-axis tick formatter — show year only
  const xTickFmt = (d: string) => d?.slice(0, 4) ?? '';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* Header bar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 12px', borderBottom: '1px solid #2d2d4e', flexShrink: 0 }}>
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
            <LineChart data={sampledData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
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
                            {['Asset', 'Buy Date', 'Sell Date', 'Buy Price', 'Sell Price', 'PnL %', 'PnL', 'Balance'].map(h => (
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
