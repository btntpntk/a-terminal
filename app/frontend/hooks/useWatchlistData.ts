import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api';

export function useWatchlistData(tickers: string[]) {
  const key = tickers.slice().sort().join(',');
  return useQuery({
    queryKey:  ['watchlist', key],
    queryFn:   () => api.watchlist(tickers),
    staleTime: 5 * 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
    enabled:   tickers.length > 0,
  });
}
