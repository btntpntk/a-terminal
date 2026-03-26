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
