import { useEffect, useRef, useState } from 'react';
import { useTabStore } from '../../store/useTabStore';
import type { WidgetType } from '../../types/tab';

interface WidgetOption {
  type: WidgetType;
  label: string;
  desc: string;
  group: string;
}

const WIDGET_OPTIONS: WidgetOption[] = [
  // Market data
  { group: 'MARKET',     type: 'market-overview',  label: 'Market Overview',    desc: 'Indices — S&P, Gold, Crude, SET with sparklines' },
  { group: 'MARKET',     type: 'regime',            label: 'Market Regime',      desc: 'Composite risk, VIX, yield curve, breadth' },
  { group: 'MARKET',     type: 'macro',             label: 'Global Macro',       desc: 'DXY, yields, copper, oil, EM flows cycle' },
  { group: 'MARKET',     type: 'sectors',           label: 'Sectors',            desc: 'Ranked sector table with momentum & RS' },
  { group: 'MARKET',     type: 'news',              label: 'Market News',        desc: 'Headlines with bullish/bearish/neutral tags' },
  // Ticker
  { group: 'TICKER',     type: 'ticker-info',       label: 'Ticker Info',        desc: 'Quick metrics — price, volume, sector sparkline' },
  { group: 'TICKER',     type: 'ticker-profile',    label: 'Ticker Profile',     desc: 'Valuation, fundamentals, analyst consensus' },
  { group: 'TICKER',     type: 'price-target',      label: 'Price Target Chart', desc: 'Interactive candlestick + volume chart' },
  { group: 'TICKER',     type: 'historical-price',  label: 'Historical Price',   desc: 'Full OHLCV table — 1 year of daily bars' },
  // Lists
  { group: 'LISTS',      type: 'watchlist',         label: 'Watchlist',          desc: 'Custom tickers — day/week/month/year %' },
  { group: 'LISTS',      type: 'rankings',          label: 'Rankings',           desc: 'Full alpha scan table with RUN SCAN control' },
  // Backtesting
  { group: 'ANALYSIS',   type: 'backtest',            label: 'Walk-Forward Backtest',    desc: 'Equity curve vs benchmark, KPIs, walk-forward folds' },
  { group: 'ANALYSIS',   type: 'hmm-regime',          label: 'HMM Regime Detector',      desc: 'Expanding-window Gaussian HMM — bull/sideways/bear with posteriors' },
  // Risk intelligence
  { group: 'RISK',       type: 'shannon-entropy',     label: 'Shannon Entropy',          desc: 'Systemic noise indicator — return distribution entropy for SET/S&P/VIX' },
  { group: 'RISK',       type: 'correlation-matrix',  label: 'Macro Correlation Matrix', desc: 'Rolling 30d correlation: US10Y, DXY, Brent, USD/THB vs SET50' },
];

interface Props {
  onWidgetAdded?: () => void;
}

export function WidgetPicker({ onWidgetAdded }: Props) {
  const [open, setOpen]   = useState(false);
  const wrapRef           = useRef<HTMLDivElement>(null);
  const activeTabId       = useTabStore(s => s.activeTabId);
  const addWidget         = useTabStore(s => s.addWidget);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const h = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, [open]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('keydown', h);
    return () => document.removeEventListener('keydown', h);
  }, [open]);

  const handleAdd = (type: WidgetType) => {
    addWidget(activeTabId, type);
    setOpen(false);
    onWidgetAdded?.();
  };

  // Group the options
  const groups = Array.from(new Set(WIDGET_OPTIONS.map(o => o.group)));

  return (
    <div ref={wrapRef} className="widget-picker-wrap">
      <button
        className={`widget-picker-btn${open ? ' active' : ''}`}
        onClick={() => setOpen(v => !v)}
        title="Add widget to dashboard"
      >
        ＋ WIDGET
      </button>

      {open && (
        <div className="widget-picker-panel">
          <div className="widget-picker-header">ADD WIDGET</div>
          {groups.map(group => (
            <div key={group}>
              <div className="widget-picker-group">{group}</div>
              {WIDGET_OPTIONS.filter(o => o.group === group).map(opt => (
                <button
                  key={opt.type}
                  className="widget-picker-item"
                  onClick={() => handleAdd(opt.type)}
                >
                  <span className="widget-picker-label">{opt.label}</span>
                  <span className="widget-picker-desc">{opt.desc}</span>
                </button>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
