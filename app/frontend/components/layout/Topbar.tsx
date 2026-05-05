import { useState, useEffect } from 'react';
import { useHealth } from '../../hooks/useQueries';

export function Topbar() {
  const [clock, setClock] = useState('');
  const { data: health } = useHealth();

  useEffect(() => {
    const tick = () => {
      const now = new Date();
      const bangkokTime = now.toLocaleTimeString('en-GB', {
        timeZone: 'Asia/Bangkok',
        hour12: false,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      });
      setClock(bangkokTime + ' BKK');
    };

    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  const isAlive = health?.status === 'ok' || health?.status === 'healthy';

  return (
    <header className="topbar">
      <span className="logo">TERMINAL</span>

      <div className="topbar-right">
        <span className="clock">{clock}</span>
        <span className="health-dot" style={{ color: isAlive ? 'var(--col-buy)' : 'var(--col-red)' }}>
          ● {isAlive ? 'LIVE' : 'DOWN'}
        </span>
      </div>
    </header>
  );
}
