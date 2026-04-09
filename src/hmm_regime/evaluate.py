"""
src/hmm_regime/evaluate.py

Visualization and statistics for HMM walk-forward output.

Functions
---------
plot_regimes(result_df, spy_close)
    Color-coded regime bands overlaid on SPY price series.

plot_posteriors(result_df)
    Posterior probability time series for all 3 states.

compute_regime_stats(result_df, spy_close) -> pd.DataFrame
    Per-regime: avg duration, frequency, annualized return, annualized vol.

print_regime_stats(result_df, spy_close)
    Pretty-print the stats table.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

try:
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    _HAS_MPL = True
except ImportError:
    _HAS_MPL = False

from .hmm_model import REGIME_COLORS, REGIME_NAMES


# ── Plotting ──────────────────────────────────────────────────────────────────

def plot_regimes(
    result_df: pd.DataFrame,
    spy_close: pd.Series,
    title: str = "HMM Market Regime — Walk-Forward (SPY)",
    save_path: str | None = None,
) -> None:
    """
    Plot SPY price with color-coded regime background bands.

    Parameters
    ----------
    result_df : pd.DataFrame
        Output of walk_forward.run_walk_forward().
    spy_close : pd.Series
        Raw SPY close prices (index = DatetimeIndex).
    save_path : str | None
        If provided, save figure to this path instead of showing.
    """
    if not _HAS_MPL:
        print("[evaluate] matplotlib not available — skipping plot.")
        return

    spy_aligned = spy_close.reindex(result_df.index).ffill()

    fig, ax = plt.subplots(figsize=(16, 6))
    ax.set_yscale("log")

    # Draw colored background spans per regime change
    prev_regime = None
    span_start  = None

    dates = list(result_df.index)
    regimes = list(result_df["regime"])

    for i, (date, regime) in enumerate(zip(dates, regimes)):
        if regime != prev_regime:
            if prev_regime is not None:
                ax.axvspan(span_start, date, alpha=0.25,
                           color=REGIME_COLORS[prev_regime], lw=0)
            span_start  = date
            prev_regime = regime

    # Close the last span
    if span_start is not None:
        ax.axvspan(span_start, dates[-1], alpha=0.25,
                   color=REGIME_COLORS[prev_regime], lw=0)

    # Overlay SPY price
    ax.plot(spy_aligned.index, spy_aligned.values, color="#1e293b", lw=1.2, label="SPY")

    # Legend
    patches = [
        mpatches.Patch(color=REGIME_COLORS[r], alpha=0.5, label=r.capitalize())
        for r in REGIME_NAMES
    ]
    ax.legend(handles=patches + [
        plt.Line2D([0], [0], color="#1e293b", lw=1.2, label="SPY")
    ], loc="upper left")

    ax.set_title(title)
    ax.set_xlabel("Date")
    ax.set_ylabel("SPY (log scale)")
    ax.grid(alpha=0.3)
    fig.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150)
        print(f"[evaluate] Regime plot saved to {save_path}")
    else:
        plt.show()

    plt.close(fig)


def plot_posteriors(
    result_df: pd.DataFrame,
    title: str = "HMM Posterior State Probabilities",
    save_path: str | None = None,
) -> None:
    """
    Plot posterior probability time series for all 3 states.
    """
    if not _HAS_MPL:
        print("[evaluate] matplotlib not available — skipping plot.")
        return

    fig, axes = plt.subplots(3, 1, figsize=(16, 8), sharex=True)
    prob_cols  = ["p_bear", "p_sideways", "p_bull"]
    labels     = ["Bear", "Sideways", "Bull"]
    colors     = [REGIME_COLORS["bear"], REGIME_COLORS["sideways"], REGIME_COLORS["bull"]]

    for ax, col, label, color in zip(axes, prob_cols, labels, colors):
        ax.fill_between(result_df.index, result_df[col], alpha=0.6, color=color)
        ax.plot(result_df.index, result_df[col], color=color, lw=0.8)
        ax.set_ylabel(label, fontsize=9)
        ax.set_ylim(0, 1)
        ax.grid(alpha=0.3)

    axes[0].set_title(title)
    axes[-1].set_xlabel("Date")
    fig.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150)
        print(f"[evaluate] Posterior plot saved to {save_path}")
    else:
        plt.show()

    plt.close(fig)


# ── Statistics ────────────────────────────────────────────────────────────────

def compute_regime_stats(
    result_df: pd.DataFrame,
    spy_close: pd.Series,
) -> pd.DataFrame:
    """
    Compute per-regime performance statistics.

    Returns
    -------
    pd.DataFrame
        Index: regime names; columns: frequency_pct, avg_duration_days,
        ann_return_pct, ann_vol_pct.
    """
    spy_aligned = spy_close.reindex(result_df.index).ffill()
    daily_ret   = spy_aligned.pct_change()

    rows = {}
    total_days = len(result_df)

    for regime in REGIME_NAMES:
        mask = result_df["regime"] == regime
        n_days = mask.sum()

        if n_days == 0:
            rows[regime] = {
                "frequency_pct":    0.0,
                "avg_duration_days": 0.0,
                "ann_return_pct":   np.nan,
                "ann_vol_pct":      np.nan,
            }
            continue

        # Duration: compute run-length encoding
        durations = []
        run = 0
        for v in mask:
            if v:
                run += 1
            else:
                if run > 0:
                    durations.append(run)
                    run = 0
        if run > 0:
            durations.append(run)

        regime_rets = daily_ret[mask].dropna()
        ann_ret = (1 + regime_rets.mean()) ** 252 - 1
        ann_vol = regime_rets.std() * np.sqrt(252)

        rows[regime] = {
            "frequency_pct":     round(100 * n_days / total_days, 1),
            "avg_duration_days": round(np.mean(durations), 1) if durations else 0.0,
            "ann_return_pct":    round(100 * ann_ret, 2),
            "ann_vol_pct":       round(100 * ann_vol, 2),
        }

    return pd.DataFrame(rows).T.loc[REGIME_NAMES]


def print_regime_stats(
    result_df: pd.DataFrame,
    spy_close: pd.Series,
) -> None:
    """Pretty-print regime statistics."""
    stats = compute_regime_stats(result_df, spy_close)
    print("\n" + "=" * 65)
    print("  HMM REGIME STATISTICS")
    print("=" * 65)
    print(f"  {'Regime':<12} {'Freq%':>7} {'AvgDur':>9} {'AnnRet%':>10} {'AnnVol%':>10}")
    print("  " + "-" * 52)
    for regime, row in stats.iterrows():
        print(
            f"  {regime:<12} {row['frequency_pct']:>7.1f} "
            f"{row['avg_duration_days']:>9.1f} "
            f"{row['ann_return_pct']:>10.2f} "
            f"{row['ann_vol_pct']:>10.2f}"
        )
    print("=" * 65 + "\n")
