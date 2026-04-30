import { useEffect } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Topbar } from './components/layout/Topbar';
import { Statusbar } from './components/layout/Statusbar';
import { ScanProgressOverlay } from './components/scan/ScanProgressOverlay';
import { TabBar } from './components/tabs/TabBar';
import { TabCanvas } from './components/tabs/TabCanvas';
import { WidgetPicker } from './components/tabs/WidgetPicker';
import { useAppStore } from './store/useAppStore';
import { api } from './lib/api';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

function Dashboard() {
  const rankings      = useAppStore(s => s.rankings);
  const scanJobId     = useAppStore(s => s.scanJobId);
  const universe      = useAppStore(s => s.selectedUniverse);
  const setScanJob    = useAppStore(s => s.setScanJob);

  useEffect(() => {
    if (rankings || scanJobId) return;
    api.startScan(universe).then(r => setScanJob(r.job_id)).catch(() => {});
  }, []);

  return (
    <div className="app-shell">
      <div className="topbar-with-viewtoggle">
        <Topbar />
        <WidgetPicker />
      </div>
      <div className="tab-system-root">
        <TabBar />
        <TabCanvas />
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
