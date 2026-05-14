import { useEffect, useRef, useState } from 'react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import { api, BASE_URL } from '../../lib/api';
import type { BacktestMetrics, DeepDiveStrategyResult, DeepDiveStreamEvent, TickerFundamentalsResponse, TradeMarker } from '../../types/api';

// eslint-disable-next-line @typescript-eslint/no-unused-vars
interface Props { tabId: string }

// ── constants ───────────────────────────────────────────────────────────────

const PERIOD_OPTIONS  = [{ v: 1, l: '1Y' }, { v: 3, l: '3Y' }, { v: 5, l: '5Y' }, { v: 10, l: '10Y' }];
const SORT_COLS = ['sharpe_ratio', 'cagr', 'total_return', 'max_drawdown', 'win_rate', 'total_trades'] as const;
type SortCol = typeof SORT_COLS[number];

const COL_LABELS: Record<SortCol, string> = {
  sharpe_ratio: 'Sharpe',
  cagr:         'CAGR',
  total_return: 'PnL %',
  max_drawdown: 'Max DD',
  win_rate:     'Win %',
  total_trades: 'Trades',
};

// ── helpers ─────────────────────────────────────────────────────────────────

function pct(v: number | null, dp = 1): string {
  return v != null ? `${(v * 100).toFixed(dp)}%` : '—';
}
function num(v: number | null, dp = 2): string {
  return v != null ? v.toFixed(dp) : '—';
}
function signColor(v: number | null, positive = true): string {
  if (v == null) return 'var(--col-body)';
  if (positive)  return v > 0 ? 'var(--col-emerald)' : 'var(--col-crimson)';
  return v < 0   ? 'var(--col-emerald)' : 'var(--col-crimson)';   // inverted for drawdown
}

const SIGNAL_COLOR: Record<string, string> = {
  STRONG_BUY:  'var(--col-emerald)',
  BUY:         'var(--col-cyan)',
  NEUTRAL:     'var(--col-body)',
  SELL:        'var(--col-amber)',
  STRONG_SELL: 'var(--col-crimson)',
};
const ZONE_COLOR: Record<string, string> = {
  SAFE:     'var(--col-emerald)',
  GREY:     'var(--col-amber)',
  DISTRESS: 'var(--col-crimson)',
};

// ── sub-components ──────────────────────────────────────────────────────────

function Badge({ label, color }: { label: string; color: string }) {
  return (
    <span style={{
      fontSize: 8, fontWeight: 700, letterSpacing: '0.5px', padding: '2px 6px',
      border: `1px solid ${color}`, color, whiteSpace: 'nowrap',
    }}>{label}</span>
  );
}

function FundamentalsBar({ data }: { data: TickerFundamentalsResponse }) {
  const spread = data.roic_wacc_spread;
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap',
      padding: '6px 12px', background: 'var(--col-elevated)',
      borderBottom: '1px solid var(--col-border)', flexShrink: 0,
    }}>
      <Badge label={data.signal.replace('_', ' ')} color={SIGNAL_COLOR[data.signal] ?? 'var(--col-body)'} />

      <div style={{ display: 'flex', gap: 12, alignItems: 'baseline' }}>
        <span style={{ fontSize: 8, color: 'var(--col-dim)' }}>ROIC−WACC</span>
        <span style={{
          fontSize: 12, fontWeight: 700,
          color: (spread ?? 0) > 0 ? 'var(--col-emerald)' : 'var(--col-crimson)',
          fontVariantNumeric: 'tabular-nums',
        }}>
          {spread != null ? `${(spread * 100) >= 0 ? '+' : ''}${(spread * 100).toFixed(1)}pp` : '—'}
        </span>
      </div>

      <div style={{ display: 'flex', gap: 6, alignItems: 'baseline' }}>
        <span style={{ fontSize: 8, color: 'var(--col-dim)' }}>ALTMAN Z</span>
        <span style={{ fontSize: 12, fontWeight: 700, color: ZONE_COLOR[data.altman_zone], fontVariantNumeric: 'tabular-nums' }}>
          {num(data.altman_z)}
        </span>
        <Badge label={data.altman_zone} color={ZONE_COLOR[data.altman_zone]} />
      </div>

      <div style={{ display: 'flex', gap: 6, alignItems: 'baseline' }}>
        <span style={{ fontSize: 8, color: 'var(--col-dim)' }}>FCF QUALITY</span>
        <span style={{
          fontSize: 12, fontWeight: 700,
          color: (data.fcf_quality ?? 0) >= 0.8 ? 'var(--col-emerald)' :
                 (data.fcf_quality ?? 0) >= 0.5 ? 'var(--col-amber)'   : 'var(--col-crimson)',
          fontVariantNumeric: 'tabular-nums',
        }}>
          {num(data.fcf_quality)}
        </span>
      </div>

      <div style={{ fontSize: 8, color: 'var(--col-dim)', marginLeft: 'auto' }}>
        α {data.alpha_score.toFixed(0)}/100
      </div>
    </div>
  );
}

// ── trade marker dots ────────────────────────────────────────────────────────

interface DotProps { cx?: number; cy?: number; value?: number }

function BuyDot({ cx, cy, value }: DotProps) {
  if (value == null || cx == null || cy == null) return null;
  const s = 5;
  return <polygon points={`${cx},${cy - s} ${cx - s},${cy + s} ${cx + s},${cy + s}`} fill="var(--col-emerald)" opacity={0.9} />;
}

function SellDot({ cx, cy, value }: DotProps) {
  if (value == null || cx == null || cy == null) return null;
  const s = 5;
  return <polygon points={`${cx},${cy + s} ${cx - s},${cy - s} ${cx + s},${cy - s}`} fill="var(--col-crimson)" opacity={0.9} />;
}

function StopDot({ cx, cy, value }: DotProps) {
  if (value == null || cx == null || cy == null) return null;
  const s = 5;
  return <polygon points={`${cx},${cy + s} ${cx - s},${cy - s} ${cx + s},${cy - s}`} fill="var(--col-crimson)" stroke="#1a0505" strokeWidth={1} opacity={0.9} />;
}

function EquityCurveChart({ result }: { result: DeepDiveStrategyResult }) {
  const { equity_curve, benchmark_curve, trade_markers } = result;
  const dates = Object.keys(equity_curve).sort();
  if (dates.length === 0) return <div style={{ fontSize: 9, color: 'var(--col-dim)', padding: 8 }}>No curve data</div>;

  const base = equity_curve[dates[0]] || 1_000_000;

  // Index markers by date for O(1) lookup
  const buys  = new Set<string>();
  const sells = new Set<string>();
  const stops = new Set<string>();
  for (const m of (trade_markers ?? []) as TradeMarker[]) {
    if (m.type === 'buy')       buys.add(m.date);
    else if (m.type === 'stop') stops.add(m.date);
    else                        sells.add(m.date);
  }

  const data = dates.map(d => {
    const stratVal = +(((equity_curve[d] / base) - 1) * 100).toFixed(2);
    return {
      date:        d,
      strategy:    stratVal,
      benchmark:   +(((benchmark_curve[d] != null ? benchmark_curve[d] : base) / base - 1) * 100).toFixed(2),
      buySignal:   buys.has(d)  ? stratVal : undefined,
      sellSignal:  sells.has(d) ? stratVal : undefined,
      stopSignal:  stops.has(d) ? stratVal : undefined,
    };
  });

  return (
    <div style={{ height: 130, padding: '6px 0 0 0' }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
          <XAxis dataKey="date" tick={{ fontSize: 7 }} tickLine={false} axisLine={false} interval="preserveStartEnd" tickFormatter={d => String(d).slice(0, 7)} />
          <YAxis tick={{ fontSize: 7 }} tickLine={false} axisLine={false} tickFormatter={v => `${v > 0 ? '+' : ''}${v.toFixed(0)}%`} width={38} />
          <Tooltip
            contentStyle={{ background: 'var(--col-elevated)', border: '1px solid var(--col-border)', fontSize: 9 }}
            formatter={(v, name) => {
              if (name === 'Strategy' || name === 'Benchmark')
                return [`${(v as number) > 0 ? '+' : ''}${(v as number).toFixed(2)}%`, name as string];
              return [null, null];
            }}
          />
          <ReferenceLine y={0} stroke="var(--col-border)" strokeDasharray="3 2" />
          <Line type="monotone" dataKey="strategy"  stroke="var(--col-cyan)" dot={false} strokeWidth={1.5} name="Strategy"  />
          <Line type="monotone" dataKey="benchmark" stroke="var(--col-dim)"  dot={false} strokeWidth={1}   name="Benchmark" strokeDasharray="4 2" />
          <Line type="monotone" dataKey="buySignal"  stroke="none" dot={<BuyDot />}  isAnimationActive={false} legendType="none" name="Buy"  />
          <Line type="monotone" dataKey="sellSignal" stroke="none" dot={<SellDot />} isAnimationActive={false} legendType="none" name="Sell" />
          <Line type="monotone" dataKey="stopSignal" stroke="none" dot={<StopDot />} isAnimationActive={false} legendType="none" name="Stop" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function SortHeader({
  col, current, asc, onSort,
}: { col: SortCol; current: SortCol; asc: boolean; onSort: (c: SortCol) => void }) {
  const active = col === current;
  return (
    <th
      onClick={() => onSort(col)}
      style={{
        cursor: 'pointer', textAlign: 'right', padding: '5px 8px',
        fontSize: 8, letterSpacing: '0.5px', fontWeight: 700,
        color: active ? 'var(--col-body)' : 'var(--col-slate)',
        userSelect: 'none', whiteSpace: 'nowrap',
      }}
    >
      {COL_LABELS[col]}{active ? (asc ? ' ▲' : ' ▼') : ''}
    </th>
  );
}

function metricVal(m: BacktestMetrics | null, col: SortCol): number {
  if (!m) return -Infinity;
  const v = m[col];
  if (col === 'max_drawdown') return -(v ?? -Infinity);   // smaller DD is better
  return v ?? -Infinity;
}

function sortResults(results: DeepDiveStrategyResult[], col: SortCol, asc: boolean): DeepDiveStrategyResult[] {
  return [...results].sort((a, b) => {
    const diff = metricVal(a.metrics, col) - metricVal(b.metrics, col);
    return asc ? diff : -diff;
  });
}

// ── main widget ─────────────────────────────────────────────────────────────

export function TickerDeepDiveWidget({ tabId: _ }: Props) {
  const [ticker,      setTicker]      = useState('AAPL');
  const [inputVal,    setInputVal]    = useState('AAPL');
  const [periodYears, setPeriodYears] = useState(5);
  const [isRunning,   setIsRunning]   = useState(false);
  const [progress,    setProgress]    = useState<{ completed: number; total: number; current: string | null }>({ completed: 0, total: 17, current: null });
  const [results,     setResults]     = useState<DeepDiveStrategyResult[]>([]);
  const [fundData,    setFundData]    = useState<TickerFundamentalsResponse | null>(null);
  const [fundLoading, setFundLoading] = useState(false);
  const [sortCol,     setSortCol]     = useState<SortCol>('sharpe_ratio');
  const [sortAsc,     setSortAsc]     = useState(false);
  const [expandedRow, setExpandedRow] = useState<string | null>(null);

  const esRef = useRef<EventSource | null>(null);

  // Fetch fundamentals whenever ticker commits
  useEffect(() => {
    if (!ticker) return;
    setFundData(null);
    setFundLoading(true);
    api.tickerFundamentals(ticker)
      .then(setFundData)
      .catch(() => setFundData(null))
      .finally(() => setFundLoading(false));
  }, [ticker]);

  function handleSort(col: SortCol) {
    if (col === sortCol) setSortAsc(a => !a);
    else { setSortCol(col); setSortAsc(false); }
  }

  function commitTicker() {
    const v = inputVal.trim().toUpperCase();
    if (v && v !== ticker) {
      setTicker(v);
      setResults([]);
      setProgress({ completed: 0, total: 17, current: null });
    }
  }

  async function handleRun() {
    if (isRunning || !ticker) return;
    esRef.current?.close();
    setResults([]);
    setProgress({ completed: 0, total: 17, current: null });
    setExpandedRow(null);
    setIsRunning(true);

    let jobId: string;
    try {
      const r = await api.startDeepDive(ticker, periodYears);
      jobId = r.job_id;
      setProgress(p => ({ ...p, total: r.total }));
    } catch {
      setIsRunning(false);
      return;
    }

    const es = new EventSource(`${BASE_URL}/api/deep-dive/stream/${jobId}`);
    esRef.current = es;

    es.onmessage = (e) => {
      const ev: DeepDiveStreamEvent = JSON.parse(e.data);
      if (ev.type === 'result' && ev.strategy) {
        setResults(prev => [...prev, {
          strategy:        ev.strategy!,
          metrics:         ev.metrics ?? null,
          equity_curve:    ev.equity_curve ?? {},
          benchmark_curve: ev.benchmark_curve ?? {},
          trade_markers:   ev.trade_markers ?? [],
          error:           ev.error,
        }]);
        setProgress({ completed: ev.completed, total: ev.total, current: ev.current_strategy ?? null });
      } else if (ev.type === 'progress') {
        setProgress({ completed: ev.completed, total: ev.total, current: ev.current_strategy ?? null });
        if (ev.status === 'completed' || ev.status === 'failed') {
          setIsRunning(false);
          es.close();
        }
      }
    };

    es.onerror = () => {
      setIsRunning(false);
      es.close();
    };
  }

  // Cleanup on unmount
  useEffect(() => () => { esRef.current?.close(); }, []);

  const sorted = sortResults(results, sortCol, sortAsc);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>

      {/* ── toolbar ── */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, padding: '5px 12px',
        background: 'var(--col-elevated)', borderBottom: '1px solid var(--col-border)', flexShrink: 0,
      }}>
        <input
          value={inputVal}
          onChange={e => setInputVal(e.target.value.toUpperCase())}
          onBlur={commitTicker}
          onKeyDown={e => { if (e.key === 'Enter') { commitTicker(); (e.target as HTMLInputElement).blur(); } }}
          placeholder="TICKER"
          style={{
            background: 'transparent', border: '1px solid var(--col-border)',
            color: 'var(--col-body)', fontSize: 11, fontWeight: 700,
            padding: '2px 6px', width: 80, letterSpacing: '0.5px',
          }}
        />

        <div style={{ display: 'flex', gap: 2 }}>
          {PERIOD_OPTIONS.map(o => (
            <button
              key={o.v}
              onClick={() => setPeriodYears(o.v)}
              style={{
                background:   periodYears === o.v ? 'var(--col-accent-dim)' : 'transparent',
                border:       `1px solid ${periodYears === o.v ? 'var(--col-accent)' : 'var(--col-border)'}`,
                color:        periodYears === o.v ? 'var(--col-accent)' : 'var(--col-dim)',
                fontSize: 8, fontWeight: 700, letterSpacing: '0.5px',
                padding: '2px 6px', cursor: 'pointer',
              }}
            >{o.l}</button>
          ))}
        </div>

        <button
          onClick={handleRun}
          disabled={isRunning || !ticker}
          style={{
            background:   isRunning ? 'transparent' : 'var(--col-accent-dim)',
            border:       `1px solid ${isRunning ? 'var(--col-border)' : 'var(--col-accent)'}`,
            color:        isRunning ? 'var(--col-dim)' : 'var(--col-accent)',
            fontSize: 8, fontWeight: 700, letterSpacing: '1px',
            padding: '3px 10px', cursor: isRunning ? 'default' : 'pointer',
          }}
        >{isRunning ? 'RUNNING…' : 'RUN'}</button>
      </div>

      {/* ── fundamentals bar ── */}
      {fundLoading && (
        <div style={{ padding: '5px 12px', fontSize: 8, color: 'var(--col-dim)', background: 'var(--col-elevated)', borderBottom: '1px solid var(--col-border)', flexShrink: 0 }}>
          Loading fundamentals for {ticker}…
        </div>
      )}
      {fundData && !fundLoading && <FundamentalsBar data={fundData} />}

      {/* ── progress bar ── */}
      {isRunning && (
        <div style={{ flexShrink: 0, padding: '5px 12px', background: 'var(--col-surface)', borderBottom: '1px solid var(--col-border)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
            <span style={{ fontSize: 8, color: 'var(--col-dim)' }}>{progress.current ?? 'Initialising…'}</span>
            <span style={{ fontSize: 8, color: 'var(--col-slate)' }}>{progress.completed}/{progress.total}</span>
          </div>
          <div style={{ height: 2, background: 'var(--col-border)', borderRadius: 1 }}>
            <div style={{
              height: '100%', borderRadius: 1, background: 'var(--col-accent)',
              width: `${progress.total > 0 ? (progress.completed / progress.total) * 100 : 0}%`,
              transition: 'width 0.3s ease',
            }} />
          </div>
        </div>
      )}

      {/* ── strategy table ── */}
      <div style={{ flex: 1, overflow: 'auto' }}>
        {results.length === 0 && !isRunning && (
          <div style={{ padding: '24px 12px', textAlign: 'center', fontSize: 9, color: 'var(--col-dim)' }}>
            Enter a ticker and press RUN to compare all 17 strategies.
          </div>
        )}
        {results.length > 0 && (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--col-border)' }}>
                <th style={{ textAlign: 'left', padding: '5px 12px', fontSize: 8, color: 'var(--col-slate)', letterSpacing: '0.5px', fontWeight: 700 }}>STRATEGY</th>
                {SORT_COLS.map(c => (
                  <SortHeader key={c} col={c} current={sortCol} asc={sortAsc} onSort={handleSort} />
                ))}
              </tr>
            </thead>
            <tbody>
              {sorted.map((r, idx) => {
                const m = r.metrics;
                const expanded = expandedRow === r.strategy;
                const rowBg = idx % 2 === 0 ? 'transparent' : 'var(--col-row-alt)';
                return (
                  <>
                    <tr
                      key={r.strategy}
                      onClick={() => setExpandedRow(expanded ? null : r.strategy)}
                      style={{ background: expanded ? 'var(--col-elevated)' : rowBg, cursor: 'pointer' }}
                    >
                      <td style={{ padding: '5px 12px', fontSize: 9, color: 'var(--col-body)', fontWeight: 600 }}>
                        {r.strategy.replace('Strategy', '')}
                        {r.error && <span style={{ fontSize: 7, color: 'var(--col-crimson)', marginLeft: 4 }}>ERR</span>}
                      </td>
                      <td style={{ padding: '5px 8px', textAlign: 'right', fontSize: 9, fontVariantNumeric: 'tabular-nums', color: signColor(m?.sharpe_ratio ?? null) }}>
                        {num(m?.sharpe_ratio ?? null)}
                      </td>
                      <td style={{ padding: '5px 8px', textAlign: 'right', fontSize: 9, fontVariantNumeric: 'tabular-nums', color: signColor(m?.cagr ?? null) }}>
                        {pct(m?.cagr ?? null)}
                      </td>
                      <td style={{ padding: '5px 8px', textAlign: 'right', fontSize: 9, fontVariantNumeric: 'tabular-nums', color: signColor(m?.total_return ?? null) }}>
                        {m?.total_return != null ? `${m.total_return >= 0 ? '+' : ''}${(m.total_return * 100).toFixed(1)}%` : '—'}
                      </td>
                      <td style={{ padding: '5px 8px', textAlign: 'right', fontSize: 9, fontVariantNumeric: 'tabular-nums', color: signColor(m?.max_drawdown ?? null, false) }}>
                        {pct(m?.max_drawdown ?? null)}
                      </td>
                      <td style={{ padding: '5px 8px', textAlign: 'right', fontSize: 9, fontVariantNumeric: 'tabular-nums', color: 'var(--col-body)' }}>
                        {pct(m?.win_rate ?? null)}
                      </td>
                      <td style={{ padding: '5px 8px', textAlign: 'right', fontSize: 9, fontVariantNumeric: 'tabular-nums', color: 'var(--col-dim)' }}>
                        {m?.total_trades ?? '—'}
                      </td>
                    </tr>
                    {expanded && (
                      <tr key={`${r.strategy}-expand`} style={{ background: 'var(--col-elevated)' }}>
                        <td colSpan={7} style={{ padding: '0 12px 8px 12px', borderBottom: '1px solid var(--col-border)' }}>
                          {r.error
                            ? <div style={{ fontSize: 9, color: 'var(--col-crimson)', padding: '8px 0' }}>Error: {r.error}</div>
                            : <EquityCurveChart result={r} />
                          }
                        </td>
                      </tr>
                    )}
                  </>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
