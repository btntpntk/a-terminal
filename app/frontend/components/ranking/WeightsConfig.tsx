import { useState } from 'react';
import { useAppStore } from '../../store/useAppStore';
import {
  DEFAULT_ALPHA_WEIGHTS,
  DEFAULT_RANK_WEIGHTS,
  type AlphaWeights,
  type RankWeights,
} from '../../lib/alphaScore';

interface Props {
  open: boolean;
  onClose: () => void;
}

interface Row<K extends string> {
  key: K;
  label: string;
  hint: string;
}

const ALPHA_ROWS: Row<keyof AlphaWeights>[] = [
  { key: 'moat',    label: 'Moat',    hint: 'ROIC − WACC spread' },
  { key: 'sloan',   label: 'Sloan',   hint: 'Earnings quality (accruals)' },
  { key: 'fcf',     label: 'FCF',     hint: 'Free cash flow / net income' },
  { key: 'altman',  label: 'Altman',  hint: 'Z-score (bankruptcy distance)' },
  { key: 'sortino', label: 'Sortino', hint: 'Downside risk-adj return' },
];

const RANK_ROWS: Row<keyof RankWeights>[] = [
  { key: 'alpha',  label: 'AlphaScore',     hint: 'Fundamental composite' },
  { key: 'signal', label: 'Signal Strength', hint: 'Technical entry signal' },
  { key: 'sector', label: 'Sector Score',    hint: 'Sector rotation rank' },
  { key: 'rr',     label: 'R:R',             hint: 'Reward-to-risk ratio' },
];

function sum(obj: AlphaWeights | RankWeights): number {
  return (Object.values(obj) as number[]).reduce((a, b) => a + b, 0);
}

export function WeightsConfig({ open, onClose }: Props) {
  const storeAlpha = useAppStore((s) => s.alphaWeights);
  const storeRank  = useAppStore((s) => s.rankWeights);
  const setAlpha   = useAppStore((s) => s.setAlphaWeights);
  const setRank    = useAppStore((s) => s.setRankWeights);
  const reset      = useAppStore((s) => s.resetWeights);

  // Local draft state — only commit on Apply, so the table doesn't re-sort mid-edit.
  const [draftAlpha, setDraftAlpha] = useState<AlphaWeights>(storeAlpha);
  const [draftRank,  setDraftRank]  = useState<RankWeights>(storeRank);

  if (!open) return null;

  const alphaTotal = sum(draftAlpha);
  const rankTotal  = sum(draftRank);

  const handleApply = () => {
    setAlpha(draftAlpha);
    setRank(draftRank);
    onClose();
  };

  const handleReset = () => {
    setDraftAlpha(DEFAULT_ALPHA_WEIGHTS);
    setDraftRank(DEFAULT_RANK_WEIGHTS);
    reset();
  };

  const handleCancel = () => {
    setDraftAlpha(storeAlpha);
    setDraftRank(storeRank);
    onClose();
  };

  const updAlpha = (k: keyof AlphaWeights, v: number) =>
    setDraftAlpha({ ...draftAlpha, [k]: Math.max(0, Math.min(100, v)) });

  const updRank = (k: keyof RankWeights, v: number) =>
    setDraftRank({ ...draftRank, [k]: Math.max(0, Math.min(100, v)) });

  return (
    <div className="wc-overlay" role="dialog" aria-modal="true" onClick={handleCancel}>
      <div className="wc-modal" onClick={(e) => e.stopPropagation()}>
        <div className="wc-header">
          <span className="wc-title">SCORE WEIGHTS</span>
          <button className="wc-close" onClick={handleCancel} aria-label="Close">✕</button>
        </div>

        <div className="wc-body">
          <Section
            title="ALPHASCORE — 5 indicators"
            subtitle="Per-indicator contribution. Auto-normalised to 100."
            total={alphaTotal}
          >
            {ALPHA_ROWS.map((r) => (
              <WeightRow
                key={r.key}
                label={r.label}
                hint={r.hint}
                value={draftAlpha[r.key]}
                defaultValue={DEFAULT_ALPHA_WEIGHTS[r.key]}
                onChange={(v) => updAlpha(r.key, v)}
              />
            ))}
          </Section>

          <Section
            title="RANK SCORE — 4 components"
            subtitle="How AlphaScore / Signal / Sector / R:R combine."
            total={rankTotal}
          >
            {RANK_ROWS.map((r) => (
              <WeightRow
                key={r.key}
                label={r.label}
                hint={r.hint}
                value={draftRank[r.key]}
                defaultValue={DEFAULT_RANK_WEIGHTS[r.key]}
                onChange={(v) => updRank(r.key, v)}
              />
            ))}
          </Section>
        </div>

        <div className="wc-footer">
          <button className="wc-btn wc-btn-ghost" onClick={handleReset}>RESET</button>
          <div style={{ flex: 1 }} />
          <button className="wc-btn wc-btn-ghost" onClick={handleCancel}>CANCEL</button>
          <button className="wc-btn wc-btn-primary" onClick={handleApply}>APPLY</button>
        </div>
      </div>
    </div>
  );
}

interface SectionProps {
  title:    string;
  subtitle: string;
  total:    number;
  children: React.ReactNode;
}
function Section({ title, subtitle, total, children }: SectionProps) {
  const totalColor = total === 0 ? 'var(--col-red)' : 'var(--col-amber)';
  return (
    <div className="wc-section">
      <div className="wc-section-head">
        <div>
          <div className="wc-section-title">{title}</div>
          <div className="wc-section-sub">{subtitle}</div>
        </div>
        <div className="wc-section-total">
          TOTAL <span style={{ color: totalColor, marginLeft: 4 }}>{total.toFixed(0)}</span>
        </div>
      </div>
      <div className="wc-rows">{children}</div>
    </div>
  );
}

interface WeightRowProps {
  label:        string;
  hint:         string;
  value:        number;
  defaultValue: number;
  onChange:     (v: number) => void;
}
function WeightRow({ label, hint, value, defaultValue, onChange }: WeightRowProps) {
  const isDefault = value === defaultValue;
  return (
    <label className="wc-row">
      <div className="wc-row-label">
        <span className="wc-row-name">{label}</span>
        <span className="wc-row-hint">{hint}</span>
      </div>
      <input
        type="range"
        min={0}
        max={100}
        step={1}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="wc-slider"
      />
      <input
        type="number"
        min={0}
        max={100}
        step={1}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="wc-num"
        style={{ color: isDefault ? 'var(--col-dim)' : 'var(--col-amber)' }}
      />
    </label>
  );
}
