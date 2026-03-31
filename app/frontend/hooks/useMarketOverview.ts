import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api';

export function useMarketOverview() {
  return useQuery({
    queryKey: ['market-overview'],
    queryFn:  () => api.marketOverview(),
    staleTime: 5 * 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
  });
}
