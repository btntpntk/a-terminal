/**
 * HurstWidget — Rolling Hurst Exponent (R/S Analysis) Market Regime Indicator
 *
 * Regime thresholds:
 *   H < 0.45  → SIDEWAYS  (mean-reverting / volatility compression)
 *   H ∈ [0.45, 0.55] → RANDOM  (no persistent structure)
 *   H > 0.55  → TRENDING (persistent / momentum)
 *
 * Visual contract:
 *   - Widget background shifts to muted grey when SIDEWAYS
 *   - document.body gets data-hurst-regime="sideways|random|trending"
 *     so a global CSS rule can dim the dashboard background
 */

import { useEffect, useRef, useState } from 'react';
import {
  LineChart, Line, XAxis, YAxis,
  ReferenceLine, Tooltip, ResponsiveContainer,
} from 'recharts';
import { useHurst, usePriceHistory } from '../../hooks/useQueries';
import { useActiveTab } from '../../hooks/useActiveTab';

const PERIODS_TO_YFINANCE: Record<number, string> = {
  126: '6mo',
  252: '1y',
  504: '2y',
};

// ── Regime config ─────────────────────────────────────────────────────────────

const REGIME_META = {
  sideways: {
    label:       'SIDEWAYS',
    description: 'Mean-reverting · Volatility compression',
    color:       '#94a3b8',         // slate-400
    bgColor:     'rgba(30,41,59,0.85)',   // dark blue-grey
    border:      '1px solid #334155',
    glow:        'none',
  },
  random: {
    label:       'RANDOM',
    description: 'No persistent structure · Random walk',
    color:       '#60a5fa',         // blue-400
    bgColor:     'rgba(15,23,42,0.85)',
    border:      '1px solid #1d4ed844',
    glow:        '0 0 12px #3b82f622',
  },
  trending: {
    label:       'TRENDING',
    description: 'Persistent momentum · Directional bias',
    color:       '#4ade80',         // green-400
    bgColor:     'rgba(15,23,42,0.85)',
    border:      '1px solid #16a34a44',
    glow:        '0 0 14px #22c55e22',
  },
} as const;

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtH(h: number | null | undefined): string {
  if (h == null || isNaN(h)) return '—';
  return h.toFixed(3);
}

// ── Sub-components ────────────────────────────────────────────────────────────

function HGauge({ h }: { h: number }) {
  const pct   = Math.max(0, Math.min(1, h));
  const left  = `${pct * 100}%`;
  return (
    <div style={{ position: 'relative', marginTop: 6 }}>
      {/* Track */}
      <div style={{
        height: 6, borderRadius: 3,
        background: 'linear-gradient(to right, #60a5fa 0%, #94a3b8 30%, #94a3b8 70%, #4ade80 100%)',
        opacity: 0.4,
      }} />
      {/* Zone marks */}
      {[0.45, 0.55].map(mark => (
        <div key={mark} style={{
          position: 'absolute', top: -2, bottom: -2,
          left: `${mark * 100}%`, width: 1,
          background: '#475569',
        }} />
      ))}
      {/* Needle */}
      <div style={{
        position: 'absolute', top: -3, left,
        transform: 'translateX(-50%)',
        width: 12, height: 12, borderRadius: '50%',
        background: h < 0.45 ? REGIME_META.sideways.color
                  : h > 0.55 ? REGIME_META.trending.color
                  : REGIME_META.random.color,
        border: '2px solid #0f172a',
        boxShadow: '0 0 6px currentColor',
      }} />
      {/* Zone labels */}
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8, fontSize: 9, color: '#475569' }}>
        <span>MR</span>
        <span style={{ marginLeft: '30%' }}>RW</span>
        <span>TR</span>
      </div>
    </div>
  );
}

function SparkTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  const hEntry    = payload.find((p: any) => p.dataKey === 'h');
  const priceEntry = payload.find((p: any) => p.dataKey === 'price');
  return (
    <div style={{
      background: '#0f172a', border: '1px solid #334155',
      borderRadius: 5, padding: '6px 10px', fontSize: 11,
    }}>
      <div style={{ color: '#64748b', marginBottom: 4 }}>{label}</div>
      {hEntry     && <div style={{ color: '#e2e8f0' }}>H = <strong>{fmtH(hEntry.value)}</strong></div>}
      {priceEntry && priceEntry.value != null && (
        <div style={{ color: '#f59e0b', marginTop: 2 }}>
          Price = <strong>{(priceEntry.value as number).toFixed(2)}</strong>
        </div>
      )}
    </div>
  );
}

// ── Config form ───────────────────────────────────────────────────────────────

interface ConfigState {
  ticker:  string;
  window:  number;
  periods: number;
}

const WINDOW_OPTIONS  = [50, 100, 150, 200];
const PERIODS_OPTIONS = [126, 252, 504];

// ── Main widget ───────────────────────────────────────────────────────────────

interface Props { tabId: string }

export function HurstWidget({ tabId: _ }: Props) {
  const tab            = useActiveTab();
  const [cfg, setCfg]  = useState<ConfigState>({
    ticker:  tab.activeTicker,
    window:  100,
    periods: 252,
  });
  const [tickerInput, setTickerInput] = useState(cfg.ticker);
  const prevRegimeRef = useRef<string | null>(null);

  const { data, isFetching, error, refetch } = useHurst(cfg.ticker, cfg.window, cfg.periods);
  const pricePeriod = PERIODS_TO_YFINANCE[cfg.periods] ?? '1y';
  const { data: priceData } = usePriceHistory(cfg.ticker, pricePeriod);

  const regime = data?.regime ?? 'random';
  const meta   = REGIME_META[regime];

  // ── Global background signal via data attribute ───────────────────────────
  // CSS rule in index.css responds to body[data-hurst-regime="sideways"]
  useEffect(() => {
    if (data?.regime && data.regime !== prevRegimeRef.current) {
      document.body.setAttribute('data-hurst-regime', data.regime);
      prevRegimeRef.current = data.regime;
    }
    return () => {
      // Clean up only if this widget unmounts AND it was the one that set it
      if (prevRegimeRef.current !== null) {
        document.body.removeAttribute('data-hurst-regime');
      }
    };
  }, [data?.regime]);

  // Apply ticker from tab when the tab activeTicker changes
  useEffect(() => {
    setCfg(c => ({ ...c, ticker: tab.activeTicker }));
    setTickerInput(tab.activeTicker);
  }, [tab.activeTicker]);

  const commitTicker = () => {
    const t = tickerInput.trim().toUpperCase();
    if (t) setCfg(c => ({ ...c, ticker: t }));
  };

  // ── Sparkline data — merge H series with close prices by date ────────────
  const priceMap = new Map(
    (priceData?.bars ?? []).map(b => [b.time.slice(0, 10), b.close])
  );
  const sparkData = (data?.series ?? []).map(p => ({
    date:  p.date,
    h:     p.h,
    price: priceMap.get(p.date.slice(0, 10)) ?? null,
  }));

  // ── Widget background: shifts when SIDEWAYS ───────────────────────────────
  const widgetBg = regime === 'sideways'
    ? { background: 'rgba(30,41,59,0.92)', border: '1px solid #334155' }
    : { background: 'rgba(15,23,42,0.60)', border: '1px solid #1e293b' };

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', gap: 12,
      height: '100%', padding: 4,
      transition: 'background 0.5s ease, border-color 0.5s ease',
      borderRadius: 8,
      ...widgetBg,
    }}>

      {/* ── Config row ─────────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <input
          value={tickerInput}
          onChange={e => setTickerInput(e.target.value.toUpperCase())}
          onBlur={commitTicker}
          onKeyDown={e => e.key === 'Enter' && commitTicker()}
          placeholder="Ticker…"
          style={{
            background: '#111828', color: '#e2e8f0',
            border: '1px solid #2d2d4e', borderRadius: 4,
            padding: '4px 8px', fontSize: 12, width: 90,
          }}
        />

        <label style={{ fontSize: 10, color: '#64748b' }}>Window</label>
        <select
          value={cfg.window}
          onChange={e => setCfg(c => ({ ...c, window: Number(e.target.value) }))}
          style={{ background: '#111828', color: '#e2e8f0', border: '1px solid #2d2d4e', borderRadius: 4, padding: '4px 6px', fontSize: 11 }}
        >
          {WINDOW_OPTIONS.map(w => <option key={w} value={w}>{w}d</option>)}
        </select>

        <label style={{ fontSize: 10, color: '#64748b' }}>History</label>
        <select
          value={cfg.periods}
          onChange={e => setCfg(c => ({ ...c, periods: Number(e.target.value) }))}
          style={{ background: '#111828', color: '#e2e8f0', border: '1px solid #2d2d4e', borderRadius: 4, padding: '4px 6px', fontSize: 11 }}
        >
          {PERIODS_OPTIONS.map(p => <option key={p} value={p}>{p / 252}yr</option>)}
        </select>

        <div style={{ flex: 1 }} />

        <button
          onClick={() => refetch()}
          disabled={isFetching}
          style={{
            padding: '3px 9px', fontSize: 10, borderRadius: 4, cursor: 'pointer',
            background: '#1e293b', color: isFetching ? '#475569' : '#94a3b8',
            border: '1px solid #334155',
          }}
        >
          {isFetching ? '⟳' : '↺'}
        </button>
      </div>

      {error && (
        <div style={{ fontSize: 11, color: '#ef4444', background: '#450a0a22', border: '1px solid #ef444433', borderRadius: 4, padding: '6px 10px' }}>
          {String(error)}
        </div>
      )}

      {/* ── Regime badge ───────────────────────────────────────────────────── */}
      <div style={{
        padding: '12px 16px', borderRadius: 8,
        background: meta.bgColor,
        border: meta.border,
        boxShadow: meta.glow,
        transition: 'all 0.4s ease',
      }}>
        {/* H value */}
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 4 }}>
          <span style={{ fontSize: 11, color: '#64748b', fontFamily: 'monospace' }}>H =</span>
          <span style={{
            fontSize: 32, fontWeight: 700, letterSpacing: '-0.02em',
            color: meta.color, fontFamily: 'monospace',
            textShadow: regime !== 'random' ? `0 0 20px ${meta.color}66` : 'none',
            transition: 'color 0.4s ease',
          }}>
            {fmtH(data?.current_h)}
          </span>

          {/* Regime label */}
          <span style={{
            fontSize: 14, fontWeight: 700, letterSpacing: '0.08em',
            color: meta.color, opacity: 0.9,
          }}>
            {meta.label}
          </span>
        </div>

        {/* Description */}
        <div style={{ fontSize: 10, color: '#64748b', marginBottom: 10 }}>
          {meta.description}
        </div>

        {/* Gauge */}
        {data?.current_h != null && <HGauge h={data.current_h} />}

        {/* Zone legend */}
        <div style={{ display: 'flex', gap: 14, marginTop: 12, fontSize: 10 }}>
          {(['sideways', 'random', 'trending'] as const).map(r => (
            <div key={r} style={{ display: 'flex', alignItems: 'center', gap: 4, opacity: r === regime ? 1 : 0.35 }}>
              <div style={{ width: 6, height: 6, borderRadius: '50%', background: REGIME_META[r].color }} />
              <span style={{ color: REGIME_META[r].color }}>{REGIME_META[r].label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* ── Ticker + window info ──────────────────────────────────────────── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: '#475569' }}>
        <span style={{ fontFamily: 'monospace' }}>{data?.ticker ?? cfg.ticker} · R/S({cfg.window}d window)</span>
        {data?.timestamp && (
          <span>{new Date(data.timestamp).toLocaleTimeString()}</span>
        )}
      </div>

      {/* ── Rolling H sparkline ───────────────────────────────────────────── */}
      <div style={{ flex: 1, minHeight: 100 }}>
        {sparkData.length > 0 ? (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={sparkData} margin={{ top: 4, right: 44, left: -28, bottom: 0 }}>
              <XAxis
                dataKey="date"
                tick={{ fontSize: 9, fill: '#475569' }}
                tickLine={false}
                tickFormatter={d => d.slice(0, 7)}
                interval="preserveStartEnd"
              />
              {/* Left axis — Hurst H (0–1) */}
              <YAxis
                yAxisId="left"
                domain={[0, 1]}
                tick={{ fontSize: 9, fill: '#475569' }}
                tickCount={5}
              />
              {/* Right axis — price (auto-scaled) */}
              <YAxis
                yAxisId="right"
                orientation="right"
                domain={['auto', 'auto']}
                tick={{ fontSize: 8, fill: '#78716c' }}
                tickCount={4}
                tickFormatter={v => v >= 1000 ? `${(v / 1000).toFixed(1)}k` : String(Math.round(v))}
                width={40}
              />
              <Tooltip content={<SparkTooltip />} />

              {/* Zone bands */}
              <ReferenceLine yAxisId="left" y={0.45} stroke="#475569" strokeDasharray="3 3" strokeWidth={1} />
              <ReferenceLine yAxisId="left" y={0.55} stroke="#475569" strokeDasharray="3 3" strokeWidth={1} />
              <ReferenceLine yAxisId="left" y={0.50} stroke="#1e293b" strokeWidth={1} />

              {/* Price line */}
              <Line
                yAxisId="right"
                type="monotone"
                dataKey="price"
                dot={false}
                stroke="#f59e0b"
                strokeWidth={1}
                strokeOpacity={0.55}
                connectNulls
                isAnimationActive={false}
              />
              {/* H line — colour tracks current regime */}
              <Line
                yAxisId="left"
                type="monotone"
                dataKey="h"
                dot={false}
                stroke={meta.color}
                strokeWidth={1.5}
                connectNulls
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', fontSize: 11, color: '#334155' }}>
            {isFetching ? 'Computing R/S…' : 'No data'}
          </div>
        )}
      </div>

      {/* ── Zone reference ────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', justifyContent: 'space-around', fontSize: 9, color: '#334155', borderTop: '1px solid #1e293b', paddingTop: 5 }}>
        <span>H &lt; 0.45 = Sideways</span>
        <span>0.45–0.55 = Random</span>
        <span>H &gt; 0.55 = Trending</span>
      </div>
    </div>
  );
}
