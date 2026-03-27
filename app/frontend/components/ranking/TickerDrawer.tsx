import { useEffect } from 'react';
import type { TickerRow } from '../../types/api';
import { fmt, scoreBar, scoreColor, riskColor } from '../../lib/format';
import { usePriceHistory } from '../../hooks/useQueries';
import { PriceChart } from './PriceChart';

interface TickerDrawerProps {
  ticker: string;
  rows: TickerRow[];
  onClose: () => void;
}

export function TickerDrawer({ ticker, rows, onClose }: TickerDrawerProps) {
  const row = rows.find((r) => r.ticker === ticker);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  const { data: priceData, isLoading: priceLoading } = usePriceHistory(ticker);

  if (!row) return null;

  const scoreW = Math.round((row.rank_score / 100) * 20);
  const verdictColor = row.verdict === 'BUY' ? 'var(--col-buy)'
    : row.verdict === 'FUND_ONLY' ? 'var(--col-fund)'
    : row.verdict === 'TECH_ONLY' ? 'var(--col-tech)'
    : 'var(--col-red)';

  const KV = ({ label, val, color }: { label: string; val: string | React.ReactNode; color?: string }) => (
    <div className="drawer-kv">
      <span className="drawer-kv-label">{label}</span>
      <span className="drawer-kv-val" style={{ color: color ?? 'var(--col-body)' }}>{val}</span>
    </div>
  );

  return (
    <div className="drawer-overlay" onClick={onClose}>
      <div className="drawer" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">

        {/* ── Header ── */}
        <div className="drawer-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{ color: 'var(--col-amber)', fontSize: '18px', fontWeight: 600 }}>{row.ticker}</span>
            <span className="pill-tech" style={{ fontSize: '10px' }}>{row.sector}</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span className="score-bar" style={{ color: scoreColor(row.rank_score), fontSize: '13px', letterSpacing: '-1px' }}>
              {'█'.repeat(scoreW)}{'░'.repeat(20 - scoreW)}
            </span>
            <span style={{ color: scoreColor(row.rank_score), fontSize: '16px', fontWeight: 600 }}>{fmt.score(row.rank_score)}</span>
            <span className={row.verdict === 'BUY' ? 'pill-buy' : row.verdict === 'FUND_ONLY' ? 'pill-fund' : row.verdict === 'TECH_ONLY' ? 'pill-tech' : 'pill-fail'}>
              {row.verdict.replace('_ONLY', '')}
            </span>
            <button className="close-btn" onClick={onClose} aria-label="Close">✕</button>
          </div>
        </div>

        {/* ── Chart ── */}
        <div style={{ borderBottom: '1px solid var(--col-border)' }}>
          {priceLoading && (
            <div style={{ height: 220, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--col-dim)', fontSize: '11px' }}>
              Loading chart…
            </div>
          )}
          {!priceLoading && priceData?.bars?.length ? (
            <PriceChart bars={priceData.bars} height={340} />
          ) : !priceLoading && (
            <div style={{ height: 80, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--col-dim)', fontSize: '11px' }}>
              No price data
            </div>
          )}
        </div>

        {/* ── News ── */}
        <div style={{ padding: '10px 16px', borderBottom: '1px solid var(--col-border)' }}>
          <div className="drawer-section-title" style={{ padding: 0, marginBottom: 8 }}>NEWS</div>
          <div style={{ color: 'var(--col-dim)', fontSize: '11px', fontStyle: 'italic' }}>
            No news feed connected — backend integration pending.
          </div>
        </div>

        {/* ── Two-column body: Fundamentals | Technical ── */}
        <div style={{ display: 'flex', flex: 1, minHeight: 0, overflow: 'hidden' }}>

          {/* Fundamentals */}
          <div style={{ flex: 1, borderRight: '1px solid var(--col-border)', overflowY: 'auto' }}>
            <div className="drawer-section-title">FUNDAMENTALS</div>
            <div style={{ padding: '0 16px' }}>
              <KV label="Alpha Score"  val={fmt.score(row.alpha)} />
              <KV label="ROIC"         val={row.roic != null ? `${row.roic.toFixed(1)}%` : '—'} />
              <KV label="WACC"         val={row.wacc != null ? `${row.wacc.toFixed(1)}%` : '—'} />
              <KV label="Moat"         val={fmt.float2(row.moat)}   color={(row.moat ?? 0) >= 0 ? 'var(--col-buy)' : 'var(--col-red)'} />
              <KV label="Altman Z"     val={fmt.z(row.z)}           color={(row.z ?? 99) < 1.81 ? 'var(--col-red)' : 'var(--col-body)'} />
              <KV label="Sloan"        val={fmt.float2(row.sloan)}  color={(row.sloan ?? 0) > 0.1 ? 'var(--col-red)' : 'var(--col-body)'} />
              <KV label="FCF Quality"  val={fmt.float2(row.fcf_q)} />
              <KV label="CVaR"         val={row.cvar != null ? `${row.cvar.toFixed(1)}%` : '—'} color="var(--col-red)" />
              <KV label="Sortino"      val={fmt.float2(row.sortino)} />
              <KV label="Beta"         val={fmt.float2(row.beta)} />
              <KV label="Asset Turn"   val={fmt.float2(row.a_turn)} />
              <KV label="CCC (days)"   val={fmt.float2(row.ccc)} />
              <KV label="Sector Adj"   val={`${row.sector_adj >= 0 ? '+' : ''}${row.sector_adj}`} color={row.sector_adj >= 0 ? 'var(--col-amber)' : 'var(--col-red)'} />
              <KV label="Sector Score" val={fmt.score(row.sector_score)} />
            </div>
          </div>

          {/* Technical */}
          <div style={{ flex: 1, overflowY: 'auto' }}>
            <div className="drawer-section-title">TECHNICAL</div>
            <div style={{ padding: '0 16px' }}>
              <KV label="Strategy"     val={row.strategy}           color="var(--col-amber)" />
              <KV label="Regime Fit"   val={row.regime_fit ?? '—'} />
              <KV label="Signal Str."  val={`${row.signal_str}`} />
              <KV label="R:R Ratio"    val={`${row.rr.toFixed(1)}x`} />
              <KV label="Entry"        val={fmt.price(row.entry)}   color="var(--col-amber)" />
              <KV label="ATR"          val={fmt.float2(row.atr)} />
              <KV label="Take Profit"  val={fmt.price(row.tp)}      color="var(--col-buy)" />
              <KV label="Stop Loss"    val={fmt.price(row.sl)}       color="var(--col-red)" />
              <KV label="Gate 3 (Fund)" val={row.gate3 ? '✓' : '✗'} color={row.gate3 ? 'var(--col-buy)' : 'var(--col-red)'} />
              <KV label="Gate 4 (Tech)" val={row.gate4 ? '✓' : '✗'} color={row.gate4 ? 'var(--col-buy)' : 'var(--col-red)'} />
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}
