import { useQueryClient } from '@tanstack/react-query';
import { useMarketEntropy } from '../../hooks/useQueries';

// eslint-disable-next-line @typescript-eslint/no-unused-vars
interface Props { tabId: string }

const TICKERS = ['^SET.BK', '^GSPC', '^VIX'] as const;
type Ticker = typeof TICKERS[number];

function EntropyBar({ normalized }: { normalized: number }) {
  const pct   = Math.min(100, Math.round(normalized * 100));
  const color = normalized < 0.50
    ? 'var(--col-emerald)'
    : normalized < 0.75
    ? 'var(--col-amber)'
    : 'var(--col-crimson)';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{ flex: 1, height: 6, background: 'var(--col-border)', borderRadius: 1, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color, transition: 'width 0.4s ease' }} />
      </div>
      <span style={{ fontSize: 10, color, minWidth: 28, textAlign: 'right', fontWeight: 600 }}>
        {pct}%
      </span>
    </div>
  );
}

function MiniSparkline({ series }: { series: Array<{ normalized: number }> }) {
  if (series.length < 2) return null;
  const vals  = series.map(s => s.normalized);
  const min   = Math.min(...vals);
  const max   = Math.max(...vals);
  const range = max - min || 0.001;
  const W = 100, H = 28;
  const pts = vals.map((v, i) => {
    const x = (i / (vals.length - 1)) * W;
    const y = H - ((v - min) / range) * (H - 2) - 1;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  return (
    <svg width={W} height={H} style={{ display: 'block', overflow: 'visible', flexShrink: 0 }}>
      <line x1="0" y1={H / 2} x2={W} y2={H / 2} stroke="var(--col-border)" strokeWidth="0.5" strokeDasharray="2,2" />
      <polyline points={pts} fill="none" stroke="var(--col-amber)" strokeWidth="1.2" opacity="0.75" />
    </svg>
  );
}

function EntropyPanel({ ticker }: { ticker: Ticker }) {
  const { data, isLoading, error } = useMarketEntropy(ticker, 30);

  if (isLoading) return (
    <div style={{ padding: '8px 12px', color: 'var(--col-dim)', fontSize: 10, borderBottom: '1px solid var(--col-border)' }}>
      Loading {ticker}…
    </div>
  );
  if (error || !data) return (
    <div style={{ padding: '8px 12px', color: 'var(--col-crimson)', fontSize: 10, borderBottom: '1px solid var(--col-border)' }}>
      Unavailable — {ticker}
    </div>
  );

  const regimeColor = data.regime === 'LOW NOISE'
    ? 'var(--col-emerald)'
    : data.regime === 'MODERATE'
    ? 'var(--col-amber)'
    : 'var(--col-crimson)';

  return (
    <div style={{ padding: '10px 12px', borderBottom: '1px solid var(--col-border)', display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: 10, fontWeight: 600, color: 'var(--col-slate)', letterSpacing: '0.8px' }}>{ticker}</span>
        <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: '0.5px', color: regimeColor }}>{data.regime}</span>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 4 }}>
          <span style={{ fontSize: 28, fontWeight: 700, letterSpacing: '-1.5px', color: regimeColor, lineHeight: 1 }}>
            {(data.normalized_entropy * 100).toFixed(0)}
          </span>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <span style={{ fontSize: 9, color: 'var(--col-dim)' }}>/100</span>
            <span style={{ fontSize: 9, color: 'var(--col-dim)' }}>H={data.current_entropy.toFixed(2)}</span>
          </div>
        </div>
        <div style={{ marginLeft: 'auto' }}>
          <MiniSparkline series={data.series} />
        </div>
      </div>

      <EntropyBar normalized={data.normalized_entropy} />

      <div style={{ fontSize: 9, color: 'var(--col-dim)', fontStyle: 'italic' }}>{data.interpretation}</div>
    </div>
  );
}

export function ShannonEntropyWidget({ tabId: _ }: Props) {
  const qc = useQueryClient();
  const refresh = () => TICKERS.forEach(t => qc.invalidateQueries({ queryKey: ['market-entropy', t, 30] }));

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'auto' }}>
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '5px 12px', background: 'var(--col-elevated)', borderBottom: '1px solid var(--col-border)',
        flexShrink: 0,
      }}>
        <span style={{ fontSize: 9, color: 'var(--col-slate)', letterSpacing: '1px' }}>
          30-DAY RETURN DISTRIBUTION · H = -Σ p log₂p
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <span className="live-dot" />
          <span style={{ fontSize: 9, color: 'var(--col-emerald)' }}>LIVE · 60s</span>
        </span>
        <button onClick={refresh} style={{ background: 'none', border: 'none', color: 'var(--col-dim)', cursor: 'pointer', fontSize: 13 }} title="Refresh">↺</button>
      </div>

      {TICKERS.map(t => <EntropyPanel key={t} ticker={t} />)}

      <div style={{ padding: '8px 12px', display: 'flex', gap: 14, flexWrap: 'wrap', flexShrink: 0 }}>
        {([
          { label: 'LOW NOISE <50%',  color: 'var(--col-emerald)' },
          { label: 'MODERATE 50–75%', color: 'var(--col-amber)'  },
          { label: 'HIGH NOISE >75%', color: 'var(--col-crimson)' },
        ] as const).map(({ label, color }) => (
          <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <div style={{ width: 7, height: 7, background: color, borderRadius: 1, flexShrink: 0 }} />
            <span style={{ fontSize: 9, color: 'var(--col-dim)' }}>{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
