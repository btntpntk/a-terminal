import { useActiveTab } from '../../hooks/useActiveTab';
import { useTickerProfile } from '../../hooks/useTickerProfile';

interface Props { tabId: string }

function fmtNum(val: unknown, type: 'pct' | 'large' | 'ratio' | 'plain' = 'plain'): string {
  if (val == null) return '—';
  const n = Number(val);
  if (isNaN(n)) return String(val);
  switch (type) {
    case 'pct':   return `${(n * 100).toFixed(2)}%`;
    case 'large': return n >= 1e12 ? `$${(n / 1e12).toFixed(2)}T`
                       : n >= 1e9  ? `$${(n / 1e9).toFixed(2)}B`
                       : n >= 1e6  ? `$${(n / 1e6).toFixed(2)}M`
                       : n.toLocaleString();
    case 'ratio': return n.toFixed(2);
    default:      return typeof val === 'number' ? n.toLocaleString() : String(val);
  }
}

const VALUATION_ROWS: Array<{ key: string; label: string; type?: 'pct' | 'large' | 'ratio' }> = [
  { key: 'marketCap',                   label: 'Market Cap',   type: 'large' },
  { key: 'enterpriseValue',             label: 'Enterprise Val', type: 'large' },
  { key: 'trailingPE',                  label: 'P/E (TTM)',    type: 'ratio' },
  { key: 'forwardPE',                   label: 'P/E (Fwd)',    type: 'ratio' },
  { key: 'priceToBook',                 label: 'P/B',          type: 'ratio' },
  { key: 'priceToSalesTrailing12Months',label: 'P/S',          type: 'ratio' },
];

const PROFITABILITY_ROWS: Array<{ key: string; label: string; type?: 'pct' | 'large' | 'ratio' }> = [
  { key: 'profitMargins',    label: 'Net Margin',   type: 'pct' },
  { key: 'operatingMargins', label: 'Op. Margin',   type: 'pct' },
  { key: 'grossMargins',     label: 'Gross Margin', type: 'pct' },
  { key: 'returnOnEquity',   label: 'ROE',          type: 'pct' },
  { key: 'returnOnAssets',   label: 'ROA',          type: 'pct' },
];

const ANALYST_ROWS: Array<{ key: string; label: string; type?: 'pct' | 'large' | 'ratio' }> = [
  { key: 'recommendationKey',       label: 'Consensus' },
  { key: 'numberOfAnalystOpinions', label: '# Analysts' },
  { key: 'targetMeanPrice',         label: 'Target (Mean)', type: 'ratio' },
  { key: 'targetHighPrice',         label: 'Target (High)', type: 'ratio' },
  { key: 'targetLowPrice',          label: 'Target (Low)',  type: 'ratio' },
];

function KVSection({ title, rows, p }: {
  title: string;
  rows: Array<{ key: string; label: string; type?: 'pct' | 'large' | 'ratio' }>;
  p: Record<string, unknown>;
}) {
  const visible = rows.filter(r => p[r.key] != null);
  if (visible.length === 0) return null;
  return (
    <div className="prof-section">
      <div className="prof-section-title">{title}</div>
      {visible.map(r => (
        <div key={r.key} className="prof-kv">
          <span className="prof-key">{r.label}</span>
          <span className="prof-val">{fmtNum(p[r.key], r.type)}</span>
        </div>
      ))}
    </div>
  );
}

export function TickerProfileWidget({ tabId: _ }: Props) {
  const { activeTicker } = useActiveTab();
  const { data, isLoading, isError } = useTickerProfile(activeTicker);

  if (isLoading) return <div className="widget-loading">Loading {activeTicker}…</div>;
  if (isError)   return <div className="widget-error">Failed to load {activeTicker}</div>;
  if (!data)     return null;

  const p = data.profile;
  const name    = p.shortName ?? p.longName ?? activeTicker;
  const sector  = [p.sector, p.industry].filter(Boolean).join(', ');
  const website = typeof p.website === 'string' ? p.website : null;
  const desc    = typeof p.longBusinessSummary === 'string' ? p.longBusinessSummary : null;

  return (
    <div className="prof-wrap">
      {/* Identity header */}
      <div className="prof-identity">
        <div className="prof-name">{String(name)}</div>
        {sector && <div className="prof-sector">Sector: {sector}</div>}
        {p.country != null && (
          <div className="prof-meta">
            {[p.country, p.exchange].filter(Boolean).join(' · ')}
          </div>
        )}
        {p.fullTimeEmployees != null && (
          <div className="prof-meta">
            Full time employees: {Number(p.fullTimeEmployees).toLocaleString()}
          </div>
        )}
        {website && (
          <a className="prof-website" href={website} target="_blank" rel="noreferrer">
            {website.replace(/^https?:\/\//, '')}
          </a>
        )}
      </div>

      {/* Description */}
      {desc && (
        <div className="prof-desc-wrap">
          <div className="prof-desc-title">Description</div>
          <p className="prof-desc">{desc}</p>
        </div>
      )}

      {/* Data sections */}
      <KVSection title="VALUATION"    rows={VALUATION_ROWS}    p={p} />
      <KVSection title="PROFITABILITY" rows={PROFITABILITY_ROWS} p={p} />
      <KVSection title="ANALYST"      rows={ANALYST_ROWS}      p={p} />
    </div>
  );
}
