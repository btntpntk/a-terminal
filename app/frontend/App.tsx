import { useCallback, useRef, useState } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Topbar } from './components/layout/Topbar';
import { Statusbar } from './components/layout/Statusbar';
import { RegimePanel } from './components/panels/RegimePanel';
import { MacroPanel } from './components/panels/MacroPanel';
import { SectorPanel } from './components/panels/SectorPanel';
import { NewsPanel } from './components/panels/NewsPanel';
import { RankingsTable } from './components/rankings/RankingsTable';
import { ScanProgressOverlay } from './components/scan/ScanProgressOverlay';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

const MIN_COL  = 180;
const MAX_COL  = 600;
const MIN_ROW  = 120;

function saved(key: string, fallback: number) {
  const v = localStorage.getItem(key);
  return v !== null ? Number(v) : fallback;
}

function Dashboard() {
  const [leftWidth,    setLeftWidth]    = useState(() => saved('panel.leftWidth',    320));
  const [sectorHeight, setSectorHeight] = useState(() => saved('panel.sectorHeight', 300));
  const [sectorWidth,  setSectorWidth]  = useState(() => saved('panel.sectorWidth',  260));
  const dragging = useRef<null | 'left' | 'sector-h' | 'sector-w'>(null);
  const startPos = useRef(0);
  const startSz  = useRef(0);

  const onMouseDownCol = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    dragging.current = 'left';
    startPos.current = e.clientX;
    startSz.current  = leftWidth;
    const onMove = (ev: MouseEvent) => {
      if (dragging.current !== 'left') return;
      const w = Math.min(MAX_COL, Math.max(MIN_COL, startSz.current + ev.clientX - startPos.current));
      setLeftWidth(w);
      localStorage.setItem('panel.leftWidth', String(w));
    };
    const onUp = () => { dragging.current = null; window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp); };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  }, [leftWidth]);

  const onMouseDownRow = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    dragging.current = 'sector-h';
    startPos.current = e.clientY;
    startSz.current  = sectorHeight;
    const onMove = (ev: MouseEvent) => {
      if (dragging.current !== 'sector-h') return;
      const h = Math.max(MIN_ROW, startSz.current + ev.clientY - startPos.current);
      setSectorHeight(h);
      localStorage.setItem('panel.sectorHeight', String(h));
    };
    const onUp = () => { dragging.current = null; window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp); };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  }, [sectorHeight]);

  const onMouseDownSectorW = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    dragging.current = 'sector-w';
    startPos.current = e.clientX;
    startSz.current  = sectorWidth;
    const onMove = (ev: MouseEvent) => {
      if (dragging.current !== 'sector-w') return;
      const w = Math.min(MAX_COL, Math.max(MIN_COL, startSz.current + ev.clientX - startPos.current));
      setSectorWidth(w);
      localStorage.setItem('panel.sectorWidth', String(w));
    };
    const onUp = () => { dragging.current = null; window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp); };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  }, [sectorWidth]);

  return (
    <div className="app-shell">
      <Topbar />

      <div className="main-layout">
        {/* Left panel */}
        <aside className="left-panel" style={{ width: leftWidth, minWidth: leftWidth }}>
          <RegimePanel />
          <div className="panel-divider" />
          <MacroPanel />
        </aside>

        {/* Left resize handle */}
        <div className="resize-handle" onMouseDown={onMouseDownCol} />

        {/* Right side — top row: Sector | News; bottom: Rankings */}
        <main className="center-panel" style={{ flexDirection: 'column' }}>

          {/* Top row */}
          <div style={{ height: sectorHeight, minHeight: sectorHeight, flexShrink: 0, display: 'flex', overflow: 'hidden' }}>
            <div style={{ width: sectorWidth, minWidth: sectorWidth, overflow: 'auto', borderRight: 'none', flexShrink: 0 }}>
              <SectorPanel />
            </div>

            <div className="resize-handle" onMouseDown={onMouseDownSectorW} />

            <div style={{ flex: 1, minWidth: 0, overflow: 'auto', borderLeft: '1px solid var(--col-border)' }}>
              <NewsPanel />
            </div>
          </div>

          <div className="resize-handle-h" onMouseDown={onMouseDownRow} />

          {/* Rankings */}
          <div style={{ flex: 1, minHeight: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            <RankingsTable />
          </div>
        </main>
      </div>

      <Statusbar />
      <ScanProgressOverlay />
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Dashboard />
    </QueryClientProvider>
  );
}
