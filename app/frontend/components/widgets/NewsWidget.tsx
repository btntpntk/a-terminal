import { useState, useEffect, useCallback } from 'react';
import { api } from '../../lib/api';

interface Props { tabId: string }

type ImpactTier = 'Tier 1: Systemic Catalyst' | 'Tier 2: Sector Shock' | 'Tier 3: Routine/Noise';

interface Headline {
  title: string;
  summary: string;
  lang: string;
  ticker_source: string;
  source: string;
  published_at: number | null;
  sentiment: 'positive' | 'negative' | 'neutral';
  confidence: number;
  impact_tier: ImpactTier;
}

interface HeadlinesData {
  global: Headline[];
  thai: Headline[];
  fetched_at: number;
}

const REFRESH_MS = 5 * 60 * 1000;

const SENTIMENT_COLOR: Record<string, string> = {
  positive: 'var(--col-buy)',
  negative: 'var(--col-red)',
  neutral:  'var(--col-amber)',
};

const TIER_META: Record<ImpactTier, { label: string; color: string }> = {
  'Tier 1: Systemic Catalyst': { label: 'T1', color: 'var(--col-red)' },
  'Tier 2: Sector Shock':      { label: 'T2', color: 'var(--col-amber)' },
  'Tier 3: Routine/Noise':     { label: 'T3', color: 'var(--col-muted, #777)' },
};

function timeAgo(ts: number | null): string {
  if (!ts) return '';
  const s = Math.floor(Date.now() / 1000) - ts;
  if (s < 60)    return `${s}s ago`;
  if (s < 3600)  return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

function updatedLabel(fetchedAt: number): string {
  const s = Math.floor(Date.now() / 1000) - fetchedAt;
  if (s < 10)   return 'just now';
  if (s < 60)   return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  return `${Math.floor(s / 3600)}h ago`;
}

function HeadlineList({ items }: { items: Headline[] }) {
  if (!items.length) return <div className="news-empty">No headlines available.</div>;
  return (
    <div className="news-list">
      {items.map((h, i) => {
        const color = SENTIMENT_COLOR[h.sentiment] ?? SENTIMENT_COLOR.neutral;
        const tier  = TIER_META[h.impact_tier] ?? TIER_META['Tier 3: Routine/Noise'];
        const src   = h.source || (h.lang === 'th' ? 'TH' : 'EN');
        const ago   = timeAgo(h.published_at);
        return (
          <div key={i} className="news-item">
            <div className="news-accent" style={{ background: color }} />
            <div className="news-content">
              <div className="news-headline">{h.title}</div>
              <div className="news-meta">
                <span
                  className="news-tier-badge"
                  style={{ color: tier.color }}
                  title={h.impact_tier}
                >
                  {tier.label}
                </span>
                {src && <span className="news-source">{src}</span>}
                {ago && <span className="news-age">{ago}</span>}
                <span className="news-conf" style={{ color }}>{h.confidence}%</span>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function NewsWidget({ tabId: _ }: Props) {
  const [data, setData]       = useState<HeadlinesData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);
  const [now, setNow]         = useState(Date.now());

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    api.newsHeadlines()
      .then(d => { setData(d); setNow(Date.now()); })
      .catch(() => setError('Failed to load headlines'))
      .finally(() => setLoading(false));
  }, []);

  // Initial load + 5-minute auto-refresh
  useEffect(() => {
    load();
    const id = setInterval(load, REFRESH_MS);
    return () => clearInterval(id);
  }, [load]);

  // Tick "updated X min ago" every 30 s without re-fetching
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="news-headlines-wrap">

      {/* ── Global section ── */}
      <div className="news-section">
        <div className="news-section-header">
          <span className="news-section-title">🌐 Global Breaking News</span>
          <div className="news-section-meta">
            {loading && <span className="news-refreshing">Refreshing…</span>}
            {!loading && data && (
              <span className="news-updated">Updated {updatedLabel(data.fetched_at)}</span>
            )}
            <button className="news-refresh-btn" onClick={load} title="Refresh now">↻</button>
          </div>
        </div>
        <div className="news-section-body">
          {error   && <div className="widget-error">{error}</div>}
          {!error  && !data && !loading && <div className="widget-loading">Loading…</div>}
          {data    && <HeadlineList items={data.global} />}
        </div>
      </div>

      <div className="news-section-divider" />

      {/* ── Thai section ── */}
      <div className="news-section">
        <div className="news-section-header">
          <span className="news-section-title">🇹🇭 Thailand Breaking News</span>
          <span className="news-section-subtitle">Direct impact on SET stocks</span>
        </div>
        <div className="news-section-body">
          {data && <HeadlineList items={data.thai} />}
        </div>
      </div>

    </div>
  );
}
