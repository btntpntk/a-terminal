import { useQueryClient } from '@tanstack/react-query';
import { useRegime } from '../../hooks/useQueries';
import { useAppStore } from '../../store/useAppStore';
import { scoreBar, riskColor, signalColor } from '../../lib/format';

export function RegimePanel() {
  const { data, isLoading, error } = useRegime();
  const regime = useAppStore((s) => s.regime) ?? data;
  const qc = useQueryClient();

  const refresh = () => qc.invalidateQueries({ queryKey: ['regime'] });

  if (isLoading) return <div className="panel-section"><div className="section-label">STAGE 0 · MARKET REGIME</div><div className="loading">Loading…</div></div>;
  if (error || !regime) return <div className="panel-section"><div className="section-label">STAGE 0 · MARKET REGIME</div><div className="error">Unavailable</div></div>;

  const indicators = [
    { label: 'SPX vs 200DMA', val: regime.spx_distance_pct != null ? `${regime.spx_distance_pct >= 0 ? '+' : ''}${regime.spx_distance_pct.toFixed(1)}%` : '—', sig: regime.spx_signal, score: regime.spx_risk_score },
    { label: 'Yield Curve', val: regime.yield_spread_bps != null ? `${regime.yield_spread_bps}bp` : '—', sig: regime.yield_signal, score: regime.yield_risk_score },
    { label: 'HY Spread', val: regime.hy_oas_bps != null ? `${regime.hy_oas_bps}bp` : '—', sig: regime.hy_signal, score: regime.hy_risk_score },
    { label: 'Breadth >50DMA', val: regime.breadth_pct != null ? `${regime.breadth_pct.toFixed(0)}%` : '—', sig: regime.breadth_signal, score: regime.breadth_risk_score },
    { label: 'RSP/SPY Z', val: regime.rsp_z_score != null ? regime.rsp_z_score.toFixed(2) : '—', sig: regime.rsp_signal, score: regime.rsp_risk_score },
    { label: 'VIX Level', val: regime.vix_level != null ? regime.vix_level.toFixed(1) : '—', sig: regime.vix_signal, score: regime.vix_risk_score },
    { label: 'VIX Term', val: regime.vix_roll_yield != null ? regime.vix_roll_yield.toFixed(2) : '—', sig: regime.vix_term_signal, score: regime.vix_term_risk_score },
  ];

  const riskCol = riskColor(regime.composite_risk);

  return (
    <div className="panel-section">
      <div className="section-header">
        <span className="section-label">STAGE 0 · MARKET REGIME</span>
        <button className="refresh-btn" onClick={refresh} title="Refresh">↺</button>
      </div>

      <div className="kv-grid">
        <div className="kv-row">
          <span className="kv-key">COMPOSITE RISK</span>
          <span className="kv-val" style={{ color: riskCol, fontSize: '18px', fontWeight: 600 }}>
            {regime.composite_risk.toFixed(1)}
          </span>
        </div>
        <div className="kv-row">
          <span className="kv-key">REGIME</span>
          <span className="kv-val amber">{regime.regime_label}</span>
        </div>
        <div className="kv-row">
          <span className="kv-key">POSITION SCALE</span>
          <span className="kv-val" style={{ color: '#fff', fontSize: '14px', fontWeight: 500 }}>{regime.position_scale}</span>
        </div>
        <div className="kv-row">
          <span className="kv-key">CONFIDENCE</span>
          <span className="kv-val">{regime.confidence_signal} ({regime.confidence.toFixed(0)}%)</span>
        </div>
      </div>

      <div className="terminal-rule" />

      <table className="indicator-table">
        <thead>
          <tr>
            <th style={{ textAlign: 'left' }}>INDICATOR</th>
            <th>VAL</th>
            <th>SIG</th>
            <th>SCORE</th>
          </tr>
        </thead>
        <tbody>
          {indicators.map((ind) => (
            <tr key={ind.label}>
              <td style={{ textAlign: 'left', color: 'var(--col-body)' }}>{ind.label}</td>
              <td>{ind.val}</td>
              <td style={{ color: signalColor(ind.sig) }}>{ind.sig}</td>
              <td style={{ color: riskColor(ind.score) }}>{ind.score}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="terminal-rule" />

      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        {([
          ['Regime',    regime.layer_scores.regime],
          ['Fragility', regime.layer_scores.fragility],
          ['Trigger',   regime.layer_scores.trigger],
        ] as [string, number][]).map(([label, score], i) => (
          <>
            {i > 0 && <span key={`sep-${i}`} style={{ color: 'var(--col-border)', fontSize: '10px', flexShrink: 0 }}>|</span>}
            <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 4, flex: 1, minWidth: 0 }}>
              <span className="layer-label" style={{ flexShrink: 0 }}>{label}</span>
              <span className="score-bar" style={{ color: riskColor(score), letterSpacing: '-1px', fontSize: '10px', flex: 1 }}>
                {scoreBar(score)}
              </span>
              <span className="layer-num" style={{ color: riskColor(score), flexShrink: 0 }}>{score}</span>
            </div>
          </>
        ))}
      </div>
    </div>
  );
}
