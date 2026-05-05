import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useCorrelationMatrix } from '../../hooks/useQueries';
import type { DriverCorrelation, CorrSignal } from '../../types/api';

// eslint-disable-next-line @typescript-eslint/no-unused-vars
interface Props { tabId: string }

const DRIVER_META: Record<string, { label: string; desc: string }> = {
  US10Y:  { label: 'US 10Y',  desc: 'Treasury yield — capital flow proxy'      },
  DXY:    { label: 'DXY',     desc: 'Dollar index — EM risk-off / risk-on'     },
  BRENT:  { label: 'BRENT',   desc: 'Brent crude — energy sector (PTT/PTTEP)'  },
  USDTHB: { label: 'USD/THB', desc: 'FX rate — export & banking sector impact' },
};

const SIGNAL_META: Record<CorrSignal, { label: string; color: string }> = {
  STRONG_POS:        { label: 'STRONG ↑',  color: 'var(--col-emerald)' },
  MILD_POS:          { label: 'MILD ↑',    color: 'var(--col-cyan)'    },
  DECOUPLED:         { label: 'DECOUPLED', color: 'var(--col-dim)'     },
  MILD_NEG:          { label: 'MILD ↓',    color: 'var(--col-amber)'   },
  STRONG_NEG:        { label: 'STRONG ↓',  color: 'var(--col-crimson)' },
  DATA_MISSING:      { label: 'NO DATA',   color: 'var(--col-dim)'     },
  INSUFFICIENT_DATA: { label: 'LOW DATA',  color: 'var(--col-dim)'     },
};

function corrColor(v: number | null): string {
  if (v == null)  return 'var(--col-dim)';
  if (v >  0.50)  return 'var(--col-emerald)';
  if (v >  0.20)  return 'var(--col-cyan)';
  if (v < -0.50)  return 'var(--col-crimson)';
  if (v < -0.20)  return 'var(--col-amber)';
  return 'var(--col-body)';
}

function CorrBar({ value }: { value: number | null }) {
  if (value == null) return <span style={{ color: 'var(--col-dim)', fontSize: 10 }}>—</span>;
  const halfPct = Math.abs(value) * 100;   // 0–100 within each half
  const color   = corrColor(value);
  return (
    <div style={{ display: 'flex', alignItems: 'center', width: 100, height: 8, gap: 0 }}>
      <div style={{ flex: 1, height: '100%', background: 'var(--col-border)', position: 'relative', overflow: 'hidden' }}>
        {value < 0 && (
          <div style={{ position: 'absolute', right: 0, top: 0, bottom: 0, width: `${halfPct}%`, background: color }} />
        )}
      </div>
      <div style={{ width: 1, height: 12, background: 'var(--col-slate)', flexShrink: 0 }} />
      <div style={{ flex: 1, height: '100%', background: 'var(--col-border)', position: 'relative', overflow: 'hidden' }}>
        {value > 0 && (
          <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: `${halfPct}%`, background: color }} />
        )}
      </div>
    </div>
  );
}

function MiniCorrLine({ series }: { series: Array<{ corr: number }> }) {
  if (series.length < 2) return null;
  const vals  = series.map(s => s.corr);
  const W = 80, H = 24;
  const pts = vals.map((v, i) => {
    const x = (i / (vals.length - 1)) * W;
    const y = H / 2 - (v * H) / 2;          // zero-centred, clamp implied by SVG viewBox
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  return (
    <svg width={W} height={H} style={{ display: 'block', overflow: 'visible', flexShrink: 0 }}>
      <line x1="0" y1={H / 2} x2={W} y2={H / 2} stroke="var(--col-border)" strokeWidth="0.5" strokeDasharray="2,2" />
      <polyline points={pts} fill="none" stroke="var(--col-cyan)" strokeWidth="1.2" opacity="0.8" />
    </svg>
  );
}

function DriverRow({ name, driver, expanded, onToggle }: {
  name:     string;
  driver:   DriverCorrelation;
  expanded: boolean;
  onToggle: () => void;
}) {
  const meta   = DRIVER_META[name]          ?? { label: name, desc: '' };
  const signal = SIGNAL_META[driver.signal] ?? { label: driver.signal, color: 'var(--col-dim)' };
  const shift  =
    driver.corr_30d != null && driver.corr_60d != null
      ? driver.corr_30d - driver.corr_60d
      : null;

  return (
    <>
      <tr onClick={onToggle} style={{ cursor: 'pointer', borderBottom: '1px solid #141414' }}>
        <td style={{ padding: '6px 8px', textAlign: 'left' }}>
          <div style={{ fontWeight: 600, fontSize: 10, color: 'var(--col-body)' }}>{meta.label}</div>
          <div style={{ fontSize: 9, color: 'var(--col-dim)', marginTop: 1 }}>{driver.ticker}</div>
        </td>
        <td style={{ padding: '6px 8px', textAlign: 'right' }}>
          <span style={{ fontSize: 11, fontWeight: 600, color: corrColor(driver.current_corr) }}>
            {driver.current_corr != null ? driver.current_corr.toFixed(2) : '—'}
          </span>
        </td>
        <td style={{ padding: '6px 8px', textAlign: 'right', color: 'var(--col-dim)', fontSize: 10 }}>
          {driver.corr_60d != null ? driver.corr_60d.toFixed(2) : '—'}
        </td>
        <td style={{ padding: '6px 8px' }}>
          <CorrBar value={driver.current_corr} />
        </td>
        <td style={{ padding: '6px 8px', textAlign: 'right' }}>
          <span style={{ fontSize: 9, fontWeight: 700, color: signal.color, letterSpacing: '0.3px' }}>
            {signal.label}
          </span>
        </td>
        <td style={{ padding: '6px 4px', textAlign: 'center', color: 'var(--col-dim)', fontSize: 10 }}>
          {expanded ? '▲' : '▼'}
        </td>
      </tr>

      {expanded && (
        <tr style={{ background: 'var(--col-elevated)', borderBottom: '1px solid var(--col-border)' }}>
          <td colSpan={6} style={{ padding: '8px 12px' }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 16 }}>
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}>
                <div style={{ fontSize: 9, color: 'var(--col-slate)', fontStyle: 'italic' }}>{meta.desc}</div>
                <div style={{ display: 'flex', gap: 14 }}>
                  {[
                    { lbl: '30D',   val: driver.corr_30d },
                    { lbl: '60D',   val: driver.corr_60d },
                  ].map(({ lbl, val }) => (
                    <div key={lbl}>
                      <div style={{ fontSize: 9, color: 'var(--col-dim)' }}>{lbl} CORR</div>
                      <div style={{ fontSize: 13, fontWeight: 600, color: corrColor(val) }}>
                        {val != null ? val.toFixed(3) : '—'}
                      </div>
                    </div>
                  ))}
                  <div>
                    <div style={{ fontSize: 9, color: 'var(--col-dim)' }}>Δ 30–60D</div>
                    <div style={{
                      fontSize: 13, fontWeight: 600,
                      color: shift != null && Math.abs(shift) > 0.2 ? 'var(--col-amber)' : 'var(--col-dim)',
                    }}>
                      {shift != null ? (shift >= 0 ? '+' : '') + shift.toFixed(2) : '—'}
                    </div>
                  </div>
                </div>
              </div>
              <MiniCorrLine series={driver.series} />
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

const BENCHMARKS = ['^SET.BK', '^GSPC', 'EEM'] as const;
type Benchmark = typeof BENCHMARKS[number];
const BM_LABELS: Record<Benchmark, string> = { '^SET.BK': 'SET', '^GSPC': 'S&P', 'EEM': 'EEM' };

export function GlobalMacroCorrelationWidget({ tabId: _ }: Props) {
  const [benchmark, setBenchmark] = useState<Benchmark>('^SET.BK');
  const [expanded, setExpanded]   = useState<string | null>(null);
  const { data, isLoading, error } = useCorrelationMatrix(benchmark, 30);
  const qc = useQueryClient();

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* Toolbar */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, padding: '5px 10px',
        background: 'var(--col-elevated)', borderBottom: '1px solid var(--col-border)', flexShrink: 0,
      }}>
        <span style={{ fontSize: 9, color: 'var(--col-slate)', letterSpacing: '1px', flex: 1 }}>
          30D ROLLING CORR vs
        </span>
        <div style={{ display: 'flex', gap: 4 }}>
          {BENCHMARKS.map(b => (
            <button key={b} onClick={() => setBenchmark(b)} style={{
              background: benchmark === b ? 'rgba(0,180,216,0.12)' : 'transparent',
              border: `1px solid ${benchmark === b ? 'var(--col-cyan)' : 'var(--col-border)'}`,
              color: benchmark === b ? 'var(--col-cyan)' : 'var(--col-dim)',
              fontFamily: 'inherit', fontSize: 9, fontWeight: 600,
              padding: '2px 7px', cursor: 'pointer', letterSpacing: '0.5px',
            }}>{BM_LABELS[b]}</button>
          ))}
        </div>
        <button
          onClick={() => qc.invalidateQueries({ queryKey: ['correlation-matrix', benchmark, 30] })}
          style={{ background: 'none', border: 'none', color: 'var(--col-dim)', cursor: 'pointer', fontSize: 13 }}
          title="Refresh"
        >↺</button>
      </div>

      {/* Table */}
      <div style={{ flex: 1, overflow: 'auto' }}>
        {isLoading && <div className="widget-loading">Computing correlations…</div>}
        {(error || (!isLoading && !data)) && <div className="widget-error">Correlation data unavailable</div>}

        {data && (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: 'var(--col-elevated)', borderBottom: '1px solid var(--col-amber)' }}>
                {[
                  { h: 'DRIVER',    align: 'left'   as const },
                  { h: '30D',       align: 'right'  as const },
                  { h: '60D',       align: 'right'  as const },
                  { h: 'DIRECTION', align: 'right'  as const },
                  { h: 'SIGNAL',    align: 'right'  as const },
                  { h: '',          align: 'center' as const },
                ].map(({ h, align }, i) => (
                  <th key={i} style={{
                    padding: '4px 8px', fontSize: 9, fontWeight: 600, letterSpacing: '0.5px',
                    color: 'var(--col-amber)', textAlign: align, whiteSpace: 'nowrap',
                    position: 'sticky', top: 0, background: 'var(--col-elevated)',
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Object.entries(data.correlations).map(([name, driver]) => (
                <DriverRow
                  key={name}
                  name={name}
                  driver={driver}
                  expanded={expanded === name}
                  onToggle={() => setExpanded(p => p === name ? null : name)}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Footer */}
      {data && (
        <div style={{
          flexShrink: 0, padding: '3px 10px', borderTop: '1px solid var(--col-border)',
          background: 'var(--col-surface)', display: 'flex', justifyContent: 'space-between',
        }}>
          <span style={{ fontSize: 9, color: 'var(--col-dim)' }}>window=30d · {data.benchmark}</span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span className="live-dot" />
            <span style={{ fontSize: 9, color: 'var(--col-emerald)' }}>LIVE · 60s</span>
          </span>
        </div>
      )}
    </div>
  );
}
