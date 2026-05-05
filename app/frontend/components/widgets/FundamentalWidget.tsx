import { useQueryClient } from '@tanstack/react-query';
import { useActiveTab } from '../../hooks/useActiveTab';
import { useTickerFundamentals } from '../../hooks/useQueries';
import type { FundamentalSignal, MoatRating, AltmanZone } from '../../types/api';

// eslint-disable-next-line @typescript-eslint/no-unused-vars
interface Props { tabId: string }

const SIGNAL_META: Record<FundamentalSignal, { label: string; color: string }> = {
  STRONG_BUY:  { label: 'STRONG BUY',  color: 'var(--col-emerald)' },
  BUY:         { label: 'BUY',          color: 'var(--col-cyan)'    },
  NEUTRAL:     { label: 'NEUTRAL',      color: 'var(--col-body)'    },
  SELL:        { label: 'SELL',         color: 'var(--col-amber)'   },
  STRONG_SELL: { label: 'STRONG SELL',  color: 'var(--col-crimson)' },
};

const MOAT_META: Record<MoatRating, { color: string }> = {
  WIDE:     { color: 'var(--col-emerald)' },
  NARROW:   { color: 'var(--col-cyan)'    },
  MARGINAL: { color: 'var(--col-amber)'   },
  NONE:     { color: 'var(--col-crimson)' },
};

const ZONE_META: Record<AltmanZone, { color: string }> = {
  SAFE:     { color: 'var(--col-emerald)' },
  GREY:     { color: 'var(--col-amber)'   },
  DISTRESS: { color: 'var(--col-crimson)' },
};

function pct(v: number | null): string {
  return v != null ? `${(v * 100).toFixed(1)}%` : '—';
}
function num(v: number | null, dp = 2): string {
  return v != null ? v.toFixed(dp) : '—';
}

function ScoreGauge({ score }: { score: number }) {
  const fill = Math.min(100, Math.max(0, score));
  const color =
    score >= 75 ? 'var(--col-emerald)' :
    score >= 55 ? 'var(--col-cyan)'    :
    score >= 40 ? 'var(--col-body)'    :
    score >= 25 ? 'var(--col-amber)'   :
                  'var(--col-crimson)';
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
      <div style={{ fontSize: 36, fontWeight: 800, color, letterSpacing: '-2px', lineHeight: 1 }}>
        {score.toFixed(0)}
      </div>
      <div style={{ fontSize: 9, color: 'var(--col-dim)' }}>/100 ALPHA</div>
      <div style={{ width: 80, height: 5, background: 'var(--col-border)', borderRadius: 1, overflow: 'hidden' }}>
        <div style={{ width: `${fill}%`, height: '100%', background: color, transition: 'width 0.4s ease' }} />
      </div>
    </div>
  );
}

function MetricRow({ label, value, color, sub }: {
  label: string; value: string; color?: string; sub?: string;
}) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '5px 0', borderBottom: '1px solid var(--col-border)',
    }}>
      <div>
        <span style={{ fontSize: 9, color: 'var(--col-slate)', letterSpacing: '0.5px' }}>{label}</span>
        {sub && <span style={{ fontSize: 8, color: 'var(--col-dim)', marginLeft: 5 }}>{sub}</span>}
      </div>
      <span style={{ fontSize: 11, fontWeight: 600, color: color ?? 'var(--col-body)', fontVariantNumeric: 'tabular-nums' }}>
        {value}
      </span>
    </div>
  );
}

function Badge({ label, color }: { label: string; color: string }) {
  return (
    <span style={{
      fontSize: 8, fontWeight: 700, letterSpacing: '0.5px', padding: '2px 6px',
      border: `1px solid ${color}`, color,
    }}>{label}</span>
  );
}

export function FundamentalWidget({ tabId: _ }: Props) {
  const { activeTicker } = useActiveTab();
  const qc = useQueryClient();
  const { data, isLoading, error } = useTickerFundamentals(activeTicker);

  const signal = data ? SIGNAL_META[data.signal] : null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* Toolbar */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, padding: '5px 12px',
        background: 'var(--col-elevated)', borderBottom: '1px solid var(--col-border)', flexShrink: 0,
      }}>
        <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--col-body)', letterSpacing: '0.5px' }}>
          {activeTicker}
        </span>
        <span style={{ fontSize: 9, color: 'var(--col-slate)', letterSpacing: '1px', flex: 1 }}>
          · STAGE 3 FUNDAMENTALS
        </span>
        <button
          onClick={() => qc.invalidateQueries({ queryKey: ['ticker-fundamentals', activeTicker] })}
          style={{ background: 'none', border: 'none', color: 'var(--col-dim)', cursor: 'pointer', fontSize: 13 }}
          title="Refresh"
        >↺</button>
      </div>

      {/* Body */}
      <div style={{ flex: 1, overflow: 'auto', padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 10 }}>
        {isLoading && <div className="widget-loading">Computing fundamentals for {activeTicker}…</div>}
        {(error || (!isLoading && !data)) && (
          <div className="widget-error">Fundamentals unavailable — {activeTicker}</div>
        )}

        {data && signal && (
          <>
            {/* Alpha score + badges */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
              <ScoreGauge score={data.alpha_score} />
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}>
                <Badge label={signal.label} color={signal.color} />
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  <Badge label={`MOAT: ${data.moat}`}       color={MOAT_META[data.moat].color} />
                  <Badge label={`Z: ${data.altman_zone}`}   color={ZONE_META[data.altman_zone].color} />
                </div>
              </div>
            </div>

            {/* ROIC vs WACC */}
            <div style={{
              background: 'var(--col-elevated)', border: '1px solid var(--col-border)', padding: '8px 10px',
            }}>
              <div style={{ fontSize: 8, color: 'var(--col-slate)', letterSpacing: '1px', marginBottom: 6 }}>
                RETURN ON CAPITAL
              </div>
              <div style={{ display: 'flex', gap: 16 }}>
                {[
                  {
                    lbl: 'ROIC', val: pct(data.roic),
                    color: (data.roic ?? 0) > (data.wacc ?? 0) ? 'var(--col-emerald)' : 'var(--col-crimson)',
                  },
                  { lbl: 'WACC', val: pct(data.wacc), color: 'var(--col-body)' },
                  {
                    lbl: 'SPREAD',
                    val: (data.roic_wacc_spread ?? 0) >= 0
                      ? `+${pct(data.roic_wacc_spread)}`
                      : pct(data.roic_wacc_spread),
                    color: (data.roic_wacc_spread ?? 0) > 0 ? 'var(--col-emerald)' : 'var(--col-crimson)',
                  },
                ].map(({ lbl, val, color }) => (
                  <div key={lbl}>
                    <div style={{ fontSize: 8, color: 'var(--col-dim)', marginBottom: 2 }}>{lbl}</div>
                    <div style={{ fontSize: 14, fontWeight: 700, color, fontVariantNumeric: 'tabular-nums' }}>{val}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* Quality metrics */}
            <div>
              <div style={{ fontSize: 8, color: 'var(--col-slate)', letterSpacing: '1px', marginBottom: 4 }}>QUALITY</div>
              <MetricRow
                label="Sloan Ratio" sub="accrual quality"
                value={num(data.sloan_ratio, 3)}
                color={Math.abs(data.sloan_ratio ?? 0) < 0.1 ? 'var(--col-emerald)' :
                       Math.abs(data.sloan_ratio ?? 0) < 0.2 ? 'var(--col-amber)'   : 'var(--col-crimson)'}
              />
              <MetricRow
                label="FCF Quality" sub="FCF / Net Income"
                value={num(data.fcf_quality, 2)}
                color={(data.fcf_quality ?? 0) >= 0.8 ? 'var(--col-emerald)' :
                       (data.fcf_quality ?? 0) >= 0.5 ? 'var(--col-amber)'   : 'var(--col-crimson)'}
              />
              <MetricRow
                label="Altman Z" sub={data.altman_zone}
                value={num(data.altman_z, 2)}
                color={ZONE_META[data.altman_zone].color}
              />
            </div>

            {/* Operational */}
            <div>
              <div style={{ fontSize: 8, color: 'var(--col-slate)', letterSpacing: '1px', marginBottom: 4 }}>OPERATIONAL</div>
              <MetricRow label="Asset Turnover"         value={num(data.asset_turnover, 2)} />
              <MetricRow label="Cash Conversion Cycle"  sub="days"
                value={data.cash_conversion_cycle != null ? data.cash_conversion_cycle.toFixed(0) : '—'} />
            </div>

            {/* Risk */}
            <div>
              <div style={{ fontSize: 8, color: 'var(--col-slate)', letterSpacing: '1px', marginBottom: 4 }}>RISK</div>
              <MetricRow
                label="Sortino Ratio"
                value={num(data.sortino, 2)}
                color={(data.sortino ?? 0) >= 1 ? 'var(--col-emerald)' :
                       (data.sortino ?? 0) >= 0 ? 'var(--col-amber)'   : 'var(--col-crimson)'}
              />
              <MetricRow label="Beta" value={num(data.beta, 2)} />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
