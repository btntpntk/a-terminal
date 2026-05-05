export const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`);
  return res.json();
}

export const api = {
  universes: () =>
    apiFetch<{ universes: Array<{ key: string; display_name: string }> }>('/api/universes')
      .then((r) => r.universes.map((u) => ({ key: u.key, display_name: u.display_name }))),
  regime: (refresh?: boolean) =>
    apiFetch<import('../types/api').RegimeResponse>(`/api/regime${refresh ? '?refresh=true' : ''}`),
  macro: () => apiFetch<import('../types/api').MacroResponse>('/api/macro'),
  sectors: (universe: string) =>
    apiFetch<import('../types/api').SectorsResponse>(`/api/sectors/${universe}`),
  rankings: (universe: string) =>
    apiFetch<import('../types/api').RankingsResponse>(`/api/rankings/${universe}`),
  startScan: (universe: string) =>
    apiFetch<{ job_id: string }>(`/api/scan/start?universe=${universe}`, { method: 'POST' }),
  health: () => apiFetch<{ status: string }>('/api/health'),
  price: (ticker: string, period = '3mo') =>
    apiFetch<{ ticker: string; bars: Array<{ time: string; open: number; high: number; low: number; close: number; volume: number }> }>(
      `/api/price/${encodeURIComponent(ticker)}?period=${period}`
    ),
  cacheStats: () => apiFetch<{ keys: number }>('/api/cache/stats'),
  clearCache: () => apiFetch<void>('/api/cache', { method: 'DELETE' }),

  // ── Widget data ──────────────────────────────────────────
  marketOverview: () =>
    apiFetch<{
      instruments: Array<{
        id: string; name: string; ticker: string;
        price: number | null; change: number | null;
        change_pct: number | null; sparkline: number[];
      }>;
    }>('/api/market-overview'),

  watchlist: (tickers: string[]) =>
    apiFetch<{
      rows: Array<{
        ticker: string; price: number | null;
        day_pct: number | null; week_pct: number | null;
        month_pct: number | null; year_pct: number | null;
      }>;
    }>(`/api/watchlist?tickers=${encodeURIComponent(tickers.join(','))}`),

  tickerProfile: (ticker: string) =>
    apiFetch<{ ticker: string; profile: Record<string, unknown> }>(
      `/api/ticker/profile/${encodeURIComponent(ticker)}`
    ),

  tickerInfo: (ticker: string) =>
    apiFetch<{
      ticker: string; price: number | null; change: number | null;
      change_pct: number | null; volume: number | null;
      avg_volume: number | null; market_cap: number | null;
      sector: string | null; industry: string | null;
      country: string | null; currency: string | null;
      sparkline: number[];
    }>(`/api/ticker/info/${encodeURIComponent(ticker)}`),

  runBacktest: (req: import('../types/api').BacktestRequest) =>
    apiFetch<import('../types/api').BacktestResponse>('/api/backtest/run', {
      method: 'POST',
      body: JSON.stringify(req),
    }),

  runMCBacktest: (req: import('../types/api').MCBacktestRequest) =>
    apiFetch<import('../types/api').MCBacktestResponse>('/api/backtest/run-mc', {
      method: 'POST',
      body: JSON.stringify(req),
    }),

  inferBenchmark: (ticker: string) =>
    apiFetch<{ benchmark: string }>(`/api/backtest/infer-benchmark?ticker=${encodeURIComponent(ticker)}`),

  news: (ticker: string) =>
    apiFetch<{
      ticker: string;
      signal: 'bullish' | 'bearish' | 'neutral';
      confidence: number;
      high_impact_alert?: boolean;
      articles: Array<{
        title: string;
        summary: string;
        lang: string;
        ticker_source: string;
        source: string;
        published_at: number | null;
        sentiment: 'positive' | 'negative' | 'neutral';
        confidence: number;
        impact_tier: 'Tier 1: Systemic Catalyst' | 'Tier 2: Sector Shock' | 'Tier 3: Routine/Noise';
      }>;
      metrics: {
        total_articles: number;
        yfinance_articles: number;
        gnews_ticker_articles: number;
        macro_articles: number;
        bullish_articles: number;
        bearish_articles: number;
        neutral_articles: number;
        impact_tiers: { tier1: number; tier2: number; tier3: number };
      };
    }>(`/api/news?ticker=${encodeURIComponent(ticker)}`),

  newsHeadlines: () =>
    apiFetch<{
      global: Array<{
        title: string; summary: string; lang: string;
        ticker_source: string; source: string; published_at: number | null;
        sentiment: 'positive' | 'negative' | 'neutral';
        confidence: number;
        impact_tier: 'Tier 1: Systemic Catalyst' | 'Tier 2: Sector Shock' | 'Tier 3: Routine/Noise';
      }>;
      thai: Array<{
        title: string; summary: string; lang: string;
        ticker_source: string; source: string; published_at: number | null;
        sentiment: 'positive' | 'negative' | 'neutral';
        confidence: number;
        impact_tier: 'Tier 1: Systemic Catalyst' | 'Tier 2: Sector Shock' | 'Tier 3: Routine/Noise';
      }>;
      fetched_at: number;
    }>('/api/news/headlines'),

  hmmRegime: (params?: { ticker?: string; start?: string; train_end?: string; test_start?: string; refresh?: boolean }) => {
    const p = new URLSearchParams();
    if (params?.ticker)     p.set('ticker',     params.ticker);
    if (params?.start)      p.set('start',      params.start);
    if (params?.train_end)  p.set('train_end',  params.train_end);
    if (params?.test_start) p.set('test_start', params.test_start);
    if (params?.refresh)    p.set('refresh',    'true');
    return apiFetch<import('../types/api').HMMRegimeResponse>(`/api/hmm-regime?${p}`);
  },

  marketEntropy: (params?: { ticker?: string; days?: number; bins?: number; refresh?: boolean }) => {
    const p = new URLSearchParams();
    if (params?.ticker)  p.set('ticker',  params.ticker);
    if (params?.days)    p.set('days',    String(params.days));
    if (params?.bins)    p.set('bins',    String(params.bins));
    if (params?.refresh) p.set('refresh', 'true');
    return apiFetch<import('../types/api').EntropyResponse>(`/api/market/entropy?${p}`);
  },

  correlationMatrix: (params?: { benchmark?: string; window?: number; refresh?: boolean }) => {
    const p = new URLSearchParams();
    if (params?.benchmark) p.set('benchmark', params.benchmark);
    if (params?.window)    p.set('window',    String(params.window));
    if (params?.refresh)   p.set('refresh',   'true');
    return apiFetch<import('../types/api').CorrelationMatrixResponse>(`/api/macro/correlation-matrix?${p}`);
  },

  transferEntropy: (params?: {
    source?: string; target?: string; lag_x?: number; lag_y?: number;
    bins?: number; window?: number; refresh?: boolean;
  }) => {
    const p = new URLSearchParams();
    if (params?.source)         p.set('source', params.source);
    if (params?.target)         p.set('target', params.target);
    if (params?.lag_x  != null) p.set('lag_x',  String(params.lag_x));
    if (params?.lag_y  != null) p.set('lag_y',  String(params.lag_y));
    if (params?.bins   != null) p.set('bins',   String(params.bins));
    if (params?.window != null) p.set('window', String(params.window));
    if (params?.refresh)        p.set('refresh', 'true');
    return apiFetch<import('../types/api').TransferEntropyResponse>(`/api/analysis/transfer-entropy?${p}`);
  },

  sectorTeMatrix: (params?: { lag?: number; bins?: number; window?: number; refresh?: boolean }) => {
    const p = new URLSearchParams();
    if (params?.lag    != null) p.set('lag',    String(params.lag));
    if (params?.bins   != null) p.set('bins',   String(params.bins));
    if (params?.window != null) p.set('window', String(params.window));
    if (params?.refresh)        p.set('refresh', 'true');
    return apiFetch<import('../types/api').SectorTEMatrixResponse>(`/api/analysis/sector-te-matrix?${p}`);
  },
};
