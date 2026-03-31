import { useActiveTab } from '../../hooks/useActiveTab';
import { useTickerInfo } from '../../hooks/useTickerInfo';
import { SparklineChart } from './SparklineChart';

interface Props { tabId: string }

function fmtVol(n: number | null): string {
  if (n == null) return '—';
  return n >= 1e9 ? `${(n / 1e9).toFixed(3)} B`
       : n >= 1e6 ? `${(n / 1e6).toFixed(3)} M`
       : n >= 1e3 ? `${(n / 1e3).toFixed(1)} K`
       : String(n);
}

function fmtCap(n: number | null): string {
  if (n == null) return '—';
  return n >= 1e12 ? `${(n / 1e12).toFixed(2)}T`
       : n >= 1e9  ? `${(n / 1e9).toFixed(2)}B`
       : n >= 1e6  ? `${(n / 1e6).toFixed(2)}M`
       : String(n);
}

export function TickerInfoWidget({ tabId: _ }: Props) {
  const { activeTicker } = useActiveTab();
  const { data, isLoading, isError } = useTickerInfo(activeTicker);

  if (isLoading) return <div className="widget-loading">Loading…</div>;
  if (isError)   return <div className="widget-error">Failed to load {activeTicker}</div>;
  if (!data)     return null;

  const pos = (data.change_pct ?? 0) >= 0;
  const changeColor = pos ? 'var(--col-green)' : 'var(--col-red)';
  const arrow = pos ? '▲' : '▼';

  return (
    <div className="ti-wrap">
      {/* Left: sparkline */}
      <div className="ti-chart-col">
        <SparklineChart data={data.sparkline} positive={pos} width={160} height={80} />
      </div>

      {/* Right: metrics */}
      <div className="ti-metrics-col">
        <div className="ti-price-row">
          <span className="ti-price">
            {data.price != null
              ? data.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
              : '—'}
          </span>
          {data.change != null && data.change_pct != null && (
            <span className="ti-change" style={{ color: changeColor }}>
              {arrow} {Math.abs(data.change).toFixed(2)} ({pos ? '+' : ''}{data.change_pct.toFixed(2)}%)
            </span>
          )}
        </div>

        <div className="ti-vol-row">
          <span className="ti-vol-label">Volume:</span>
          <span className="ti-vol-val">{fmtVol(data.volume)}</span>
          {data.market_cap != null && (
            <>
              <span className="ti-vol-label" style={{ marginLeft: 12 }}>Mkt Cap:</span>
              <span className="ti-vol-val">{fmtCap(data.market_cap)}</span>
            </>
          )}
        </div>

        <div className="ti-tags-row">
          {data.industry && <span className="ti-tag">{data.industry}</span>}
          {data.country  && <span className="ti-tag-sep">|</span>}
          {data.country  && <span className="ti-tag">{data.country}</span>}
          {data.currency && <span className="ti-tag-sep">|</span>}
          {data.currency && <span className="ti-tag" style={{ color: 'var(--col-amber)', fontWeight: 600 }}>{data.currency}</span>}
        </div>
      </div>
    </div>
  );
}
