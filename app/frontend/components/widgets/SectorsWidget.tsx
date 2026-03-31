import { useSectors } from '../../hooks/useQueries';
import { useAppStore } from '../../store/useAppStore';
import { fmt } from '../../lib/format';

// eslint-disable-next-line @typescript-eslint/no-unused-vars
interface Props { tabId: string }

export function SectorsWidget({ tabId: _ }: Props) {
  const { data, isLoading, error } = useSectors();
  const sectors = useAppStore(s => s.sectors) ?? data;
  const universe = useAppStore(s => s.selectedUniverse);

  if (isLoading) return <div className="widget-loading">Loading sectors…</div>;
  if (error || !sectors) return <div className="widget-error">Unavailable</div>;

  return (
    <div className="sectors-widget-wrap">
      {/* Universe label */}
      <div className="sectors-universe">{universe}</div>

      {/* Top / Avoid */}
      <div className="sectors-top-avoid">
        <div>
          <span className="sectors-lbl">TOP </span>
          <span style={{ color: 'var(--col-buy)', fontWeight: 600, fontSize: '10px' }}>
            {sectors.top_sectors.join(' · ')}
          </span>
        </div>
        <div>
          <span className="sectors-lbl">AVOID </span>
          <span style={{ color: 'var(--col-red)', fontWeight: 600, fontSize: '10px' }}>
            {sectors.avoid_sectors.join(' · ')}
          </span>
        </div>
      </div>

      {/* Sector table — remove GATE and ROTATION columns */}
      <table className="w-table">
        <thead>
          <tr>
            <th style={{ textAlign: 'right', width: 22 }}>RK</th>
            <th style={{ textAlign: 'left' }}>SECTOR</th>
            <th style={{ textAlign: 'left' }}>ETF</th>
            <th>SCORE</th>
            <th>MOM20</th>
            <th>RS</th>
          </tr>
        </thead>
        <tbody>
          {sectors.ranked_sectors.map((s, i) => (
            <tr key={s.sector}>
              <td style={{ color: 'var(--col-amber)', textAlign: 'right' }}>{i + 1}</td>
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
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
