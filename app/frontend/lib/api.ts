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
};
