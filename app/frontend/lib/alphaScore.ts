/**
 * Client-side port of src/agents/calculator.py:generate_alpha_score
 * plus the Rank Score formula from app/backend/pipeline.py:analyze_ticker.
 *
 * Same tiered sub-scores as Python; weights are applied as the maximum
 * contribution per dimension. Total weight auto-normalises to 100 so the
 * final score stays on a 0-100 scale regardless of user-entered values.
 *
 * Beta penalty and sector macro adjustment match the Python implementation.
 */
import type { TickerRow } from '../types/api';

export interface AlphaWeights {
  moat: number;    // ROIC - WACC
  sloan: number;   // Earnings quality
  fcf: number;     // FCF / Net income
  altman: number;  // Altman Z
  sortino: number; // Risk-adjusted return
}

export interface RankWeights {
  alpha: number;
  signal: number;
  sector: number;
  rr: number;
}

export const DEFAULT_ALPHA_WEIGHTS: AlphaWeights = {
  moat: 30,
  sloan: 20,
  fcf: 10,
  altman: 20,
  sortino: 20,
};

export const DEFAULT_RANK_WEIGHTS: RankWeights = {
  alpha: 45,
  signal: 30,
  sector: 15,
  rr: 10,
};

/** Tiered 0-1 sub-score for ROIC-WACC moat. `moatPct` is in percentage points (e.g. 14.2). */
function moatSub(moatPct: number): number {
  if (moatPct > 10) return 1.0;
  if (moatPct > 5)  return 22 / 30;
  if (moatPct > 0)  return 12 / 30;
  return 0;
}

function sloanSub(sloan: number): number {
  if (sloan > -0.05 && sloan < 0.05)  return 1.0;
  if (sloan > -0.10 && sloan < 0.10)  return 14 / 20;
  if (sloan >= 0.10 && sloan < 0.20)  return 6 / 20;
  return 0;
}

function fcfSub(fcfQ: number): number {
  if (fcfQ > 1.0) return 1.0;
  if (fcfQ > 0.6) return 7 / 10;
  if (fcfQ > 0.3) return 3 / 10;
  return 0;
}

function altmanSub(z: number): number {
  if (z > 2.99) return 1.0;
  if (z > 1.81) return 10 / 20;
  return 0;
}

function sortinoSub(sortino: number): number {
  if (sortino > 2.5) return 1.0;
  if (sortino > 1.5) return 15 / 20;
  if (sortino > 1.0) return 9 / 20;
  if (sortino > 0.5) return 4 / 20;
  return 0;
}

export function computeAlpha(
  row: TickerRow,
  weights: AlphaWeights,
  compositeRisk: number,
): number {
  const totalW =
    weights.moat + weights.sloan + weights.fcf + weights.altman + weights.sortino;

  if (totalW <= 0) return 0;

  const weighted =
    moatSub(row.moat ?? 0)        * weights.moat +
    sloanSub(row.sloan ?? 0)      * weights.sloan +
    fcfSub(row.fcf_q ?? 0)        * weights.fcf +
    altmanSub(row.z ?? 0)         * weights.altman +
    sortinoSub(row.sortino ?? 0)  * weights.sortino;

  // Renormalise so the maximum possible weighted score is 100, regardless of
  // user-entered weight magnitudes. This keeps beta penalty / sector_adj on
  // the same 0-100 scale as the Python implementation.
  let score = weighted * (100 / totalW);

  // Beta penalty — regime-scaled, matches Python verbatim.
  const beta = row.beta ?? 1.0;
  const regimeMult = 1.0 + Math.max(0, (compositeRisk - 40) / 120);
  if (beta > 2.0)      score -= 15 * regimeMult;
  else if (beta > 1.5) score -= 10 * regimeMult;
  else if (beta > 1.3) score -= 5  * regimeMult;

  // Macro sector adjustment (already in points).
  score += row.sector_adj ?? 0;

  return Math.max(0, Math.min(100, Math.round(score * 10) / 10));
}

export function computeRankScore(
  row: TickerRow,
  alpha: number,
  weights: RankWeights,
): number {
  const totalW = weights.alpha + weights.signal + weights.sector + weights.rr;
  if (totalW <= 0) return 0;

  const rrScore = Math.min((row.rr / 3.0) * 100, 100);

  const weighted =
    alpha             * weights.alpha +
    row.signal_str    * weights.signal +
    row.sector_score  * weights.sector +
    rrScore           * weights.rr;

  return weighted / totalW;
}

export interface RecomputedRow extends TickerRow {
  /** True when the configured weights changed the score vs. the server value. */
  weights_modified: boolean;
}

export function recomputeRow(
  row: TickerRow,
  alphaW: AlphaWeights,
  rankW: RankWeights,
  compositeRisk: number,
): RecomputedRow {
  const newAlpha = computeAlpha(row, alphaW, compositeRisk);
  const newRank  = computeRankScore(row, newAlpha, rankW);

  // gate3 logic from pipeline.py: alpha >= 50 AND z > 1.81.
  // gate4 depends on signal/RR which are not affected by weights.
  const newGate3 = newAlpha >= 50 && (row.z ?? 0) > 1.81;

  let verdict: TickerRow['verdict'];
  if (newGate3 && row.gate4)      verdict = 'BUY';
  else if (newGate3)              verdict = 'FUND_ONLY';
  else if (row.gate4)             verdict = 'TECH_ONLY';
  else                            verdict = 'FAIL';

  return {
    ...row,
    alpha:      newAlpha,
    rank_score: newRank,
    gate3:      newGate3,
    verdict,
    weights_modified:
      Math.abs(newAlpha - row.alpha) > 0.05 ||
      Math.abs(newRank - row.rank_score) > 0.05,
  };
}

export function alphaWeightsEqualDefault(w: AlphaWeights): boolean {
  return (
    w.moat    === DEFAULT_ALPHA_WEIGHTS.moat &&
    w.sloan   === DEFAULT_ALPHA_WEIGHTS.sloan &&
    w.fcf     === DEFAULT_ALPHA_WEIGHTS.fcf &&
    w.altman  === DEFAULT_ALPHA_WEIGHTS.altman &&
    w.sortino === DEFAULT_ALPHA_WEIGHTS.sortino
  );
}

export function rankWeightsEqualDefault(w: RankWeights): boolean {
  return (
    w.alpha  === DEFAULT_RANK_WEIGHTS.alpha &&
    w.signal === DEFAULT_RANK_WEIGHTS.signal &&
    w.sector === DEFAULT_RANK_WEIGHTS.sector &&
    w.rr     === DEFAULT_RANK_WEIGHTS.rr
  );
}
