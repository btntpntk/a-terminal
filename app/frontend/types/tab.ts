import type { LayoutItem } from 'react-grid-layout';

export type WidgetType =
  | 'historical-price'
  | 'market-overview'
  | 'watchlist'
  | 'price-target'
  | 'ticker-profile'
  | 'ticker-info'
  | 'regime'
  | 'macro'
  | 'sectors'
  | 'news'
  | 'rankings'
  | 'backtest';

export interface WidgetConfig {
  id: string;     // matches LayoutItem 'i'
  type: WidgetType;
}

export interface Tab {
  id: string;
  name: string;
  activeTicker: string;
  layout: LayoutItem[];
  widgets: WidgetConfig[];
}
