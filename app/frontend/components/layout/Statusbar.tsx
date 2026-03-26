import { useState, useEffect } from 'react';
import { useAppStore } from '../../store/useAppStore';
import { ttlSeconds, formatDuration } from '../../lib/format';

export function Statusbar() {
  const { regime, macro, rankings } = useAppStore();
  const [, setTick] = useState(0);

  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, []);

  const regimeTTL = regime ? formatDuration(Math.floor(ttlSeconds(regime.timestamp, 15))) : '—';
  const macroTTL = macro ? formatDuration(Math.floor(ttlSeconds(macro.timestamp, 30))) : '—';
  const rankTTL = rankings ? formatDuration(Math.floor(ttlSeconds(rankings.timestamp, 60))) : '—';

  const lastUpdated = rankings?.timestamp
    ? new Date(rankings.timestamp).toUTCString().slice(0, 25) + ' UTC'
    : regime?.timestamp
    ? new Date(regime.timestamp).toUTCString().slice(0, 25) + ' UTC'
    : '—';

  return (
    <footer className="statusbar">
      <span>Last updated: {lastUpdated}</span>
      <span className="dot">·</span>
      <span>Regime TTL: {regimeTTL}</span>
      <span className="dot">·</span>
      <span>Macro TTL: {macroTTL}</span>
      <span className="dot">·</span>
      <span>Rankings TTL: {rankTTL}</span>
    </footer>
  );
}
