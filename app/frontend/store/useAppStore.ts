import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import type {
  RegimeResponse,
  MacroResponse,
  SectorsResponse,
  RankingsResponse,
  ScanProgress,
  FilterState,
} from '../types/api';
import {
  DEFAULT_ALPHA_WEIGHTS,
  DEFAULT_RANK_WEIGHTS,
  type AlphaWeights,
  type RankWeights,
} from '../lib/alphaScore';

interface AppStore extends FilterState {
  selectedUniverse: string;
  setUniverse: (key: string) => void;

  regime: RegimeResponse | null;
  macro: MacroResponse | null;
  sectors: SectorsResponse | null;
  rankings: RankingsResponse | null;
  setRegime: (r: RegimeResponse) => void;
  setMacro: (m: MacroResponse) => void;
  setSectors: (s: SectorsResponse) => void;
  setRankings: (r: RankingsResponse) => void;

  scanJobId: string | null;
  scanStatus: ScanProgress | null;
  setScanJob: (id: string) => void;
  setScanStatus: (s: ScanProgress) => void;
  clearScan: () => void;

  selectedTicker: string | null;
  setSelectedTicker: (t: string | null) => void;

  setFilters: (f: Partial<FilterState>) => void;

  alphaWeights: AlphaWeights;
  rankWeights: RankWeights;
  setAlphaWeights: (w: AlphaWeights) => void;
  setRankWeights: (w: RankWeights) => void;
  resetWeights: () => void;
}

export const useAppStore = create<AppStore>()(
  persist(
    (set) => ({
      selectedUniverse: 'SET100',
      setUniverse: (key) => set({ selectedUniverse: key, selectedTicker: null }),

      regime: null,
      macro: null,
      sectors: null,
      rankings: null,
      setRegime: (regime) => set({ regime }),
      setMacro: (macro) => set({ macro }),
      setSectors: (sectors) => set({ sectors }),
      setRankings: (rankings) => set({ rankings }),

      scanJobId: null,
      scanStatus: null,
      setScanJob: (id) => set({ scanJobId: id }),
      setScanStatus: (s) => set({ scanStatus: s }),
      clearScan: () => set({ scanJobId: null, scanStatus: null }),

      selectedTicker: null,
      setSelectedTicker: (t) => set({ selectedTicker: t }),

      verdictFilter: 'ALL',
      sectorFilter: '',
      tickerSearch: '',
      setFilters: (f) => set((s) => ({ ...s, ...f })),

      alphaWeights: DEFAULT_ALPHA_WEIGHTS,
      rankWeights: DEFAULT_RANK_WEIGHTS,
      setAlphaWeights: (alphaWeights) => set({ alphaWeights }),
      setRankWeights: (rankWeights) => set({ rankWeights }),
      resetWeights: () => set({
        alphaWeights: DEFAULT_ALPHA_WEIGHTS,
        rankWeights: DEFAULT_RANK_WEIGHTS,
      }),
    }),
    {
      name: 'alphas-app-store',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        alphaWeights: state.alphaWeights,
        rankWeights: state.rankWeights,
      }),
    },
  ),
);
