/**
 * calculateHurst.ts
 *
 * Client-side Hurst Exponent via Rescaled Range (R/S) analysis.
 * Accepts an array of log-returns (not raw prices) for scale invariance.
 *
 * H < 0.45  → mean-reverting / sideways
 * H = 0.50  → random walk (geometric Brownian motion)
 * H > 0.55  → trending / persistent
 */

export type HurstRegime = 'sideways' | 'random' | 'trending';

export interface HurstResult {
  h: number;
  regime: HurstRegime;
}

/**
 * Compute a single Hurst Exponent for a log-return array using R/S analysis.
 * Returns 0.5 (random walk) when the series is too short or degenerate.
 */
export function hurstRS(logReturns: number[]): number {
  const n = logReturns.length;
  if (n < 8) return 0.5;

  const mean = logReturns.reduce((a, b) => a + b, 0) / n;
  const dev  = logReturns.map(x => x - mean);

  // Cumulative deviation series
  const cum: number[] = [];
  let acc = 0;
  for (const d of dev) {
    acc += d;
    cum.push(acc);
  }

  const R = Math.max(...cum) - Math.min(...cum);
  const variance = logReturns.reduce((a, x) => a + (x - mean) ** 2, 0) / n;
  const S = Math.sqrt(variance);

  if (S <= 0 || R <= 0) return 0.5;
  return Math.log(R / S) / Math.log(n);
}

/**
 * Convert raw prices to log-returns, then compute rolling Hurst over a window.
 * Returns the Hurst value and regime for the most recent window.
 */
export function calculateHurst(
  prices: number[],
  window = 100,
): HurstResult {
  if (prices.length < 2) return { h: 0.5, regime: 'random' };

  const logReturns = prices
    .slice(1)
    .map((p, i) => Math.log(p / prices[i]));

  const slice = logReturns.slice(-window);
  const h = hurstRS(slice);

  const regime: HurstRegime =
    h < 0.45 ? 'sideways' :
    h > 0.55 ? 'trending' :
    'random';

  return { h, regime };
}

/**
 * Compute a full rolling Hurst series from a price array.
 * Useful for sparkline rendering on the client side.
 */
export function rollingHurst(prices: number[], window = 100): number[] {
  if (prices.length < 2) return [];
  const logReturns = prices.slice(1).map((p, i) => Math.log(p / prices[i]));
  const result: number[] = [];
  for (let i = window; i <= logReturns.length; i++) {
    result.push(hurstRS(logReturns.slice(i - window, i)));
  }
  return result;
}
