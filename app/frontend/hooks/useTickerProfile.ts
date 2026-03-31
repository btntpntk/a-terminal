import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api';

export function useTickerProfile(ticker: string) {
  return useQuery({
    queryKey: ['ticker-profile', ticker],
    queryFn:  () => api.tickerProfile(ticker),
    staleTime: 60 * 60 * 1000,
    enabled:   !!ticker,
  });
}
