"""
src/hmm_regime/tests/test_no_lookahead.py

Automated lookahead bias unit tests for the HMM regime detector.

Run with:
    pytest src/hmm_regime/tests/test_no_lookahead.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parents[4]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.hmm_regime.features import build_features
from src.hmm_regime.hmm_model import RegimeHMM
from src.hmm_regime.normalizer import WalkForwardScaler
from src.hmm_regime.walk_forward import run_walk_forward


# ── Shared fixtures ───────────────────────────────────────────────────────────

def _make_raw_df(n: int = 800, seed: int = 0) -> pd.DataFrame:
    """Synthetic DataFrame that mimics data_loader output columns."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2000-01-03", periods=n)

    log_rets  = rng.normal(0.0003, 0.012, size=n)
    spy_close = 100 * np.exp(np.cumsum(log_rets))
    vix       = np.clip(18 + rng.normal(0, 4, size=n).cumsum() * 0.05, 8, 80)

    return pd.DataFrame(
        {"spy_close": spy_close, "vix": vix},
        index=dates,
    )


def _make_features(n: int = 800) -> pd.DataFrame:
    return build_features(_make_raw_df(n))


# ── Test 1: Feature lookahead ─────────────────────────────────────────────────

class TestNoFutureDataInFeatures:
    """At time t, feature value must depend only on data[0 : t-1]."""

    def test_ret_5d_uses_shifted_returns(self):
        raw = _make_raw_df(300)
        spike_idx = 100

        feat_base = build_features(raw)

        raw_spiked = raw.copy()
        raw_spiked.iloc[spike_idx, raw_spiked.columns.get_loc("spy_close")] *= 10.0
        feat_spiked = build_features(raw_spiked)

        spike_date = raw_spiked.index[spike_idx]

        assert feat_base.loc[spike_date, "ret_5d"] == pytest.approx(
            feat_spiked.loc[spike_date, "ret_5d"], rel=1e-6
        ), "ret_5d at spike date should equal baseline — spike not yet observed"

    def test_rvol_uses_shifted_returns(self):
        raw = _make_raw_df(300)
        spike_idx = 120

        feat_base   = build_features(raw)
        raw_spiked  = raw.copy()
        raw_spiked.iloc[spike_idx, raw_spiked.columns.get_loc("spy_close")] *= 10.0
        feat_spiked = build_features(raw_spiked)

        spike_date = raw_spiked.index[spike_idx]
        assert feat_base.loc[spike_date, "rvol_21d"] == pytest.approx(
            feat_spiked.loc[spike_date, "rvol_21d"], rel=1e-6
        ), "rvol_21d at spike date must equal baseline"

    def test_vix_shifted_by_one_day(self):
        """vix feature at row t must equal raw vix value at row t-1."""
        raw = _make_raw_df(200)
        feat = build_features(raw)

        for date in feat.index[10:30]:
            prev_date = raw.index[raw.index.get_loc(date) - 1]
            assert feat.loc[date, "vix"] == pytest.approx(
                raw.loc[prev_date, "vix"], rel=1e-9
            ), f"vix lookahead at {date}"

    def test_all_features_nan_free_after_warmup(self):
        feat = _make_features(500)
        assert feat.isna().sum().sum() == 0, "Feature matrix contains unexpected NaNs"

    def test_feature_columns(self):
        feat = _make_features(100)
        assert list(feat.columns) == ["ret_5d", "rvol_21d", "vix"]


# ── Test 2: Scaler fitted on past only ───────────────────────────────────────

class TestScalerFitOnPastOnly:

    def test_scaler_parameters_match_past_slice(self):
        feat = _make_features(400)
        cut = feat.index[199]
        past_data = feat.loc[:cut].values

        scaler = WalkForwardScaler().fit(past_data)
        expected_mean = past_data.mean(axis=0)
        expected_std  = past_data.std(axis=0, ddof=0)

        np.testing.assert_allclose(scaler._mean, expected_mean, rtol=1e-10)
        np.testing.assert_allclose(scaler._std,  expected_std,  rtol=1e-10)

    def test_full_sample_scaler_differs_from_past_scaler(self):
        feat = _make_features(400)
        cut  = feat.index[199]

        past_data = feat.loc[:cut].values
        full_data = feat.values

        scaler_past = WalkForwardScaler().fit(past_data)
        scaler_full = WalkForwardScaler().fit(full_data)

        assert not np.allclose(scaler_past._mean, scaler_full._mean)

    def test_transform_raises_without_fit(self):
        scaler = WalkForwardScaler()
        with pytest.raises(RuntimeError, match="fitted"):
            scaler.transform(np.zeros((5, 3)))

    def test_transform_does_not_refit(self):
        feat = _make_features(300)
        cut  = feat.index[149]
        past_data = feat.loc[:cut].values

        scaler = WalkForwardScaler().fit(past_data)
        mean_before = scaler._mean.copy()
        std_before  = scaler._std.copy()

        future_data = feat.loc[feat.index[150]:feat.index[200]].values
        scaler.transform(future_data)

        np.testing.assert_array_equal(scaler._mean, mean_before)
        np.testing.assert_array_equal(scaler._std,  std_before)


# ── Test 3: HMM fitted on past only ──────────────────────────────────────────

class TestHMMFitOnPastOnly:

    def test_walk_forward_cutoff_strictly_before_t(self):
        feat = _make_features(500)
        train_end  = str(feat.index[299].date())
        test_start = str(feat.index[300].date())
        test_end   = str(feat.index[350].date())

        result = run_walk_forward(
            df_features       = feat,
            train_end         = train_end,
            test_start        = test_start,
            test_end          = test_end,
            retrain_freq_days = 10,
        )

        assert len(result) > 0
        assert result.index.min() >= pd.Timestamp(test_start)
        assert result.index.max() <= pd.Timestamp(test_end)

    def test_hmm_fit_returns_valid_labels(self):
        feat     = _make_features(400)
        X_train  = feat.values[:300]
        scaler   = WalkForwardScaler().fit(X_train)
        X_scaled = scaler.transform(X_train)

        model = RegimeHMM(n_components=3, random_state=42).fit(X_scaled)
        labels_seen = set(model._label_map.values())
        assert labels_seen == {"bull", "sideways", "bear"}

    def test_predict_uses_transform_only(self):
        feat = _make_features(400)
        X_train  = feat.values[:300]
        X_test   = feat.values[300:310]

        scaler   = WalkForwardScaler().fit(X_train)
        mean_pre = scaler._mean.copy()
        std_pre  = scaler._std.copy()

        X_scaled = scaler.transform(X_train)
        model    = RegimeHMM(n_components=3, random_state=42).fit(X_scaled)

        X_test_scaled = scaler.transform(X_test)
        regimes = model.predict_regimes(X_test_scaled)

        np.testing.assert_array_equal(scaler._mean, mean_pre)
        np.testing.assert_array_equal(scaler._std,  std_pre)
        assert all(r in {"bull", "sideways", "bear"} for r in regimes)

    def test_state_labels_deterministic_by_mean_return(self):
        feat = _make_features(500)
        X_train = feat.values[:400]
        scaler  = WalkForwardScaler().fit(X_train)
        X_sc    = scaler.transform(X_train)

        model = RegimeHMM(n_components=3, random_state=7).fit(X_sc)

        state_means = {
            label: model._model.means_[idx, 0]
            for idx, label in model._label_map.items()
        }
        assert state_means["bull"] > state_means["sideways"] > state_means["bear"]

    def test_posterior_probabilities_sum_to_one(self):
        feat    = _make_features(400)
        X_train = feat.values[:300]
        X_test  = feat.values[300:310]

        scaler = WalkForwardScaler().fit(X_train)
        model  = RegimeHMM(n_components=3, random_state=42).fit(scaler.transform(X_train))
        proba  = model.predict_proba(scaler.transform(X_test))

        np.testing.assert_allclose(
            proba.sum(axis=1), np.ones(len(X_test)), atol=1e-6,
            err_msg="Posterior probabilities must sum to 1"
        )
