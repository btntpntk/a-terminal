import { useState } from 'react';
import { useMarketOverview } from '../../hooks/useMarketOverview';
import { useWatchlistData } from '../../hooks/useWatchlistData';
import { useTabStore } from '../../store/useTabStore';
import { SparklineChart } from './SparklineChart';

interface Props { tabId: string }

export function MarketOverviewWidget({ tabId }: Props) {
  const { data, isLoading, isError } = useMarketOverview();
  const setActiveTicker = useTabStore(s => s.setActiveTicker);

  const [customTickers, setCustomTickers] = useState<string[]>([]);
  const [inputVal, setInputVal] = useState('');

  const { data: customData } = useWatchlistData(customTickers);

  const addTicker = () => {
    const t = inputVal.trim().toUpperCase();
    if (t && !customTickers.includes(t)) setCustomTickers(prev => [...prev, t]);
    setInputVal('');
  };

  if (isLoading) return <div className="widget-loading">Loading market data…</div>;
  if (isError)   return <div className="widget-error">Failed to load market data</div>;
  if (!data)     return null;

  return (
    <div className="mkt-overview-wrap">
      {/* Add index input */}
      <div className="mkt-add-row">
        <input
          className="mkt-add-input"
          placeholder="Add index…"
          value={inputVal}
          onChange={e => setInputVal(e.target.value.toUpperCase())}
          onKeyDown={e => { if (e.key === 'Enter') addTicker(); }}
        />
        <button className="mkt-add-btn" onClick={addTicker}>+</button>
        {customTickers.length > 0 && (
          <div className="mkt-custom-chips">
            {customTickers.map(t => (
              <span key={t} className="mkt-chip">
                {t}
                <button
                  className="mkt-chip-remove"
                  onClick={() => setCustomTickers(prev => prev.filter(x => x !== t))}
                >×</button>
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Cards grid */}
      <div className="mkt-overview-grid">
        {data.instruments.map(inst => {
          const pos = (inst.change_pct ?? 0) >= 0;
          const changeColor = pos ? 'var(--col-green)' : 'var(--col-red)';
          return (
            <div
              key={inst.id}
              className="mkt-card"
              onClick={() => setActiveTicker(tabId, inst.ticker)}
              title={`Set to ${inst.ticker}`}
            >
              <div className="mkt-card-top">
                <div>
                  <div className="mkt-card-name">{inst.name}</div>
                  <div className="mkt-card-price">
                    {inst.price != null
                      ? inst.price.toLocaleString(undefined, { maximumFractionDigits: 2 })
                      : '—'}
                  </div>
                  <div className="mkt-card-change" style={{ color: changeColor }}>
                    {inst.change != null && inst.change_pct != null
                      ? `${pos ? '+' : ''}${inst.change.toFixed(2)} (${pos ? '+' : ''}${inst.change_pct.toFixed(2)}%)`
                      : '—'}
                  </div>
                </div>
                <SparklineChart data={inst.sparkline} positive={pos} width={100} height={50} />
              </div>
            </div>
          );
        })}

        {customData?.rows.map(row => {
          const pos = (row.day_pct ?? 0) >= 0;
          const changeColor = pos ? 'var(--col-green)' : 'var(--col-red)';
          return (
            <div
              key={row.ticker}
              className="mkt-card mkt-card-custom"
              onClick={() => setActiveTicker(tabId, row.ticker)}
              title={`Set to ${row.ticker}`}
            >
              <div className="mkt-card-top">
                <div>
                  <div className="mkt-card-name">{row.ticker}</div>
                  <div className="mkt-card-price">
                    {row.price != null
                      ? row.price.toLocaleString(undefined, { maximumFractionDigits: 2 })
                      : '—'}
                  </div>
                  <div className="mkt-card-change" style={{ color: changeColor }}>
                    {row.day_pct != null
                      ? `${pos ? '+' : ''}${row.day_pct.toFixed(2)}%`
                      : '—'}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
