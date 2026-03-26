export const fmt = {
  pct: (v: number | null) =>
    v == null ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`,
  float2: (v: number | null) =>
    v == null ? '—' : v.toFixed(2),
  int: (v: number | null) =>
    v == null ? '—' : Math.round(v).toString(),
  price: (v: number | null) =>
    v == null ? '—' : v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
  score: (v: number) => v.toFixed(1),
  z: (v: number | null) => v == null ? '—' : v.toFixed(2),
};

export function scoreBar(score: number, width = 10): string {
  const filled = Math.round((score / 100) * width);
  return '█'.repeat(filled) + '░'.repeat(width - filled);
}

export function scoreColor(score: number): string {
  if (score >= 70) return 'var(--col-buy)';
  if (score >= 50) return 'var(--col-amber)';
  return 'var(--col-red)';
}

export function riskColor(risk: number): string {
  if (risk <= 30) return 'var(--col-buy)';
  if (risk <= 45) return 'var(--col-cyan)';
  if (risk <= 60) return 'var(--col-amber)';
  if (risk <= 74) return '#FF6B00';
  return 'var(--col-red)';
}

export function signalColor(signal: string): string {
  const s = signal?.toUpperCase() ?? '';
  if (s.includes('SAFE') || s.includes('BULL') || s.includes('PASS')) return 'var(--col-buy)';
  if (s.includes('NEUTRAL') || s.includes('NORMAL')) return 'var(--col-dim)';
  if (s.includes('CAUTION') || s.includes('WARN')) return 'var(--col-amber)';
  if (s.includes('RISK') || s.includes('BEAR') || s.includes('FAIL')) return 'var(--col-red)';
  return 'var(--col-body)';
}

export function quadrantColor(quadrant: string): string {
  switch (quadrant?.toUpperCase()) {
    case 'GOLDILOCKS': return '#00FF87';
    case 'OVERHEAT': return '#FF8C00';
    case 'STAGFLATION': return '#FF3B30';
    case 'RECESSION_RISK': return '#FFD60A';
    default: return 'var(--col-body)';
  }
}

export function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

export function ttlSeconds(timestamp: string, ttlMinutes: number): number {
  const elapsed = (Date.now() - new Date(timestamp).getTime()) / 1000;
  return Math.max(0, ttlMinutes * 60 - elapsed);
}
