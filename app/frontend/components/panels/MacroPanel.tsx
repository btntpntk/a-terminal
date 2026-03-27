import { useQueryClient } from '@tanstack/react-query';
import { useMacro } from '../../hooks/useQueries';
import { useAppStore } from '../../store/useAppStore';
import { riskColor, signalColor, quadrantColor, fmt } from '../../lib/format';
import type { MacroSignalDetail } from '../../types/api';

interface SignalRow {
  key: string;
  label: string;
  detail: MacroSignalDetail;
  weight: number;
  score: number;
}

export function MacroPanel() {
  const { data, isLoading, error } = useMacro();
  const macro = useAppStore((s) => s.macro) ?? data;
  const qc = useQueryClient();

  const refresh = () => qc.invalidateQueries({ queryKey: ['macro'] });

  if (isLoading) return <div className="panel-section"><div className="section-label"> · GLOBAL MACRO</div><div className="loading">Loading…</div></div>;
  if (error || !macro) return <div className="panel-section"><div className="section-label"> · GLOBAL MACRO</div><div className="error">Unavailable</div></div>;

  const signalRows: SignalRow[] = [
    { key: 'real_yield', label: 'REAL YLD', detail: macro.real_yield, weight: macro.signal_weights['real_yield'] ?? 20, score: macro.raw_scores['real_yield'] ?? 0 },
    { key: 'dxy', label: 'DXY', detail: macro.dxy, weight: macro.signal_weights['dxy'] ?? 20, score: macro.raw_scores['dxy'] ?? 0 },
    { key: 'em_flows', label: 'EM FLOWS', detail: macro.em_flows, weight: macro.signal_weights['em_flows'] ?? 15, score: macro.raw_scores['em_flows'] ?? 0 },
    { key: 'copper', label: 'COPPER', detail: macro.copper, weight: macro.signal_weights['copper'] ?? 15, score: macro.raw_scores['copper'] ?? 0 },
    { key: 'crude_oil', label: 'OIL', detail: macro.crude_oil, weight: macro.signal_weights['crude_oil'] ?? 12, score: macro.raw_scores['crude_oil'] ?? 0 },
    { key: 'china', label: 'CHINA', detail: macro.china, weight: macro.signal_weights['china'] ?? 10, score: macro.raw_scores['china'] ?? 0 },
    { key: 'thb', label: 'THB', detail: macro.thb, weight: macro.signal_weights['thb'] ?? 5, score: macro.raw_scores['thb'] ?? 0 },
    { key: 'gold', label: 'GOLD', detail: macro.gold, weight: macro.signal_weights['gold'] ?? 3, score: macro.raw_scores['gold'] ?? 0 },
  ];

  const qColor = quadrantColor(macro.cycle_quadrant);
  const adjEntries = Object.entries(macro.sector_adjustments).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).slice(0, 8);
  const maxAdj = Math.max(...adjEntries.map(([, v]) => Math.abs(v)), 1);

  return (
    <div className="panel-section">
      <div className="section-header">
        <span className="section-label"> · GLOBAL MACRO</span>
        <button className="refresh-btn" onClick={refresh} title="Refresh">↺</button>
      </div>

      <div className="kv-grid">
        <div className="kv-row">
          <span className="kv-key">MACRO RISK</span>
          <span className="kv-val" style={{ color: riskColor(macro.composite_macro_risk), fontSize: '18px', fontWeight: 600 }}>
            {macro.composite_macro_risk.toFixed(0)}
          </span>
          <span className="kv-key" style={{ marginLeft: 12 }}>REGIME</span>
          <span className="kv-val amber">{macro.macro_regime}</span>
        </div>
        <div className="kv-row" style={{ gap: 8, flexWrap: 'wrap' }}>
          <span className="kv-key">CYCLE</span>
          <span className="quadrant-pill" style={{ background: qColor, color: '#000' }}>
            {macro.cycle_quadrant}
          </span>
          <span style={{ color: 'var(--col-dim)', fontSize: '10px', fontStyle: 'italic', flex: 1 }}>
            {macro.quadrant_advice}
          </span>
        </div>
        <div className="kv-row">
          <span className="kv-key">Cu/Au Ratio</span>
          <span className="kv-val">{macro.copper_gold_ratio.toFixed(4)}</span>
        </div>
      </div>

      <div className="terminal-rule" />

      <table className="indicator-table" style={{ fontSize: '10px' }}>
        <thead>
          <tr>
            <th style={{ textAlign: 'left' }}>SIG</th>
            <th style={{ textAlign: 'left' }}>TICKER</th>
            <th>PRICE</th>
            <th>20d%</th>
            <th>Z60</th>
            <th>BIAS</th>
            <th>WT</th>
            <th>SCORE</th>
          </tr>
        </thead>
        <tbody>
          {signalRows.map((row) => (
            <tr key={row.key}>
              <td style={{ textAlign: 'left', color: 'var(--col-amber)' }}>{row.label}</td>
              <td style={{ textAlign: 'left', color: 'var(--col-dim)' }}>{row.detail.ticker}</td>
              <td>{fmt.price(row.detail.current_price)}</td>
              <td style={{ color: (row.detail.mom_20d_pct ?? 0) >= 0 ? 'var(--col-buy)' : 'var(--col-red)' }}>
                {fmt.pct(row.detail.mom_20d_pct)}
              </td>
              <td style={{ color: (row.detail.z_score_60d ?? 0) >= 0 ? 'var(--col-body)' : 'var(--col-red)' }}>
                {fmt.z(row.detail.z_score_60d)}
              </td>
              <td style={{ color: signalColor(row.detail.macro_bias) }}>{row.detail.macro_bias}</td>
              <td style={{ color: 'var(--col-dim)' }}>{row.weight}%</td>
              <td style={{ color: riskColor(row.score) }}>{row.score.toFixed(0)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="terminal-rule" />

      <div className="section-sublabel">SECTOR ADJUSTMENTS</div>
      <div className="sector-adj-list">
        {adjEntries.map(([sector, adj]) => {
          const barW = Math.round((Math.abs(adj) / maxAdj) * 10);
          const color = adj > 0 ? 'var(--col-amber)' : adj < 0 ? 'var(--col-red)' : 'var(--col-dim)';
          return (
            <div key={sector} className="adj-row">
              <span className="adj-sector">{sector}</span>
              <span className="adj-val" style={{ color }}>{adj >= 0 ? '+' : ''}{adj}</span>
              <span className="adj-bar" style={{ color }}>
                {adj !== 0 ? '▮'.repeat(barW) : '·'}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
