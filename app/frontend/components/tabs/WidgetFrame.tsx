import { useState, useCallback } from 'react';
import { useTabStore } from '../../store/useTabStore';
import { useActiveTab } from '../../hooks/useActiveTab';
import type { WidgetConfig, WidgetType } from '../../types/tab';

// Ticker-aware widgets
import { HistoricalPriceWidget } from '../widgets/HistoricalPriceWidget';
import { MarketOverviewWidget }  from '../widgets/MarketOverviewWidget';
import { WatchlistWidget }       from '../widgets/WatchlistWidget';
import { PriceTargetWidget }     from '../widgets/PriceTargetWidget';
import { TickerProfileWidget }   from '../widgets/TickerProfileWidget';
import { TickerInfoWidget }      from '../widgets/TickerInfoWidget';

// Panel-derived widgets (no per-ticker state)
import { RegimeWidget }          from '../widgets/RegimeWidget';
import { MacroWidget }           from '../widgets/MacroWidget';
import { SectorsWidget }         from '../widgets/SectorsWidget';
import { NewsWidget }            from '../widgets/NewsWidget';
import { RankingsWidget }        from '../widgets/RankingsWidget';
import { BacktestWidget }               from '../widgets/BacktestWidget';
import { HMMRegimeWidget }              from '../widgets/HMMRegimeWidget';
import { ShannonEntropyWidget }         from '../widgets/ShannonEntropyWidget';
import { GlobalMacroCorrelationWidget } from '../widgets/GlobalMacroCorrelationWidget';
import { TransferEntropyWidget }         from '../widgets/TransferEntropyWidget';
import { FundamentalWidget }            from '../widgets/FundamentalWidget';
import { HurstWidget }                  from '../widgets/HurstWidget';

// ── Widgets that use the tab's activeTicker in their header ──
const TICKER_WIDGETS = new Set<WidgetType>([
  'historical-price', 'price-target', 'ticker-profile', 'ticker-info', 'watchlist', 'fundamental',
]);

const WIDGET_LABELS: Record<WidgetType, string> = {
  'historical-price': 'HISTORICAL PRICE',
  'market-overview':  'MARKET OVERVIEW',
  'watchlist':        'WATCHLIST',
  'price-target':     'PRICE TARGET',
  'ticker-profile':   'TICKER PROFILE',
  'ticker-info':      'TICKER INFO',
  'regime':           'MARKET REGIME',
  'macro':            'GLOBAL MACRO',
  'sectors':          'SECTORS',
  'news':             'MARKET NEWS',
  'rankings':         'RANKINGS',
  'backtest':           'WALK-FORWARD BACKTEST',
  'hmm-regime':         'HMM REGIME DETECTOR',
  'shannon-entropy':    'SHANNON ENTROPY · SYSTEMIC RISK',
  'correlation-matrix': 'MACRO CORRELATION MATRIX',
  'transfer-entropy':   'TRANSFER ENTROPY · INFORMATION FLOW',
  'fundamental':        'FUNDAMENTALS · STAGE 3',
  'hurst-exponent':     'HURST EXPONENT · MARKET REGIME',
};

interface Props {
  widget: WidgetConfig;
  tabId: string;
}

function WidgetBody({ widget, tabId }: Props) {
  switch (widget.type) {
    case 'historical-price': return <HistoricalPriceWidget tabId={tabId} />;
    case 'market-overview':  return <MarketOverviewWidget  tabId={tabId} />;
    case 'watchlist':        return <WatchlistWidget       tabId={tabId} />;
    case 'price-target':     return <PriceTargetWidget     tabId={tabId} />;
    case 'ticker-profile':   return <TickerProfileWidget   tabId={tabId} />;
    case 'ticker-info':      return <TickerInfoWidget      tabId={tabId} />;
    case 'regime':           return <RegimeWidget          tabId={tabId} />;
    case 'macro':            return <MacroWidget           tabId={tabId} />;
    case 'sectors':          return <SectorsWidget         tabId={tabId} />;
    case 'news':             return <NewsWidget            tabId={tabId} />;
    case 'rankings':         return <RankingsWidget        tabId={tabId} />;
    case 'backtest':         return <BacktestWidget        tabId={tabId} />;
    case 'hmm-regime':         return <HMMRegimeWidget              tabId={tabId} />;
    case 'shannon-entropy':    return <ShannonEntropyWidget         tabId={tabId} />;
    case 'correlation-matrix': return <GlobalMacroCorrelationWidget tabId={tabId} />;
    case 'transfer-entropy':   return <TransferEntropyWidget        tabId={tabId} />;
    case 'fundamental':        return <FundamentalWidget            tabId={tabId} />;
    case 'hurst-exponent':     return <HurstWidget                  tabId={tabId} />;
    default:                   return null;
  }
}

export function WidgetFrame({ widget, tabId }: Props) {
  const tab             = useActiveTab();
  const setActiveTicker = useTabStore(s => s.setActiveTicker);
  const removeWidget    = useTabStore(s => s.removeWidget);

  const showTicker = TICKER_WIDGETS.has(widget.type);

  const [inputValue, setInputValue] = useState(tab.activeTicker);
  const [editing, setEditing]       = useState(false);

  const commitTicker = useCallback(() => {
    const v = inputValue.trim().toUpperCase();
    if (v) setActiveTicker(tabId, v);
    else   setInputValue(tab.activeTicker);
    setEditing(false);
  }, [inputValue, tabId, setActiveTicker, tab.activeTicker]);

  const displayTicker = editing ? inputValue : tab.activeTicker;

  return (
    <div className="widget-frame">
      <div className="widget-header">
        <span className="widget-label">{WIDGET_LABELS[widget.type] ?? widget.type}</span>

        {showTicker && (
          <div className="widget-ticker-area">
            <span className="widget-ticker-prefix">⇔</span>
            <input
              className="widget-ticker-input"
              value={displayTicker}
              onFocus={() => { setEditing(true); setInputValue(tab.activeTicker); }}
              onChange={e => setInputValue(e.target.value.toUpperCase())}
              onBlur={commitTicker}
              onKeyDown={e => {
                if (e.key === 'Enter') (e.target as HTMLInputElement).blur();
                if (e.key === 'Escape') { setInputValue(tab.activeTicker); setEditing(false); }
              }}
            />
          </div>
        )}

        <div style={{ flex: 1 }} />

        <button
          className="widget-close"
          onClick={() => removeWidget(tabId, widget.id)}
          title="Remove widget"
        >×</button>
      </div>

      <div className="widget-body">
        <WidgetBody widget={widget} tabId={tabId} />
      </div>
    </div>
  );
}
