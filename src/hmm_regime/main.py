"""
src/hmm_regime/main.py

End-to-end orchestrator for the HMM Market Regime Detector.

Usage
-----
    python -m src.hmm_regime.main
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd

from src.hmm_regime.data_loader import load_raw_data
from src.hmm_regime.features import build_features
from src.hmm_regime.walk_forward import bias_audit_summary, run_walk_forward
from src.hmm_regime.evaluate import plot_regimes, plot_posteriors, print_regime_stats


SPY_TICKER      = "SPY"
DATA_START      = "2000-01-01"
TRAIN_END       = "2010-12-31"
TEST_START      = "2011-01-01"
RETRAIN_FREQ    = 21
N_COMPONENTS    = 3
COVARIANCE_TYPE = "diag"
N_ITER          = 200
N_RESTARTS      = 5
RANDOM_STATE    = 42
SAVE_PLOTS      = False


def main() -> pd.DataFrame:
    print("[1/5] Loading raw data …")
    raw = load_raw_data(spy_ticker=SPY_TICKER, start=DATA_START)
    print(f"      Raw data: {raw.index[0].date()} → {raw.index[-1].date()} ({len(raw)} rows)")

    print("[2/5] Building features …")
    features = build_features(raw)
    print(f"      Features: {features.index[0].date()} → {features.index[-1].date()} "
          f"({len(features)} rows, cols={list(features.columns)})")

    print("[3/5] Running walk-forward HMM …")
    result = run_walk_forward(
        df_features       = features,
        train_end         = TRAIN_END,
        test_start        = TEST_START,
        retrain_freq_days = RETRAIN_FREQ,
        n_components      = N_COMPONENTS,
        covariance_type   = COVARIANCE_TYPE,
        n_iter            = N_ITER,
        n_restarts        = N_RESTARTS,
        random_state      = RANDOM_STATE,
    )
    print(f"      Walk-forward complete: {len(result)} test observations.")

    print("[4/5] Computing regime statistics …")
    print_regime_stats(result, raw["spy_close"])

    print("[5/5] Generating plots …")
    regime_png    = "regime_plot.png"    if SAVE_PLOTS else None
    posterior_png = "posterior_plot.png" if SAVE_PLOTS else None
    plot_regimes(result, raw["spy_close"], save_path=regime_png)
    plot_posteriors(result, save_path=posterior_png)

    print(bias_audit_summary(result))

    return result


if __name__ == "__main__":
    main()
