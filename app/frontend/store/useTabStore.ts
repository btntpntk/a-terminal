import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { LayoutItem } from 'react-grid-layout';
import type { Tab, WidgetConfig, WidgetType } from '../types/tab';

// ─── Default layout helpers ──────────────────────────────────

let _widgetCounter = 0;
function genId() {
  return `w-${Date.now()}-${_widgetCounter++}`;
}

const DEFAULT_WIDGET_SIZES: Record<WidgetType, { w: number; h: number }> = {
  'market-overview':  { w: 12, h: 5 },
  'watchlist':        { w: 4,  h: 9 },
  'ticker-info':      { w: 5,  h: 5 },
  'historical-price': { w: 6,  h: 9 },
  'price-target':     { w: 8,  h: 10 },
  'ticker-profile':   { w: 4,  h: 12 },
  'regime':           { w: 4,  h: 11 },
  'macro':            { w: 6,  h: 11 },
  'sectors':          { w: 4,  h: 10 },
  'news':             { w: 4,  h: 8  },
  'rankings':         { w: 12, h: 12 },
  'backtest':         { w: 10, h: 14 },
};

/** Used by addTab() when the user clicks "+". */
function defaultTab(name: string, ticker = 'AAPL'): Tab {
  const w1 = genId();
  const w2 = genId();
  const w3 = genId();
  const w4 = genId();
  return {
    id:           `tab-${Date.now()}`,
    name,
    activeTicker: ticker,
    widgets: [
      { id: w1, type: 'market-overview' },
      { id: w2, type: 'ticker-info' },
      { id: w3, type: 'watchlist' },
      { id: w4, type: 'price-target' },
    ],
    layout: [
      { i: w1, x: 0, y: 0, w: 4, h: 9  },
      { i: w2, x: 4, y: 0, w: 4, h: 5  },
      { i: w3, x: 8, y: 0, w: 4, h: 9  },
      { i: w4, x: 0, y: 9, w: 8, h: 10 },
    ],
  };
}

// ─── Preset tabs (loaded on first run / after version reset) ─

function makeOverviewTab(): Tab {
  const wOverview = genId();
  const wNews     = genId();
  const wRegime   = genId();
  const wMacro    = genId();
  return {
    id:           'preset-overview',
    name:         'Overview',
    activeTicker: 'AAPL',
    widgets: [
      { id: wOverview, type: 'market-overview' },
      { id: wNews,     type: 'news'            },
      { id: wRegime,   type: 'regime'          },
      { id: wMacro,    type: 'macro'           },
    ],
    layout: [
      { i: wOverview, x: 0, y: 0,  w: 8, h: 4  },
      { i: wNews,     x: 8, y: 0,  w: 4, h: 13 },
      { i: wRegime,   x: 0, y: 4,  w: 4, h: 9  },
      { i: wMacro,    x: 4, y: 4,  w: 4, h: 9  },
    ],
  };
}

function makeQuoteTab(): Tab {
  const wInfo    = genId();
  const wProfile = genId();
  const wSectors = genId();
  const wChart   = genId();
  const wWatch   = genId();
  return {
    id:           'preset-quote',
    name:         'Quote',
    activeTicker: 'TISCO.BK',
    widgets: [
      { id: wInfo,    type: 'ticker-info'    },
      { id: wProfile, type: 'ticker-profile' },
      { id: wSectors, type: 'sectors'        },
      { id: wChart,   type: 'price-target'   },
      { id: wWatch,   type: 'watchlist'      },
    ],
    layout: [
      { i: wInfo,    x: 0, y: 0,  w: 3, h: 5  },
      { i: wProfile, x: 3, y: 0,  w: 5, h: 5  },
      { i: wSectors, x: 8, y: 0,  w: 4, h: 5  },
      { i: wChart,   x: 0, y: 5,  w: 8, h: 10 },
      { i: wWatch,   x: 8, y: 5,  w: 4, h: 10 },
    ],
  };
}

function makeRankingTab(): Tab {
  const wRank = genId();
  return {
    id:           'preset-ranking',
    name:         'Ranking',
    activeTicker: 'AAPL',
    widgets: [
      { id: wRank, type: 'rankings' },
    ],
    layout: [
      { i: wRank, x: 0, y: 0, w: 12, h: 12 },
    ],
  };
}

function makeBacktestTab(): Tab {
  const wBt1 = genId();
  const wBt2 = genId();
  return {
    id:           'preset-backtest',
    name:         'Backtest',
    activeTicker: 'AAPL',
    widgets: [
      { id: wBt1, type: 'backtest' },
      { id: wBt2, type: 'backtest' },
    ],
    layout: [
      { i: wBt1, x: 0, y: 0, w: 6, h: 14 },
      { i: wBt2, x: 6, y: 0, w: 6, h: 14 },
    ],
  };
}

const INITIAL_TABS: Tab[] = [
  makeOverviewTab(),
  makeQuoteTab(),
  makeRankingTab(),
  makeBacktestTab(),
];

// ─── Store ───────────────────────────────────────────────────

interface TabStore {
  tabs: Tab[];
  activeTabId: string;

  addTab: () => void;
  removeTab: (tabId: string) => void;
  renameTab: (tabId: string, name: string) => void;
  setActiveTab: (tabId: string) => void;
  setActiveTicker: (tabId: string, ticker: string) => void;
  setLayout: (tabId: string, layout: LayoutItem[]) => void;
  addWidget: (tabId: string, type: WidgetType) => void;
  removeWidget: (tabId: string, widgetId: string) => void;
}

export const useTabStore = create<TabStore>()(
  persist(
    (set, get) => ({
      tabs:        INITIAL_TABS,
      activeTabId: INITIAL_TABS[0].id,

      addTab: () => {
        const { tabs } = get();
        const tab = defaultTab(`Tab ${tabs.length + 1}`);
        set(s => ({ tabs: [...s.tabs, tab], activeTabId: tab.id }));
      },

      removeTab: (tabId) => {
        const { tabs, activeTabId } = get();
        if (tabs.length === 1) return;
        const idx    = tabs.findIndex(t => t.id === tabId);
        const next   = tabs.filter(t => t.id !== tabId);
        const nextId = activeTabId === tabId
          ? (next[Math.max(0, idx - 1)]?.id ?? next[0].id)
          : activeTabId;
        set({ tabs: next, activeTabId: nextId });
      },

      renameTab: (tabId, name) =>
        set(s => ({
          tabs: s.tabs.map(t => t.id === tabId ? { ...t, name } : t),
        })),

      setActiveTab: (tabId) => set({ activeTabId: tabId }),

      setActiveTicker: (tabId, ticker) =>
        set(s => ({
          tabs: s.tabs.map(t =>
            t.id === tabId ? { ...t, activeTicker: ticker.toUpperCase() } : t,
          ),
        })),

      setLayout: (tabId, layout) =>
        set(s => ({
          tabs: s.tabs.map(t => t.id === tabId ? { ...t, layout } : t),
        })),

      addWidget: (tabId, type) => {
        const id        = genId();
        const size      = DEFAULT_WIDGET_SIZES[type];
        const cfg: WidgetConfig  = { id, type };
        const item: LayoutItem   = { i: id, x: 0, y: Infinity, ...size };
        set(s => ({
          tabs: s.tabs.map(t =>
            t.id === tabId
              ? { ...t, widgets: [...t.widgets, cfg], layout: [...t.layout, item] }
              : t,
          ),
        }));
      },

      removeWidget: (tabId, widgetId) =>
        set(s => ({
          tabs: s.tabs.map(t =>
            t.id === tabId
              ? {
                  ...t,
                  widgets: t.widgets.filter(w => w.id !== widgetId),
                  layout:  t.layout.filter(l => l.i !== widgetId),
                }
              : t,
          ),
        })),
    }),
    {
      name:    'alphas-tabs',
      version: 2,
      migrate: (_state, _fromVersion) => ({
        tabs:        INITIAL_TABS,
        activeTabId: INITIAL_TABS[0].id,
      }),
      partialize: (s) => ({ tabs: s.tabs, activeTabId: s.activeTabId }),
    },
  ),
);
