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
  { value: 'RSIStrategy',                label: 'RSI (14)' },
  { value: 'VolatilityBreakoutStrategy', label: 'Volatility Breakout' },
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

function buildChartData(
  equity: Record<string, number>,
  benchmark: Record<string, number>,
): Array<{ date: string; portfolio: number; benchmark: number }> {
  const allDates = Array.from(new Set([...Object.keys(equity), ...Object.keys(benchmark)])).sort();
  return allDates.map(date => ({
    date,
    portfolio: equity[date] ?? NaN,
    benchmark: benchmark[date] ?? NaN,
  })).filter(d => !isNaN(d.portfolio) || !isNaN(d.benchmark));
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
          {p.name}: {p.value != null ? fmtCurrency(p.value) : '—'}
        </div>
      ))}
    </div>
  );
}

// ── Main Widget ───────────────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-unused-vars
interface Props { tabId: string }

export function BacktestWidget({ tabId: _ }: Props) {
  const [config, setConfig]       = useState<BacktestConfig>(DEFAULT_CONFIG);
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
      const data = await api.runBacktest(config);
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
        <div style={{ fontSize: 11, color: '#888' }}>Configure and run a walk-forward backtest.</div>

        {/* Row 1 */}
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <LabeledSelect
            label="Trading Strategy"
            value={config.strategy}
            options={STRATEGIES}
            onChange={update('strategy')}
          />
          <LabeledSelect
            label="Universe"
            value={config.universe}
            options={UNIVERSES}
            onChange={update('universe')}
          />
        </div>

        {/* Row 2 */}
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <LabeledSelect
            label="Portfolio Optimization"
            value={config.optimizer}
            options={OPTIMIZERS}
            onChange={update('optimizer')}
          />
          <LabeledSelect
            label="Backtest Period"
            value={config.period_years}
            options={PERIODS}
            onChange={v => setConfig(c => ({ ...c, period_years: Number(v) }))}
          />
        </div>

        {/* Row 3 */}
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
  const chartData = buildChartData(result.equity_curve, result.benchmark_curve);
  const stratLabel = STRATEGIES.find(s => s.value === config.strategy)?.label ?? config.strategy;
  const uniLabel   = UNIVERSES.find(u => u.value === config.universe)?.label ?? config.universe;

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
        <span style={{ fontSize: 11, color: '#888' }}>{stratLabel} · {uniLabel} · {config.period_years}Y</span>
        {error && <span style={{ fontSize: 11, color: '#f87171', marginLeft: 'auto' }}>{error}</span>}
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 12px 16px' }}>
        {/* Equity chart */}
        <div style={{ height: 220, marginBottom: 16 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={sampledData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
              <XAxis dataKey="date" tickFormatter={xTickFmt} tick={{ fontSize: 10, fill: '#666' }} minTickGap={40} />
              <YAxis tickFormatter={v => `$${(v / 1000).toFixed(0)}k`} tick={{ fontSize: 10, fill: '#666' }} width={52} />
              <Tooltip content={<ChartTooltip />} />
              <Legend wrapperStyle={{ fontSize: 10, paddingTop: 4 }} />
              {result.fold_boundaries.map((d, i) => (
                <ReferenceLine key={i} x={d} stroke="#2d2d4e" strokeDasharray="3 3" />
              ))}
              <Line type="monotone" dataKey="portfolio" name="Portfolio" stroke="#818cf8" strokeWidth={1.5} dot={false} connectNulls />
              <Line type="monotone" dataKey="benchmark" name="Benchmark" stroke="#4b5563" strokeWidth={1} dot={false} strokeDasharray="4 2" connectNulls />
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

        {/* Positions chart toggle */}
        {result.positions_chart.length > 0 && (
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
              <div>
                <div style={{ fontSize: 10, color: '#666', marginBottom: 8 }}>
                  Open positions by weight · positive = long · negative = short
                </div>
                <div style={{ height: 220 }}>
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
          </div>
        )}
      </div>
    </div>
  );
}
