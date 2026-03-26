import { useSectors } from '../../hooks/useQueries';
import { useAppStore } from '../../store/useAppStore';
import { fmt } from '../../lib/format';

export function SectorPanel() {
  const { data, isLoading, error } = useSectors();
  const sectors = useAppStore((s) => s.sectors) ?? data;
  const universe = useAppStore((s) => s.selectedUniverse);

  if (isLoading) return <div className="panel-section"><div className="section-label">STAGE 2 · SECTORS</div><div className="loading">Loading…</div></div>;
  if (error || !sectors) return <div className="panel-section"><div className="section-label">STAGE 2 · SECTORS</div><div className="error">Unavailable</div></div>;

  const rotationColor = sectors.sector_rotation === 'OFFENSIVE' ? 'var(--col-cyan)'
    : sectors.sector_rotation === 'DEFENSIVE' ? 'var(--col-amber)'
    : 'var(--col-dim)';

  return (
    <div className="panel-section">
      <div className="section-label">STAGE 2 · SECTORS · {universe}</div>

      <div className="kv-row" style={{ gap: 8, marginTop: 6 }}>
        <span className="kv-key">GATE:</span>
        <span style={{ color: sectors.sector_gate ? 'var(--col-buy)' : 'var(--col-red)', fontWeight: 600 }}>
          {sectors.sector_gate ? '✓ PASS' : '✗ FAIL'}
        </span>
        <span className="kv-key" style={{ marginLeft: 8 }}>ROTATION:</span>
        <span style={{ color: rotationColor, fontWeight: 600 }}>{sectors.sector_rotation}</span>
      </div>

      <div style={{ marginTop: 6 }}>
        <span className="kv-key">TOP </span>
        <span style={{ color: 'var(--col-buy)', fontWeight: 600, fontSize: '10px' }}>
          {sectors.top_sectors.join(' · ')}
        </span>
      </div>
      <div style={{ marginTop: 2 }}>
        <span className="kv-key">AVOID </span>
        <span style={{ color: 'var(--col-red)', fontWeight: 600, fontSize: '10px' }}>
          {sectors.avoid_sectors.join(' · ')}
        </span>
      </div>

      <div className="terminal-rule" />

      <table className="indicator-table" style={{ fontSize: '10px' }}>
        <thead>
          <tr>
            <th style={{ textAlign: 'right', width: 24 }}>RK</th>
            <th style={{ textAlign: 'left' }}>SECTOR</th>
            <th style={{ textAlign: 'left' }}>ETF</th>
            <th>SCORE</th>
            <th>MOM20</th>
            <th>RS</th>
            <th>GATE</th>
          </tr>
        </thead>
        <tbody>
          {sectors.ranked_sectors.map((s, i) => (
            <tr key={s.sector}>
              <td style={{ color: 'var(--col-amber)' }}>{i + 1}</td>
              <td style={{ textAlign: 'left' }}>{s.sector}</td>
              <td style={{ textAlign: 'left', color: 'var(--col-dim)' }}>{s.etf}</td>
              <td style={{ color: s.sector_score >= 60 ? 'var(--col-buy)' : s.sector_score >= 40 ? 'var(--col-amber)' : 'var(--col-red)' }}>
                {s.sector_score.toFixed(1)}
              </td>
              <td style={{ color: s.mom_20d_pct >= 0 ? 'var(--col-buy)' : 'var(--col-red)' }}>
                {fmt.pct(s.mom_20d_pct)}
              </td>
              <td style={{ color: s.rs_vs_index >= 0 ? 'var(--col-buy)' : 'var(--col-red)' }}>
                {s.rs_vs_index >= 0 ? '+' : ''}{s.rs_vs_index.toFixed(2)}
              </td>
              <td style={{ color: s.gate_pass ? 'var(--col-buy)' : 'var(--col-red)' }}>
                {s.gate_pass ? '✓' : '✗'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
