import numpy as np
import pandas as pd

from .data_loader import load_prices
from .features import compute_features
from .walk_forward import run_walk_forward


def _compute_regime_stats(wf: pd.DataFrame, prices: pd.DataFrame) -> dict:
    log_ret = np.log(prices["Close"] / prices["Close"].shift(1)).reindex(wf.index)
    result = {}

    for regime in ("bull", "sideways", "bear", "crash"):
        mask = wf["regime"] == regime
        n = int(mask.sum())
        freq_pct = 100.0 * n / len(wf) if len(wf) > 0 else 0.0

        spans: list[int] = []
        span_len = 0
        for v in mask:
            if v:
                span_len += 1
            elif span_len > 0:
                spans.append(span_len)
                span_len = 0
        if span_len > 0:
            spans.append(span_len)
        avg_dur = float(np.mean(spans)) if spans else 0.0

        regime_rets = log_ret[mask].dropna()
        if len(regime_rets) > 1:
            ann_return_pct = float(regime_rets.mean() * 252 * 100)
            ann_vol_pct    = float(regime_rets.std() * np.sqrt(252) * 100)
        else:
            ann_return_pct = 0.0
            ann_vol_pct    = 0.0

        result[regime] = {
            "frequency_pct":    round(freq_pct, 4),
            "avg_duration_days": round(avg_dur, 4),
            "ann_return_pct":   round(ann_return_pct, 4),
            "ann_vol_pct":      round(ann_vol_pct, 4),
        }

    return result


def run_hmm_pipeline(ticker: str, start: str, train_end: str, test_start: str) -> dict:
    prices   = load_prices(ticker, start)
    features = compute_features(prices)
    wf       = run_walk_forward(features, train_end)

    test_start_dt = pd.Timestamp(test_start)
    wf_test = wf[wf.index >= test_start_dt]

    if wf_test.empty:
        raise ValueError("No walk-forward results in the test window")

    close_aligned = prices["Close"].reindex(wf_test.index)

    series = [
        {
            "date":       date.strftime("%Y-%m-%d"),
            "regime":     row["regime"],
            "p_bull":     float(row["p_bull"]),
            "p_sideways": float(row["p_sideways"]),
            "p_bear":     float(row["p_bear"]),
            "p_crash":    float(row["p_crash"]),
            "close":      float(close_aligned.loc[date]) if not pd.isna(close_aligned.loc[date]) else None,
        }
        for date, row in wf_test.iterrows()
    ]

    last = wf_test.iloc[-1]
    regime_stats = _compute_regime_stats(wf_test, prices)

    return {
        "ticker":         ticker,
        "current_regime": last["regime"],
        "current_p_bull": float(last["p_bull"]),
        "current_p_side": float(last["p_sideways"]),
        "current_p_bear": float(last["p_bear"]),
        "current_p_crash": float(last["p_crash"]),
        "train_end":      train_end,
        "test_start":     test_start,
        "n_observations": len(wf_test),
        "regime_stats":   regime_stats,
        "series":         series,
    }
