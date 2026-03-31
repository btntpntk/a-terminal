import { useState, useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useAppStore } from '../../store/useAppStore';
import { useUniverses, useHealth } from '../../hooks/useQueries';
import { api } from '../../lib/api';

export function Topbar() {
  const [clock, setClock] = useState('');
  const { selectedUniverse, setUniverse, setScanJob } = useAppStore();
  const { data: universes } = useUniverses();
  const { data: health } = useHealth();
  const qc = useQueryClient();

  useEffect(() => {
    const tick = () => {
      const now = new Date();
      
      // Format the time specifically for Bangkok (Asia/Bangkok)
      const bangkokTime = now.toLocaleTimeString('en-GB', {
        timeZone: 'Asia/Bangkok',
        hour12: false, // Set to true if you prefer 12-hour format
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
      });

      setClock(bangkokTime + ' BKK');
    };

    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  const handleScan = async () => {
    try {
      const { job_id } = await api.startScan(selectedUniverse);
      setScanJob(job_id);
    } catch (e) {
      console.error('Failed to start scan', e);
    }
  };

  const handleUniverseChange = (val: string) => {
    setUniverse(val);
    qc.invalidateQueries({ queryKey: ['sectors', val] });
    qc.invalidateQueries({ queryKey: ['rankings', val] });
  };

  const isAlive = health?.status === 'ok' || health?.status === 'healthy';

  return (
    <header className="topbar">
      <span className="logo">ALPHAS</span>

      <select
        className="universe-select"
        value={selectedUniverse}
        onChange={(e) => handleUniverseChange(e.target.value)}
      >
        {universes?.map((u) => (
          <option key={u.key} value={u.key}>{u.display_name}</option>
        )) ?? <option value="SET100">SET100</option>}
      </select>

      <button className="scan-btn" onClick={handleScan}>
        ▶ RUN SCAN
      </button>

      <div className="topbar-right">
        <span className="clock">{clock}</span>
        <span className="health-dot" style={{ color: isAlive ? 'var(--col-buy)' : 'var(--col-red)' }}>
          ● {isAlive ? 'LIVE' : 'DOWN'}
        </span>
      </div>
    </header>
  );
}
