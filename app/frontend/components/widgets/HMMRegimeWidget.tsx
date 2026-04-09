/**
 * HMMRegimeWidget
 *
 * Phase 1 — Config form: choose ticker, data start, train/test split
 * Phase 2 — Running:     animated progress bar with elapsed time
 * Phase 3 — Results:     regime badge, posterior chart, stats table
 */

import { useState, useMemo, useEffect, useRef } from 'react';
import {
  AreaChart, Area, ComposedChart, Line,
  XAxis, YAxis, Tooltip, Legend,
  ReferenceArea, ResponsiveContainer,
} from 'recharts';
import { api } from '../../lib/api';
import type { HMMRegimeResponse, HMMRegimePoint } from '../../types/api';

// ── Constants ──────────────────────────────────────────────────────────────

const REGIME_COLOR: Record<string, string> = {
  bull:     '#22c55e',
  sideways: '#94a3b8',
  bear:     '#ef4444',
};

// Separate chart-background color for sideways: slightly warmer/brighter so it's
// visible at low opacity against the near-black (#0f172a) chart background.
// At fillOpacity=0.22, #64748b on #0f172a produces a subtle but visible tint.
const REGIME_CHART_COLOR: Record<string, string> = {
  bull:     '#22c55e',
  sideways: '#64748b',   // slate-500 — more visible than slate-400 at low opacity
  bear:     '#ef4444',
};

const REGIME_FILL_OPACITY: Record<string, number> = {
  bull:     0.20,
  sideways: 0.28,   // higher opacity to compensate for the low-contrast gray
  bear:     0.20,
};

const REGIME_EMOJI: Record<string, string> = {
  bull:     '▲',
  sideways: '—',
  bear:     '▼',
};

// Rough expected seconds per year of test data (empirical)
const SECS_PER_TEST_YEAR = 6;

// Data start options
const START_OPTIONS = [
  { value: '2000-01-01', label: 'Since 2000 (max)' },
  { value: '2005-01-01', label: 'Since 2005' },
  { value: '2010-01-01', label: 'Since 2010' },
  { value: '2015-01-01', label: 'Since 2015' },
];

// Train window options (years from data start)
const TRAIN_YEARS_OPTIONS = [
  { value: 5,  label: '5 yr warm-up' },
  { value: 8,  label: '8 yr warm-up' },
  { value: 10, label: '10 yr warm-up' },
  { value: 12, label: '12 yr warm-up' },
];

interface HMMConfig {
  ticker:      string;
  dataStart:   string;
  trainYears:  number;
}

const DEFAULT_CONFIG: HMMConfig = {
  ticker:     'SPY',
  dataStart:  '2000-01-01',
  trainYears: 10,
};

// ── Helpers ────────────────────────────────────────────────────────────────

function addYears(isoDate: string, years: number): string {
  const d = new Date(isoDate);
  d.setFullYear(d.getFullYear() + years);
  return d.toISOString().slice(0, 10);
}

function yearsBetween(start: string, end: string): number {
  return (new Date(end).getTime() - new Date(start).getTime()) / (365.25 * 24 * 3600 * 1000);
}

function downsample<T>(arr: T[], maxPoints: number): T[] {
  if (arr.length <= maxPoints) return arr;
  const step = Math.ceil(arr.length / maxPoints);
  return arr.filter((_, i) => i % step === 0 || i === arr.length - 1);
}

/** Convert a regime series into contiguous spans for ReferenceArea rendering. */
interface RegimeSpan { x1: string; x2: string; regime: string }

function buildRegimeSpans(series: HMMRegimePoint[]): RegimeSpan[] {
  if (series.length === 0) return [];
  const spans: RegimeSpan[] = [];
  let spanStart = series[0].date;
  let spanRegime = series[0].regime;

  for (let i = 1; i < series.length; i++) {
    if (series[i].regime !== spanRegime) {
      spans.push({ x1: spanStart, x2: series[i - 1].date, regime: spanRegime });
      spanStart  = series[i].date;
      spanRegime = series[i].regime;
    }
  }
  // close the last span
  spans.push({ x1: spanStart, x2: series[series.length - 1].date, regime: spanRegime });
  return spans;
}

// ── Sub-components ─────────────────────────────────────────────────────────

function LabeledSelect({
  label, value, options, onChange,
}: {
  label: string;
  value: string | number;
  options: { value: string | number; label: string }[];
  onChange: (v: string) => void;
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, flex: 1, minWidth: 110 }}>
      <label style={{ fontSize: 10, color: '#888', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        {label}
      </label>
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

// ── Animated progress bar ──────────────────────────────────────────────────

function RunningScreen({ config, estimatedSecs }: { config: HMMConfig; estimatedSecs: number }) {
  const [elapsed, setElapsed] = useState(0);
  const startRef = useRef(Date.now());

  useEffect(() => {
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - startRef.current) / 1000)), 500);
    return () => clearInterval(id);
  }, []);

  // Progress based on elapsed vs estimate, capped at 95% until result arrives
  const rawPct  = estimatedSecs > 0 ? Math.min(elapsed / estimatedSecs, 0.95) : 0;
  const fillPct = Math.round(rawPct * 100);

  const trainEnd  = addYears(config.dataStart, config.trainYears);
  const testStart = addYears(trainEnd, 0);   // same date
  const today     = new Date().toISOString().slice(0, 10);
  const testYears = yearsBetween(testStart, today).toFixed(1);

  // Steps to display
  const steps = [
    { label: 'Downloading price data',       done: elapsed > 2 },
    { label: 'Building lookahead-safe features', done: elapsed > 4 },
    { label: 'Running walk-forward HMM',      done: false },
    { label: 'Computing regime statistics',   done: false },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, padding: '20px 8px' }}>

      {/* Header */}
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0', marginBottom: 4 }}>
          Running HMM Regime Detector
        </div>
        <div style={{ fontSize: 11, color: '#64748b' }}>
          {config.ticker} · {config.dataStart.slice(0, 4)}–today
          · {testYears}yr test window
        </div>
      </div>

      {/* Progress bar */}
      <div>
        <div style={{
          display: 'flex', justifyContent: 'space-between',
          fontSize: 10, color: '#64748b', marginBottom: 5,
        }}>
          <span>Progress (estimated)</span>
          <span>{fillPct}%</span>
        </div>
        <div style={{
          height: 10, background: '#1e293b', borderRadius: 6,
          border: '1px solid #334155', overflow: 'hidden',
        }}>
          <div style={{
            height: '100%', borderRadius: 6, background: '#3b82f6',
            width: `${fillPct}%`,
            transition: 'width 0.5s ease',
            boxShadow: '0 0 8px #3b82f688',
          }} />
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: '#475569', marginTop: 4 }}>
          <span>Elapsed: {elapsed}s</span>
          <span>Est: ~{estimatedSecs}s</span>
        </div>
      </div>

      {/* Step list */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
        {steps.map((s, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11 }}>
            <div style={{
              width: 16, height: 16, borderRadius: '50%', flexShrink: 0,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              background: s.done ? '#22c55e22' : '#1e293b',
              border: `1px solid ${s.done ? '#22c55e' : '#334155'}`,
              fontSize: 9,
            }}>
              {s.done ? '✓' : <SpinnerDot active={!s.done && steps.slice(0, i).every(x => x.done)} />}
            </div>
            <span style={{ color: s.done ? '#22c55e' : '#94a3b8' }}>{s.label}</span>
          </div>
        ))}
      </div>

      <div style={{ fontSize: 10, color: '#475569', textAlign: 'center', marginTop: 4 }}>
        First run downloads ~25yr of data and fits the model. Subsequent runs use cache.
      </div>
    </div>
  );
}

function SpinnerDot({ active }: { active: boolean }) {
  const [frame, setFrame] = useState(0);
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => setFrame(f => (f + 1) % 4), 300);
    return () => clearInterval(id);
  }, [active]);
  if (!active) return null;
  return <span style={{ color: '#3b82f6' }}>{'·'.repeat(frame + 1)}</span>;
}

// ── Props ──────────────────────────────────────────────────────────────────

interface Props { tabId: string }

// ── Main widget ────────────────────────────────────────────────────────────

export function HMMRegimeWidget({ tabId: _ }: Props) {
  const [phase, setPhase]   = useState<'config' | 'running' | 'results'>('config');
  const [config, setConfig] = useState<HMMConfig>(DEFAULT_CONFIG);
  const [tickerInput, setTickerInput] = useState(DEFAULT_CONFIG.ticker);

  const [result, setResult] = useState<HMMRegimeResponse | null>(null);
  const [error, setError]   = useState<string | null>(null);
  const [view, setView]     = useState<'price' | 'proba'>('price');

  const trainEnd  = addYears(config.dataStart, config.trainYears);
  const testStart = addYears(trainEnd, 0);
  const today     = new Date().toISOString().slice(0, 10);
  const testYears = yearsBetween(testStart, today);
  const estimatedSecs = Math.max(10, Math.round(testYears * SECS_PER_TEST_YEAR) + 10);

  const update = <K extends keyof HMMConfig>(key: K) => (v: HMMConfig[K]) =>
    setConfig(c => ({ ...c, [key]: v }));

  const handleRun = async () => {
    const ticker = tickerInput.trim().toUpperCase() || 'SPY';
    const cfg = { ...config, ticker };
    setConfig(cfg);
    setError(null);
    setPhase('running');
    try {
      const data = await api.hmmRegime({
        ticker,
        start:      cfg.dataStart,
        train_end:  addYears(cfg.dataStart, cfg.trainYears),
        test_start: addYears(cfg.dataStart, cfg.trainYears),
        refresh:    true,   // always fetch fresh when user explicitly runs
      });
      setResult(data);
      setPhase('results');
    } catch (e: any) {
      setError(e.message ?? 'Unknown error');
      setPhase('config');
    }
  };

  // Downsample for chart performance (line + area data)
  const chartData = useMemo(
    () => downsample(result?.series ?? [], 600).map((p: HMMRegimePoint) => ({
      date:       p.date,
      p_bull:     +(p.p_bull * 100).toFixed(1),
      p_sideways: +(p.p_sideways * 100).toFixed(1),
      p_bear:     +(p.p_bear * 100).toFixed(1),
      price:      p.spy_close ?? undefined,
    })),
    [result?.series],
  );

  // Regime spans — computed from FULL series so no span is missed at boundaries
  const regimeSpans = useMemo(
    () => buildRegimeSpans(result?.series ?? []),
    [result?.series],
  );

  // ── Phase: config ──────────────────────────────────────────────────────

  if (phase === 'config') {
    return (
      <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 18, height: '100%', overflowY: 'auto' }}>

        {/* Title */}
        <div>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0', marginBottom: 2 }}>
            HMM Regime Detector
          </div>
          <div style={{ fontSize: 11, color: '#64748b' }}>
            Expanding-window Gaussian HMM · 3 states · price + VIX · zero lookahead
          </div>
        </div>

        {/* Ticker */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <label style={{ fontSize: 10, color: '#888', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Ticker
          </label>
          <input
            value={tickerInput}
            onChange={e => setTickerInput(e.target.value.toUpperCase())}
            onKeyDown={e => e.key === 'Enter' && handleRun()}
            placeholder="SPY, QQQ, AAPL…"
            style={{
              background: '#111128', color: '#e0e0f0', border: '1px solid #2d2d4e',
              borderRadius: 4, padding: '6px 10px', fontSize: 13, width: '100%',
            }}
          />
        </div>

        {/* Data start + train window */}
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <LabeledSelect
            label="Data start"
            value={config.dataStart}
            options={START_OPTIONS}
            onChange={update('dataStart')}
          />
          <LabeledSelect
            label="Training warm-up"
            value={config.trainYears}
            options={TRAIN_YEARS_OPTIONS}
            onChange={v => update('trainYears')(Number(v))}
          />
        </div>

        {/* Summary preview */}
        <div style={{
          padding: '10px 14px', borderRadius: 6,
          background: '#0f172a', border: '1px solid #334155',
          fontSize: 11, color: '#94a3b8', display: 'flex', flexDirection: 'column', gap: 5,
        }}>
          {[
            ['Ticker',        tickerInput.trim().toUpperCase() || 'SPY'],
            ['Data range',    `${config.dataStart.slice(0, 4)} → today`],
            ['Training end',  trainEnd],
            ['Test start',    testStart],
            ['Test years',    `~${testYears.toFixed(1)} yr`],
            ['Est. runtime',  `~${estimatedSecs}s`],
          ].map(([k, v]) => (
            <div key={k} style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: '#64748b' }}>{k}</span>
              <span style={{ color: '#cbd5e1', fontFamily: 'monospace' }}>{v}</span>
            </div>
          ))}
        </div>

        {error && (
          <div style={{ fontSize: 11, color: '#ef4444', background: '#450a0a22', border: '1px solid #ef444433', borderRadius: 4, padding: '8px 12px' }}>
            {error}
          </div>
        )}

        {/* Run button */}
        <button
          onClick={handleRun}
          style={{
            padding: '10px 0', fontSize: 13, fontWeight: 600, borderRadius: 6,
            background: 'linear-gradient(135deg, #1d4ed8, #2563eb)',
            color: '#fff', border: 'none', cursor: 'pointer',
            boxShadow: '0 2px 12px #3b82f644',
            letterSpacing: '0.04em',
          }}
        >
          ▶ RUN HMM ANALYSIS
        </button>

        {result && (
          <button
            onClick={() => setPhase('results')}
            style={{
              padding: '7px 0', fontSize: 11, borderRadius: 6, marginTop: -8,
              background: '#1e293b', color: '#94a3b8', border: '1px solid #334155', cursor: 'pointer',
            }}
          >
            View previous results ({result.ticker})
          </button>
        )}
      </div>
    );
  }

  // ── Phase: running ─────────────────────────────────────────────────────

  if (phase === 'running') {
    return <RunningScreen config={config} estimatedSecs={estimatedSecs} />;
  }

  // ── Phase: results ─────────────────────────────────────────────────────

  if (!result) return null;
  const regime = result.current_regime;
  const color  = REGIME_COLOR[regime];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, height: '100%' }}>

      {/* ── Toolbar ──────────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{ fontSize: 11, color: '#64748b', fontFamily: 'monospace' }}>
          {result.ticker} · {result.test_start.slice(0, 10)} → today
        </span>
        <div style={{ flex: 1 }} />
        <button
          onClick={() => setPhase('config')}
          style={toolbarBtn}
        >⚙ Config</button>
        <button
          onClick={handleRun}
          style={toolbarBtn}
        >↺ Rerun</button>
      </div>

      {/* ── Regime badge ─────────────────────────────────────────────────── */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 14,
        padding: '9px 13px', borderRadius: 8,
        background: `${color}18`, border: `1px solid ${color}44`,
      }}>
        <div style={{ fontSize: 26, fontWeight: 700, color, lineHeight: 1, minWidth: 90 }}>
          {REGIME_EMOJI[regime]} {regime.toUpperCase()}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, flex: 1 }}>
          {(['bull', 'sideways', 'bear'] as const).map(r => {
            const p = r === 'bull' ? result.current_p_bull
                    : r === 'bear' ? result.current_p_bear
                    : result.current_p_side;
            return (
              <div key={r} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <div style={{ width: 7, height: 7, borderRadius: '50%', background: REGIME_COLOR[r], flexShrink: 0 }} />
                <span style={{ fontSize: 10, color: '#94a3b8', width: 54 }}>{r}</span>
                <div style={{ flex: 1, height: 5, background: '#1e293b', borderRadius: 3 }}>
                  <div style={{ height: '100%', borderRadius: 3, background: REGIME_COLOR[r], width: `${p * 100}%`, transition: 'width 0.4s' }} />
                </div>
                <span style={{ fontSize: 10, color: '#cbd5e1', width: 34, textAlign: 'right', fontFamily: 'monospace' }}>
                  {(p * 100).toFixed(1)}%
                </span>
              </div>
            );
          })}
        </div>
        <div style={{ fontSize: 10, color: '#475569', textAlign: 'right', flexShrink: 0 }}>
          <div>{result.n_observations.toLocaleString()} obs</div>
        </div>
      </div>

      {/* ── View toggle ──────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', gap: 4 }}>
        {([
          { id: 'price', label: `${result.ticker} + Regimes` },
          { id: 'proba', label: 'Posteriors' },
        ] as const).map(v => (
          <button key={v.id} onClick={() => setView(v.id)} style={{
            padding: '3px 10px', fontSize: 11, borderRadius: 4, cursor: 'pointer',
            background: view === v.id ? '#3b82f6' : '#1e293b',
            color: view === v.id ? '#fff' : '#94a3b8',
            border: '1px solid #334155',
          }}>
            {v.label}
          </button>
        ))}
      </div>

      {/* ── Chart ────────────────────────────────────────────────────────── */}
      <div style={{ flex: 1, minHeight: 150 }}>
        {view === 'price' ? (
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData} margin={{ top: 4, right: 4, left: -22, bottom: 0 }}>
              <XAxis
                dataKey="date"
                tick={{ fontSize: 9 }}
                tickLine={false}
                tickFormatter={d => d.slice(0, 7)}
                interval="preserveStartEnd"
              />
              <YAxis
                tick={{ fontSize: 9 }}
                domain={['auto', 'auto']}
                tickFormatter={v => `$${v}`}
              />
              <Tooltip
                content={({ active, payload, label }) => {
                  if (!active || !payload?.length) return null;
                  const pt = chartData.find(d => d.date === label);
                  return (
                    <div style={{
                      background: '#0f172a', border: '1px solid #334155',
                      borderRadius: 5, padding: '7px 11px', fontSize: 11,
                    }}>
                      <div style={{ color: '#64748b', marginBottom: 3 }}>{label}</div>
                      {payload[0]?.value != null && (
                        <div style={{ color: '#93c5fd' }}>
                          Price: <strong>${Number(payload[0].value).toFixed(2)}</strong>
                        </div>
                      )}
                      {pt && (
                        <div style={{ marginTop: 4, color: REGIME_COLOR[result.series.find(s => s.date === label)?.regime ?? 'sideways'] ?? '#94a3b8' }}>
                          Regime: <strong>
                            {result.series.find(s => s.date === label)?.regime ?? '—'}
                          </strong>
                        </div>
                      )}
                    </div>
                  );
                }}
              />

              {/* Colored background spans per regime — rendered before the line */}
              {regimeSpans.map((span, i) => (
                <ReferenceArea
                  key={i}
                  x1={span.x1}
                  x2={span.x2}
                  fill={REGIME_CHART_COLOR[span.regime]}
                  fillOpacity={REGIME_FILL_OPACITY[span.regime]}
                  strokeOpacity={0}
                  ifOverflow="hidden"
                />
              ))}

              <Line
                type="monotone"
                dataKey="price"
                dot={false}
                stroke="#93c5fd"
                strokeWidth={1.3}
                name={result.ticker}
                connectNulls
              />
            </ComposedChart>
          </ResponsiveContainer>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData} margin={{ top: 4, right: 4, left: -22, bottom: 0 }}>
              <XAxis dataKey="date" tick={{ fontSize: 9 }} tickLine={false}
                tickFormatter={d => d.slice(0, 7)} interval="preserveStartEnd" />
              <YAxis tick={{ fontSize: 9 }} domain={[0, 100]} tickFormatter={v => `${v}%`} />
              <Tooltip
                formatter={(v: number, name: string) => [`${v.toFixed(1)}%`, name.replace('p_', '')]}
                contentStyle={{ background: '#0f172a', border: '1px solid #334155', fontSize: 11 }}
              />
              <Legend iconSize={8} wrapperStyle={{ fontSize: 10 }} />
              <Area type="monotone" dataKey="p_bull"     stackId="1"
                stroke={REGIME_COLOR.bull}     fill={REGIME_COLOR.bull}     fillOpacity={0.55} name="Bull" />
              <Area type="monotone" dataKey="p_sideways" stackId="1"
                stroke={REGIME_COLOR.sideways} fill={REGIME_COLOR.sideways} fillOpacity={0.55} name="Sideways" />
              <Area type="monotone" dataKey="p_bear"     stackId="1"
                stroke={REGIME_COLOR.bear}     fill={REGIME_COLOR.bear}     fillOpacity={0.55} name="Bear" />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* ── Regime legend ─────────────────────────────────────────────────── */}
      {view === 'price' && (
        <div style={{ display: 'flex', gap: 12, justifyContent: 'center' }}>
          {(['bull', 'sideways', 'bear'] as const).map(r => (
            <div key={r} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 10, color: '#94a3b8' }}>
              <div style={{ width: 12, height: 12, borderRadius: 2, background: REGIME_COLOR[r], opacity: 0.7 }} />
              {r}
            </div>
          ))}
        </div>
      )}

      {/* ── Regime stats table ────────────────────────────────────────────── */}
      <table className="w-table" style={{ fontSize: 11 }}>
        <thead>
          <tr>
            <th style={{ textAlign: 'left' }}>REGIME</th>
            <th>FREQ</th>
            <th>AVG DUR</th>
            <th>ANN RET</th>
            <th>ANN VOL</th>
          </tr>
        </thead>
        <tbody>
          {(['bull', 'sideways', 'bear'] as const).map(r => {
            const s = result.regime_stats[r];
            const c = REGIME_COLOR[r];
            return (
              <tr key={r}>
                <td style={{ color: c, textAlign: 'left', fontWeight: 600 }}>
                  {REGIME_EMOJI[r]} {r}
                </td>
                <td>{s.frequency_pct.toFixed(1)}%</td>
                <td>{s.avg_duration_days.toFixed(0)}d</td>
                <td style={{ color: s.ann_return_pct >= 0 ? '#22c55e' : '#ef4444' }}>
                  {s.ann_return_pct >= 0 ? '+' : ''}{s.ann_return_pct.toFixed(1)}%
                </td>
                <td>{s.ann_vol_pct.toFixed(1)}%</td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <div style={{ fontSize: 10, color: '#334155', textAlign: 'center' }}>
        GaussianHMM diag · price returns + VIX · expanding window · refit every 21d
      </div>
    </div>
  );
}

// ── Shared style ───────────────────────────────────────────────────────────

const toolbarBtn: React.CSSProperties = {
  padding: '3px 9px', fontSize: 11, borderRadius: 4, cursor: 'pointer',
  background: '#1e293b', color: '#94a3b8', border: '1px solid #334155',
};
