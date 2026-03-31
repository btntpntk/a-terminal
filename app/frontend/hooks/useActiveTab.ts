import { useTabStore } from '../store/useTabStore';
import type { Tab } from '../types/tab';

export function useActiveTab(): Tab {
  const tabs       = useTabStore(s => s.tabs);
  const activeTabId = useTabStore(s => s.activeTabId);
  return tabs.find(t => t.id === activeTabId) ?? tabs[0];
}

export function useTabTicker(): string {
  return useActiveTab().activeTicker;
}
