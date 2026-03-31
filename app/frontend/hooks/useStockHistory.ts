import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api';

export function useStockHistory(ticker: string, period = '1y') {
  return useQuery({
    queryKey: ['stock-history', ticker, period],
    queryFn:  () => api.price(ticker, period),
    staleTime: 60 * 60 * 1000,
    enabled:   !!ticker,
  });
}
