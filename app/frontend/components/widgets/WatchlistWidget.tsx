import { useRankings } from '../../hooks/useQueries';
import { useWatchlistData } from '../../hooks/useWatchlistData';
import { useTabStore } from '../../store/useTabStore';

interface Props { tabId: string }

function pctCell(val: number | null) {
  if (val == null) return <td className="col-dim">—</td>;
  const pos = val >= 0;
  return <td className={pos ? 'col-green' : 'col-red'}>{pos ? '+' : ''}{val.toFixed(2)}%</td>;
}

export function WatchlistWidget({ tabId }: Props) {
  const { data: rankingsData } = useRankings();
  const setActiveTicker = useTabStore(s => s.setActiveTicker);

  const tickers = rankingsData?.rows.map(r => r.ticker) ?? [];
  const { data, isLoading, isError } = useWatchlistData(tickers);

  if (!rankingsData && !isLoading) {
    return (
      <div className="watchlist-wrap">
        <div className="widget-loading">Run a scan to populate the watchlist</div>
      </div>
    );
  }

  return (
    <div className="watchlist-wrap">
      {isLoading && <div className="widget-loading">Loading…</div>}
      {isError   && <div className="widget-error">Failed to load watchlist</div>}

      {data && (
        <table className="watchlist-table">
          <thead>
            <tr>
              <th>TICKER</th>
              <th>PRICE</th>
              <th>DAY</th>
              <th>WEEK</th>
              <th>MONTH</th>
              <th>YEAR</th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map(row => (
              <tr
                key={row.ticker}
                className="watchlist-row"
                onClick={() => setActiveTicker(tabId, row.ticker)}
                title={`Set ticker to ${row.ticker}`}
              >
                <td className="col-amber">{row.ticker}</td>
                <td>{row.price != null ? row.price.toLocaleString(undefined, { maximumFractionDigits: 2 }) : '—'}</td>
                {pctCell(row.day_pct)}
                {pctCell(row.week_pct)}
                {pctCell(row.month_pct)}
                {pctCell(row.year_pct)}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
