import { useQueryClient } from '@tanstack/react-query';
import { useMacro } from '../../hooks/useQueries';
import { useAppStore } from '../../store/useAppStore';
import { riskColor, quadrantColor, fmt } from '../../lib/format';
import type { MacroSignalDetail } from '../../types/api';

// eslint-disable-next-line @typescript-eslint/no-unused-vars
interface Props { tabId: string }

const ROWS: Array<{ key: keyof typeof KEYS; label: string }> = [
  { key: 'real_yield', label: 'REAL YLD' },
  { key: 'dxy',        label: 'DXY'      },
  { key: 'em_flows',   label: 'EM FLOWS' },
  { key: 'copper',     label: 'COPPER'   },
  { key: 'crude_oil',  label: 'OIL'      },
  { key: 'china',      label: 'CHINA'    },
  { key: 'thb',        label: 'THB'      },
  { key: 'gold',       label: 'GOLD'     },
];

// used only for typing
const KEYS = { real_yield:1, dxy:1, em_flows:1, copper:1, crude_oil:1, china:1, thb:1, gold:1 };
type MacroKey = keyof typeof KEYS;

export function MacroWidget({ tabId: _ }: Props) {
  const { data, isLoading, error } = useMacro();
  const macro = useAppStore(s => s.macro) ?? data;
  const qc = useQueryClient();

  if (isLoading) return <div className="widget-loading">Loading macro…</div>;
  if (error || !macro) return <div className="widget-error">Unavailable</div>;

  const qColor = quadrantColor(macro.cycle_quadrant);
  const adjEntries = Object.entries(macro.sector_adjustments)
    .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
    .slice(0, 6);
  const maxAdj = Math.max(...adjEntries.map(([, v]) => Math.abs(v)), 1);

  return (
    <div className="macro-widget-wrap">
      {/* Summary */}
      <div className="macro-summary">
        <div>
          <span className="macro-risk-num" style={{ color: riskColor(macro.composite_macro_risk) }}>
            {macro.composite_macro_risk.toFixed(0)}
          </span>
          <span className="macro-regime-lbl">{macro.macro_regime}</span>
        </div>
        <div className="macro-cycle">
          <span className="quadrant-pill" style={{ background: qColor, color: '#000', padding: '2px 8px', fontSize: '10px', fontWeight: 600 }}>
            {macro.cycle_quadrant}
          </span>
          <span className="macro-advice">{macro.quadrant_advice}</span>
        </div>
        <div className="macro-cuau">
          Cu/Au: <strong>{macro.copper_gold_ratio.toFixed(4)}</strong>
        </div>
        <button
          className="regime-refresh"
          onClick={() => qc.invalidateQueries({ queryKey: ['macro'] })}
          title="Refresh"
        >↺</button>
      </div>

      {/* Signal table — remove BIAS and SCORE columns */}
      <table className="w-table">
        <thead>
          <tr>
            <th style={{ textAlign: 'left' }}>SIG</th>
            <th style={{ textAlign: 'left' }}>TICKER</th>
            <th>PRICE</th>
            <th>20d%</th>
            <th>Z60</th>
            <th>WT</th>
          </tr>
        </thead>
        <tbody>
          {ROWS.map(row => {
            const detail = macro[row.key as MacroKey] as MacroSignalDetail;
            const weight = macro.signal_weights[row.key] ?? 0;
            return (
              <tr key={row.key}>
                <td style={{ textAlign: 'left', color: 'var(--col-amber)' }}>{row.label}</td>
                <td style={{ textAlign: 'left', color: 'var(--col-dim)' }}>{detail.ticker}</td>
                <td>{fmt.price(detail.current_price)}</td>
                <td style={{ color: (detail.mom_20d_pct ?? 0) >= 0 ? 'var(--col-buy)' : 'var(--col-red)' }}>
                  {fmt.pct(detail.mom_20d_pct)}
                </td>
                <td style={{ color: (detail.z_score_60d ?? 0) >= 0 ? 'var(--col-body)' : 'var(--col-red)' }}>
                  {fmt.z(detail.z_score_60d)}
                </td>
                <td style={{ color: 'var(--col-dim)' }}>{weight}%</td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {/* Sector adjustments */}
      <div className="macro-adj-header">SECTOR ADJ</div>
      <div className="macro-adj-list">
        {adjEntries.map(([sector, adj]) => {
          const pct = (Math.abs(adj) / maxAdj) * 100;
          const color = adj > 0 ? 'var(--col-amber)' : adj < 0 ? 'var(--col-red)' : 'var(--col-dim)';
          return (
            <div key={sector} className="macro-adj-row">
              <span className="macro-adj-sector">{sector}</span>
              <span style={{ color, minWidth: 28, textAlign: 'right', fontSize: '10px' }}>{adj >= 0 ? '+' : ''}{adj}</span>
              <div className="macro-bar-track">
                <div className="macro-bar-fill" style={{ width: `${pct}%`, background: color }} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
