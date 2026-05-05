import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useTransferEntropy, useSectorTEMatrix } from '../../hooks/useQueries';
import type { LeakageSignal } from '../../types/api';

// eslint-disable-next-line @typescript-eslint/no-unused-vars
interface Props { tabId: string }

type View = 'leakage' | 'sector';

const LEAKAGE_META: Record<LeakageSignal, { label: string; color: string }> = {
  HIGH:     { label: 'HIGH LEAKAGE',  color: 'var(--col-crimson)' },
  MODERATE: { label: 'MODERATE FLOW', color: 'var(--col-amber)'   },
  REVERSE:  { label: 'PRICE LEADS',   color: 'var(--col-cyan)'    },
  NONE:     { label: 'NO FLOW',       color: 'var(--col-dim)'     },
};

const SET50_TARGETS = ['^SET.BK', '^GSPC', 'EEM'] as const;
type Target = typeof SET50_TARGETS[number];
const TARGET_LABELS: Record<Target, string> = { '^SET.BK': 'SET', '^GSPC': 'S&P', 'EEM': 'EEM' };

function TESparkline({ series }: { series: Array<{ te: number }> }) {
  if (series.length < 2) return null;
  const vals = series.map(s => s.te);
  const max  = Math.max(...vals, 1e-9);
  const W = 100, H = 28;
  const pts = vals.map((v, i) => {
    const x = (i / (vals.length - 1)) * W;
    const y = H - (v / max) * H;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  return (
    <svg width={W} height={H} style={{ display: 'block', overflow: 'visible', flexShrink: 0 }}>
      <polyline points={pts} fill="none" stroke="var(--col-amber)" strokeWidth="1.2" opacity="0.85" />
      <line x1="0" y1={H} x2={W} y2={H} stroke="var(--col-border)" strokeWidth="0.5" />
    </svg>
  );
}

function NetFlowBar({ net, max }: { net: number; max: number }) {
  const pct   = max > 0 ? Math.min(Math.abs(net) / max, 1) * 100 : 0;
  const color = net > 0 ? 'var(--col-crimson)' : net < 0 ? 'var(--col-cyan)' : 'var(--col-dim)';
  return (
    <div style={{ display: 'flex', alignItems: 'center', width: '100%', height: 6, gap: 0 }}>
      <div style={{ flex: 1, height: '100%', background: 'var(--col-border)', position: 'relative', overflow: 'hidden' }}>
        {net < 0 && (
          <div style={{ position: 'absolute', right: 0, top: 0, bottom: 0, width: `${pct}%`, background: color }} />
        )}
      </div>
      <div style={{ width: 1, height: 10, background: 'var(--col-slate)', flexShrink: 0 }} />
      <div style={{ flex: 1, height: '100%', background: 'var(--col-border)', position: 'relative', overflow: 'hidden' }}>
        {net > 0 && (
          <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: `${pct}%`, background: color }} />
        )}
      </div>
    </div>
  );
}

type TELevel = 'HIGH' | 'MED' | 'LOW' | 'NONE';

const LEVEL_META: Record<Exclude<TELevel, 'NONE'>, { color: string; activeColor: string }> = {
  HIGH: { color: 'rgba(192,57,43,0.55)', activeColor: 'var(--col-crimson)' },
  MED:  { color: 'rgba(192,57,43,0.28)', activeColor: 'var(--col-amber)'   },
  LOW:  { color: 'rgba(0,180,216,0.18)', activeColor: 'var(--col-cyan)'    },
};

function teLevel(v: number, max: number): TELevel {
  if (max === 0) return 'NONE';
  const r = v / max;
  if (r > 0.7)  return 'HIGH';
  if (r > 0.4)  return 'MED';
  if (r > 0.15) return 'LOW';
  return 'NONE';
}

function teLevelColor(level: TELevel): string {
  if (level === 'NONE') return 'var(--col-surface)';
  return LEVEL_META[level].color;
}

function SectorMatrix() {
  const { data, isLoading, error } = useSectorTEMatrix();
  const qc = useQueryClient();
  const [selected, setSelected] = useState<Set<Exclude<TELevel, 'NONE'>>>(
    new Set(['HIGH', 'MED', 'LOW'])
  );

  if (isLoading) return <div className="widget-loading">Computing sector flows…</div>;
  if (error || !data) return <div className="widget-error">Sector data unavailable</div>;

  const { sectors, matrix } = data;
  const allVals = sectors.flatMap(src =>
    sectors.filter(t => t !== src).map(tgt => matrix[src]?.[tgt] ?? 0)
  );
  const maxVal = Math.max(...allVals, 1e-9);

  const toggleLevel = (lvl: Exclude<TELevel, 'NONE'>) =>
    setSelected(prev => {
      const next = new Set(prev);
      next.has(lvl) ? next.delete(lvl) : next.add(lvl);
      return next;
    });

  const hasMatchingCell = (s: string) =>
    sectors.some(t => {
      if (t === s) return false;
      const rowLvl = teLevel(matrix[s]?.[t] ?? 0, maxVal);
      const colLvl = teLevel(matrix[t]?.[s] ?? 0, maxVal);
      return (rowLvl !== 'NONE' && selected.has(rowLvl as Exclude<TELevel, 'NONE'>)) ||
             (colLvl !== 'NONE' && selected.has(colLvl as Exclude<TELevel, 'NONE'>));
    });

  const visibleSectors = sectors.filter(hasMatchingCell);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 6, padding: '4px 10px',
        background: 'var(--col-elevated)', borderBottom: '1px solid var(--col-border)', flexShrink: 0,
      }}>
        <span style={{ fontSize: 9, color: 'var(--col-slate)', letterSpacing: '1px', flex: 1 }}>
          TE(ROW → COL) · {data.window}D · lag={data.lag}
        </span>
        {(['HIGH', 'MED', 'LOW'] as const).map(lvl => {
          const active = selected.has(lvl);
          return (
            <button key={lvl} onClick={() => toggleLevel(lvl)} style={{
              background: active ? LEVEL_META[lvl].color : 'transparent',
              border: `1px solid ${active ? LEVEL_META[lvl].activeColor : 'var(--col-border)'}`,
              color: active ? LEVEL_META[lvl].activeColor : 'var(--col-dim)',
              fontFamily: 'inherit', fontSize: 8, fontWeight: 700,
              padding: '2px 6px', cursor: 'pointer', letterSpacing: '0.3px',
            }}>{lvl}</button>
          );
        })}
        <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
          <span className="live-dot" />
          <span style={{ fontSize: 8, color: 'var(--col-emerald)' }}>60s</span>
        </span>
        <button
          onClick={() => qc.invalidateQueries({ queryKey: ['sector-te-matrix'] })}
          style={{ background: 'none', border: 'none', color: 'var(--col-dim)', cursor: 'pointer', fontSize: 13 }}
          title="Refresh"
        >↺</button>
      </div>

      <div style={{ flex: 1, overflow: 'auto', padding: '8px' }}>
        {visibleSectors.length === 0 ? (
          <div className="widget-loading">No sectors match the selected level(s)</div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed' }}>
            <thead>
              <tr>
                <th style={{ width: 52, padding: '3px 6px', fontSize: 8, color: 'var(--col-slate)', textAlign: 'left' }}>SRC↓ TGT→</th>
                {visibleSectors.map(s => (
                  <th key={s} style={{ padding: '3px 4px', fontSize: 9, fontWeight: 700, color: 'var(--col-amber)', textAlign: 'center', letterSpacing: '0.3px' }}>{s}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {visibleSectors.map(src => (
                <tr key={src}>
                  <td style={{ padding: '3px 6px', fontSize: 9, fontWeight: 700, color: 'var(--col-body)', whiteSpace: 'nowrap' }}>{src}</td>
                  {visibleSectors.map(tgt => {
                    const v    = src === tgt ? null : (matrix[src]?.[tgt] ?? null);
                    const lvl  = v != null ? teLevel(v, maxVal) : 'NONE';
                    const show = v != null && lvl !== 'NONE' && selected.has(lvl as Exclude<TELevel, 'NONE'>);
                    return (
                      <td
                        key={tgt}
                        title={v != null ? `${data.tickers[src]} → ${data.tickers[tgt]}` : undefined}
                        style={{
                          padding: '5px 2px', textAlign: 'center', fontSize: 9, fontWeight: 600,
                          background: show ? teLevelColor(lvl) : '#0a0f1a',
                          color: show ? 'var(--col-body)' : 'var(--col-dim)',
                          border: '1px solid var(--col-border)',
                          opacity: v != null && lvl !== 'NONE' && !show ? 0.25 : 1,
                          transition: 'opacity 0.15s, background 0.15s',
                        }}
                      >
                        {v != null && lvl !== 'NONE' ? v.toFixed(3) : ''}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

export function TransferEntropyWidget({ tabId: _ }: Props) {
  const [view,   setView]   = useState<View>('leakage');
  const [target, setTarget] = useState<Target>('^SET.BK');
  const qc = useQueryClient();

  const { data, isLoading, error } = useTransferEntropy('SEC_PROXY', target);

  const leakageMeta = data ? (LEAKAGE_META[data.leakage_signal] ?? LEAKAGE_META.NONE) : null;
  const maxFlow     = data ? Math.max(data.te_x_to_y, data.te_y_to_x, 1e-9) : 1e-9;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* Toolbar */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 6, padding: '4px 10px',
        background: 'var(--col-elevated)', borderBottom: '1px solid var(--col-border)', flexShrink: 0,
      }}>
        {(['leakage', 'sector'] as View[]).map(v => (
          <button key={v} onClick={() => setView(v)} style={{
            background: view === v ? 'rgba(0,180,216,0.12)' : 'transparent',
            border: `1px solid ${view === v ? 'var(--col-cyan)' : 'var(--col-border)'}`,
            color: view === v ? 'var(--col-cyan)' : 'var(--col-dim)',
            fontFamily: 'inherit', fontSize: 9, fontWeight: 700,
            padding: '2px 8px', cursor: 'pointer', letterSpacing: '0.5px', textTransform: 'uppercase',
          }}>{v === 'leakage' ? 'LEAKAGE' : 'SECTOR FLOW'}</button>
        ))}
        <div style={{ flex: 1 }} />
        {view === 'leakage' && SET50_TARGETS.map(t => (
          <button key={t} onClick={() => setTarget(t)} style={{
            background: target === t ? 'rgba(0,180,216,0.12)' : 'transparent',
            border: `1px solid ${target === t ? 'var(--col-cyan)' : 'var(--col-border)'}`,
            color: target === t ? 'var(--col-cyan)' : 'var(--col-dim)',
            fontFamily: 'inherit', fontSize: 9, padding: '2px 6px', cursor: 'pointer',
          }}>{TARGET_LABELS[t]}</button>
        ))}
        <button
          onClick={() => qc.invalidateQueries({ queryKey: ['transfer-entropy'] })}
          style={{ background: 'none', border: 'none', color: 'var(--col-dim)', cursor: 'pointer', fontSize: 13 }}
          title="Refresh"
        >↺</button>
      </div>

      {/* Body */}
      {view === 'sector' ? <SectorMatrix /> : (
        <div style={{ flex: 1, overflow: 'auto', padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 10 }}>
          {isLoading && <div className="widget-loading">Computing transfer entropy…</div>}
          {(error || (!isLoading && !data)) && <div className="widget-error">Transfer entropy unavailable</div>}

          {data && leakageMeta && (
            <>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div>
                  <div style={{ fontSize: 9, color: 'var(--col-slate)', letterSpacing: '1px' }}>SEC EVENT PROXY → PRICE ACTION</div>
                  <div style={{ fontSize: 9, color: 'var(--col-dim)', marginTop: 1 }}>{data.target} · {data.n_obs} obs · window={data.window}d</div>
                </div>
                <span style={{
                  fontSize: 9, fontWeight: 800, letterSpacing: '0.8px', padding: '3px 8px',
                  border: `1px solid ${leakageMeta.color}`, color: leakageMeta.color,
                }}>
                  {leakageMeta.label}
                </span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 6 }}>
                {[
                  { lbl: 'TE(X→Y)',  val: data.te_x_to_y.toFixed(4), color: 'var(--col-crimson)' },
                  { lbl: 'TE(Y→X)',  val: data.te_y_to_x.toFixed(4), color: 'var(--col-cyan)'    },
                  { lbl: 'NET FLOW', val: (data.net_flow >= 0 ? '+' : '') + data.net_flow.toFixed(4), color: data.net_flow > 0 ? 'var(--col-crimson)' : 'var(--col-cyan)' },
                  { lbl: 'NORM TE',  val: (data.normalized_te * 100).toFixed(1) + '%', color: 'var(--col-body)' },
                ].map(({ lbl, val, color }) => (
                  <div key={lbl} style={{ background: 'var(--col-elevated)', padding: '6px 8px', border: '1px solid var(--col-border)' }}>
                    <div style={{ fontSize: 8, color: 'var(--col-dim)', letterSpacing: '0.5px', marginBottom: 2 }}>{lbl}</div>
                    <div style={{ fontSize: 13, fontWeight: 700, color, fontVariantNumeric: 'tabular-nums' }}>{val}</div>
                  </div>
                ))}
              </div>

              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                  <span style={{ fontSize: 8, color: 'var(--col-cyan)' }}>← PRICE LEADS</span>
                  <span style={{ fontSize: 8, color: 'var(--col-slate)', letterSpacing: '0.5px' }}>NET DIRECTION</span>
                  <span style={{ fontSize: 8, color: 'var(--col-crimson)' }}>EVENT LEADS →</span>
                </div>
                <NetFlowBar net={data.net_flow} max={maxFlow} />
              </div>

              {data.series.length > 1 && (
                <div>
                  <div style={{ fontSize: 8, color: 'var(--col-dim)', marginBottom: 4, letterSpacing: '0.5px' }}>ROLLING TE SERIES</div>
                  <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8 }}>
                    <TESparkline series={data.series} />
                    <span style={{ fontSize: 9, color: 'var(--col-dim)' }}>{data.series.length}d</span>
                  </div>
                </div>
              )}

              <div style={{
                padding: '6px 8px', background: 'var(--col-elevated)',
                borderLeft: `2px solid ${leakageMeta.color}`,
                fontSize: 9, color: 'var(--col-slate)', fontStyle: 'italic', lineHeight: 1.5,
              }}>
                {data.interpretation}
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 'auto' }}>
                <span style={{ fontSize: 8, color: 'var(--col-dim)' }}>H(Y)={data.h_target.toFixed(3)} bits · bins={data.bins} · lag=({data.lag_x},{data.lag_y})</span>
                <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <span className="live-dot" />
                  <span style={{ fontSize: 8, color: 'var(--col-emerald)' }}>LIVE · 60s</span>
                </span>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
