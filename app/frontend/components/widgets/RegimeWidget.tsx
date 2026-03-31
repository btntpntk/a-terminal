import { useQueryClient } from '@tanstack/react-query';
import { useRegime } from '../../hooks/useQueries';
import { useAppStore } from '../../store/useAppStore';
import { riskColor } from '../../lib/format';

// eslint-disable-next-line @typescript-eslint/no-unused-vars
interface Props { tabId: string }

export function RegimeWidget({ tabId: _ }: Props) {
  const { data, isLoading, error } = useRegime();
  const regime = useAppStore(s => s.regime) ?? data;
  const qc = useQueryClient();

  if (isLoading) return <div className="widget-loading">Loading regime…</div>;
  if (error || !regime) return <div className="widget-error">Unavailable</div>;

  const riskCol = riskColor(regime.composite_risk);

  const indicators = [
    { label: 'SPX vs 200DMA',  val: regime.spx_distance_pct   != null ? `${regime.spx_distance_pct >= 0 ? '+' : ''}${regime.spx_distance_pct.toFixed(1)}%`   : '—' },
    { label: 'Yield Curve',     val: regime.yield_spread_bps   != null ? `${regime.yield_spread_bps}bp`                                                          : '—' },
    { label: 'HY Spread',       val: regime.hy_oas_bps         != null ? `${regime.hy_oas_bps}bp`                                                                : '—' },
    { label: 'Breadth >50DMA',  val: regime.breadth_pct        != null ? `${regime.breadth_pct.toFixed(0)}%`                                                     : '—' },
    { label: 'RSP/SPY Z',       val: regime.rsp_z_score        != null ? regime.rsp_z_score.toFixed(2)                                                           : '—' },
    { label: 'VIX Level',       val: regime.vix_level          != null ? regime.vix_level.toFixed(1)                                                             : '—' },
    { label: 'VIX Term',        val: regime.vix_roll_yield     != null ? regime.vix_roll_yield.toFixed(2)                                                        : '—' },
  ];

  return (
    <div className="regime-widget-wrap">
      {/* Summary row */}
      <div className="regime-summary">
        <div className="regime-risk" style={{ color: riskCol }}>
          {regime.composite_risk.toFixed(1)}
        </div>
        <div className="regime-meta">
          <div className="regime-label">{regime.regime_label}</div>
          <div className="regime-scale">
            Scale <strong>{regime.position_scale}</strong>
            &nbsp;· {regime.confidence_signal} ({regime.confidence.toFixed(0)}%)
          </div>
        </div>
        <button
          className="regime-refresh"
          onClick={() => qc.invalidateQueries({ queryKey: ['regime'] })}
          title="Refresh"
        >↺</button>
      </div>

      {/* Layer scores */}
      <div className="regime-layers">
        {([['Regime', regime.layer_scores.regime], ['Fragility', regime.layer_scores.fragility], ['Trigger', regime.layer_scores.trigger]] as [string, number][]).map(([label, score]) => (
          <div key={label} className="regime-layer-row">
            <span className="regime-layer-label">{label}</span>
            <div className="regime-bar-track">
              <div className="regime-bar-fill" style={{ width: `${Math.min(score, 100)}%`, background: riskColor(score) }} />
            </div>
            <span className="regime-layer-num" style={{ color: riskColor(score) }}>{score}</span>
          </div>
        ))}
      </div>

      {/* Indicator table */}
      <table className="w-table">
        <thead>
          <tr>
            <th style={{ textAlign: 'left' }}>INDICATOR</th>
            <th>VAL</th>
          </tr>
        </thead>
        <tbody>
          {indicators.map(ind => (
            <tr key={ind.label}>
              <td style={{ textAlign: 'left' }}>{ind.label}</td>
              <td>{ind.val}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
