import warnings

import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM

_N_RESTARTS = 15
_MIN_STATE_FREQ = 0.03      # reject if any state < 3% of training data
_MIN_MEAN_SPREAD = 2e-4     # reject if max–min realized daily log return < ~5% ann


def _fit_one(X: np.ndarray, seed: int) -> tuple[GaussianHMM, float]:
    model = GaussianHMM(
        n_components=4,
        covariance_type="diag",
        n_iter=200,
        tol=1e-4,
        random_state=seed,
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model.fit(X)
    return model, model.score(X)


def _realized_means(model: GaussianHMM, X_scaled: np.ndarray, X_orig: np.ndarray):
    """Actual mean log return and mean vol per state in original (unscaled) space."""
    states = model.predict(X_scaled)
    log_ret = np.array([
        X_orig[states == s, 0].mean() if (states == s).any() else 0.0
        for s in range(model.n_components)
    ])
    vol = np.array([
        X_orig[states == s, 1].mean() if (states == s).any() else 0.0
        for s in range(model.n_components)
    ])
    return states, log_ret, vol


def _is_acceptable(model: GaussianHMM, X_scaled: np.ndarray, X_orig: np.ndarray) -> bool:
    states, log_ret, _ = _realized_means(model, X_scaled, X_orig)
    n = len(states)
    # Reject if any state has too few samples
    if any(np.sum(states == s) / n < _MIN_STATE_FREQ for s in range(model.n_components)):
        return False
    # Reject if the realized mean returns aren't spread out enough
    if log_ret.max() - log_ret.min() < _MIN_MEAN_SPREAD:
        return False
    return True


class HMMModel:
    def __init__(self) -> None:
        self._model: GaussianHMM | None = None
        self._state_to_label: dict[int, str] = {}
        self._label_to_col: dict[str, int] = {}

    def fit(self, X_scaled: np.ndarray, X_orig: np.ndarray) -> "HMMModel":
        """
        X_scaled : StandardScaler-transformed features (what the HMM trains on).
        X_orig   : original unscaled features, same rows — used to label states by
                   realized returns instead of estimated means in scaled space.
        """
        best_model: GaussianHMM | None = None
        best_score = -np.inf

        # Pass 1: require full acceptability (frequency + spread)
        for seed in range(_N_RESTARTS):
            try:
                model, score = _fit_one(X_scaled, seed)
                if _is_acceptable(model, X_scaled, X_orig) and score > best_score:
                    best_score = score
                    best_model = model
            except Exception:
                continue

        # Pass 2: relax spread requirement, keep frequency check
        if best_model is None:
            for seed in range(_N_RESTARTS):
                try:
                    model, score = _fit_one(X_scaled, seed)
                    states = model.predict(X_scaled)
                    freq_ok = all(
                        np.sum(states == s) / len(states) >= _MIN_STATE_FREQ
                        for s in range(model.n_components)
                    )
                    if freq_ok and score > best_score:
                        best_score = score
                        best_model = model
                except Exception:
                    continue

        # Pass 3: last resort — any model that fits
        if best_model is None:
            for seed in range(_N_RESTARTS):
                try:
                    model, score = _fit_one(X_scaled, seed)
                    if score > best_score:
                        best_score = score
                        best_model = model
                except Exception:
                    continue

        if best_model is None:
            raise RuntimeError("HMM failed to fit with any random seed")

        self._model = best_model
        self._build_label_map(X_scaled, X_orig)
        return self

    def _build_label_map(self, X_scaled: np.ndarray, X_orig: np.ndarray) -> None:
        """Label states using realized (unscaled) mean log returns — not HMM estimated means."""
        _, log_ret, vol = _realized_means(self._model, X_scaled, X_orig)

        sorted_by_return = np.argsort(log_ret)
        crash_state = int(sorted_by_return[0])
        bull_state  = int(sorted_by_return[-1])
        remaining   = [int(sorted_by_return[1]), int(sorted_by_return[2])]

        # Of the two middle states: lower realized vol → sideways, higher → bear
        if vol[remaining[0]] <= vol[remaining[1]]:
            sideways_state, bear_state = remaining[0], remaining[1]
        else:
            sideways_state, bear_state = remaining[1], remaining[0]

        self._state_to_label = {
            bull_state:     "bull",
            sideways_state: "sideways",
            bear_state:     "bear",
            crash_state:    "crash",
        }
        self._label_to_col = {
            "bull":     bull_state,
            "sideways": sideways_state,
            "bear":     bear_state,
            "crash":    crash_state,
        }

    def predict(self, X_scaled: np.ndarray) -> list[str]:
        states = self._model.predict(X_scaled)
        return [self._state_to_label[int(s)] for s in states]

    def predict_proba(self, X_scaled: np.ndarray) -> pd.DataFrame:
        proba = self._model.predict_proba(X_scaled)
        return pd.DataFrame({
            "p_bull":     proba[:, self._label_to_col["bull"]],
            "p_sideways": proba[:, self._label_to_col["sideways"]],
            "p_bear":     proba[:, self._label_to_col["bear"]],
            "p_crash":    proba[:, self._label_to_col["crash"]],
        })
