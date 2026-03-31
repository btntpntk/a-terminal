import { useActiveTab } from '../../hooks/useActiveTab';
import { useStockHistory } from '../../hooks/useStockHistory';

interface Props { tabId: string }

export function HistoricalPriceWidget({ tabId: _ }: Props) {
  const { activeTicker } = useActiveTab();
  const { data, isLoading, isError } = useStockHistory(activeTicker, '1y');

  if (isLoading) return <div className="widget-loading">Loading…</div>;
  if (isError)   return <div className="widget-error">Failed to load {activeTicker}</div>;
  if (!data)     return null;

  const bars = data.bars.slice().reverse(); // most recent first

  return (
    <div className="hist-price-wrap">
      <table className="hist-table">
        <thead>
          <tr>
            <th>DATE</th>
            <th>OPEN</th>
            <th>HIGH</th>
            <th>LOW</th>
            <th>CLOSE</th>
            <th>VOLUME</th>
          </tr>
        </thead>
        <tbody>
          {bars.map(bar => {
            const up = bar.close >= bar.open;
            return (
              <tr key={bar.time}>
                <td className="hist-date">{bar.time}</td>
                <td>{bar.open.toFixed(2)}</td>
                <td>{bar.high.toFixed(2)}</td>
                <td>{bar.low.toFixed(2)}</td>
                <td className={up ? 'col-green' : 'col-red'}>{bar.close.toFixed(2)}</td>
                <td className="col-dim">{(bar.volume / 1e6).toFixed(2)}M</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
