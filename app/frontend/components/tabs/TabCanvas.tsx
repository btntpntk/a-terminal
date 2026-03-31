import { useCallback, useEffect, useRef, useState } from 'react';
import GridLayout from 'react-grid-layout';
import type { Layout, LayoutItem } from 'react-grid-layout';
import { useTabStore } from '../../store/useTabStore';
import { WidgetFrame } from './WidgetFrame';
import 'react-grid-layout/css/styles.css';
import 'react-resizable/css/styles.css';

function useContainerWidth(ref: React.RefObject<HTMLDivElement | null>) {
  const [width, setWidth] = useState(window.innerWidth);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(entries => {
      setWidth(entries[0].contentRect.width);
    });
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, [ref]);
  return width;
}

export function TabCanvas() {
  const tabs        = useTabStore(s => s.tabs);
  const activeTabId = useTabStore(s => s.activeTabId);
  const setLayout   = useTabStore(s => s.setLayout);
  const containerRef = useRef<HTMLDivElement>(null);
  const width        = useContainerWidth(containerRef);

  const onLayoutChange = useCallback(
    (layout: Layout, tabId: string) => {
      setLayout(tabId, layout as LayoutItem[]);
    },
    [setLayout],
  );

  return (
    <div className="tab-canvas" ref={containerRef}>
      {tabs.map(tab => (
        <div
          key={tab.id}
          style={{ display: tab.id === activeTabId ? 'block' : 'none' }}
        >
          <GridLayout
            className="widget-grid"
            layout={tab.layout}
            width={width}
            gridConfig={{ cols: 12, rowHeight: 40, margin: [6, 6], containerPadding: [8, 8], maxRows: Infinity }}
            dragConfig={{ enabled: true, handle: '.widget-header' }}
            resizeConfig={{ enabled: true, handles: ['se'] }}
            onLayoutChange={(layout) => onLayoutChange(layout, tab.id)}
          >
            {tab.widgets.map(widget => (
              <div key={widget.id} className="widget-cell">
                <WidgetFrame widget={widget} tabId={tab.id} />
              </div>
            ))}
          </GridLayout>
        </div>
      ))}
    </div>
  );
}
