import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api';

export function useTickerInfo(ticker: string) {
  return useQuery({
    queryKey: ['ticker-info', ticker],
    queryFn:  () => api.tickerInfo(ticker),
    staleTime: 5 * 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
    enabled:   !!ticker,
  });
}
