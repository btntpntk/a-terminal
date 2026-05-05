import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../lib/api';
import { useAppStore } from '../store/useAppStore';

export function useUniverses() {
  return useQuery({
    queryKey: ['universes'],
    queryFn: () => api.universes(),
    staleTime: Infinity,
  });
}

export function useRegime(refresh = false) {
  const setRegime = useAppStore((s) => s.setRegime);
  return useQuery({
    queryKey: ['regime'],
    queryFn: async () => {
      const data = await api.regime(refresh);
      setRegime(data);
      return data;
    },
    staleTime: 14 * 60 * 1000,
    refetchInterval: 15 * 60 * 1000,
  });
}

export function useMacro() {
  const setMacro = useAppStore((s) => s.setMacro);
  return useQuery({
    queryKey: ['macro'],
    queryFn: async () => {
      const data = await api.macro();
      setMacro(data);
      return data;
    },
    staleTime: 28 * 60 * 1000,
    refetchInterval: 30 * 60 * 1000,
  });
}

export function useSectors() {
  const universe = useAppStore((s) => s.selectedUniverse);
  const setSectors = useAppStore((s) => s.setSectors);
  return useQuery({
    queryKey: ['sectors', universe],
    queryFn: async () => {
      const data = await api.sectors(universe);
      setSectors(data);
      return data;
    },
    staleTime: 28 * 60 * 1000,
  });
}

export function useRankings() {
  const universe = useAppStore((s) => s.selectedUniverse);
  const setRankings = useAppStore((s) => s.setRankings);
  return useQuery({
    queryKey: ['rankings', universe],
    queryFn: async () => {
      const data = await api.rankings(universe);
      setRankings(data);
      return data;
    },
    staleTime: 58 * 60 * 1000,
    retry: false,
  });
}

export function usePriceHistory(ticker: string | null, period = '3mo') {
  return useQuery({
    queryKey: ['price', ticker, period],
    queryFn: () => api.price(ticker!, period),
    enabled: !!ticker,
    staleTime: 60 * 60 * 1000,
  });
}

export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: () => api.health(),
    refetchInterval: 30 * 1000,
    staleTime: 25 * 1000,
  });
}

export function useRefreshRegime() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: ['regime'] });
}

export function useRefreshMacro() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: ['macro'] });
}

export function useRefreshRankings() {
  const universe = useAppStore((s) => s.selectedUniverse);
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: ['rankings', universe] });
}

export function useHMMRegime(ticker = 'SPY') {
  return useQuery({
    queryKey: ['hmm-regime', ticker],
    queryFn: () => api.hmmRegime({ ticker }),
    staleTime: 6 * 60 * 60 * 1000,   // 6 hours — matches backend cache
    retry: false,
  });
}

export function useMarketEntropy(ticker = '^SET.BK', days = 30) {
  return useQuery({
    queryKey: ['market-entropy', ticker, days],
    queryFn: () => api.marketEntropy({ ticker, days }),
    staleTime: 55 * 1000,
    refetchInterval: 60 * 1000,
    retry: 1,
  });
}

export function useCorrelationMatrix(benchmark = '^SET.BK', window = 30) {
  return useQuery({
    queryKey: ['correlation-matrix', benchmark, window],
    queryFn: () => api.correlationMatrix({ benchmark, window }),
    staleTime: 55 * 1000,
    refetchInterval: 60 * 1000,
    retry: 1,
  });
}

export function useTransferEntropy(
  source = 'SEC_PROXY',
  target = '^SET.BK',
  opts?: { lag_x?: number; lag_y?: number; bins?: number; window?: number },
) {
  return useQuery({
    queryKey: ['transfer-entropy', source, target, opts],
    queryFn:  () => api.transferEntropy({ source, target, ...opts }),
    staleTime: 55 * 1000,
    refetchInterval: 60 * 1000,
    retry: 1,
  });
}

export function useSectorTEMatrix(
  opts?: { lag?: number; bins?: number; window?: number },
) {
  return useQuery({
    queryKey: ['sector-te-matrix', opts],
    queryFn:  () => api.sectorTeMatrix(opts),
    staleTime: 55 * 1000,
    refetchInterval: 60 * 1000,
    retry: 1,
  });
}
