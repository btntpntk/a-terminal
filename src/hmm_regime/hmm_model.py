"""
src/hmm_regime/hmm_model.py

RegimeHMM — thin wrapper around hmmlearn.GaussianHMM that adds:
  - deterministic state labeling (bull / bear / sideways) based on mean return
  - convenience methods: predict_regimes(), predict_proba(), get_state_stats()
  - robust EM initialization (multiple restarts, best log-likelihood kept)
"""

from __future__ import annotations

import warnings
from typing import Literal

import numpy as np
import pandas as pd
from hmmlearn import hmm

# Silence hmmlearn convergence warnings on noisy data
warnings.filterwarnings("ignore", category=UserWarning, module="hmmlearn")

# Canonical regime names, ordered by mean return (set in _assign_labels)
REGIME_NAMES = ["bear", "sideways", "bull"]
REGIME_COLORS = {"bull": "#22c55e", "sideways": "#94a3b8", "bear": "#ef4444"}


class RegimeHMM:
    """
    HMM-based market regime classifier.

    After fitting, each hidden state is labeled deterministically:
      - State with lowest  mean ret_5d  → "bear"
      - State with middle  mean ret_5d  → "sideways"
      - State with highest mean ret_5d  → "bull"

    Parameters
    ----------
    n_components : int
        Number of hidden states (default 3: bull/sideways/bear).
    covariance_type : str
        hmmlearn covariance type.  "diag" is the recommended default —
        it's regularized and less prone to EM collapse than "full".
    n_iter : int
        Maximum EM iterations per restart.
    n_restarts : int
        Number of random EM restarts; best log-likelihood is kept.
    random_state : int
        Seed for reproducibility.
    """

    def __init__(
        self,
        n_components: int = 3,
        covariance_type: Literal["diag", "full", "spherical", "tied"] = "diag",
        n_iter: int = 200,
        n_restarts: int = 5,
        random_state: int = 42,
    ) -> None:
        self.n_components = n_components
        self.covariance_type = covariance_type
        self.n_iter = n_iter
        self.n_restarts = n_restarts
        self.random_state = random_state

        self._model: hmm.GaussianHMM | None = None
        self._label_map: dict[int, str] = {}   # state_idx → regime name
        self._fitted = False

    # ── Public interface ──────────────────────────────────────────────────────

    def fit(self, X: np.ndarray) -> "RegimeHMM":
        """
        Fit HMM on training data using multiple random restarts.

        Parameters
        ----------
        X : np.ndarray of shape (n_samples, n_features)
            Already scaled by WalkForwardScaler.  Must be from data[0:t-1] only.

        Returns
        -------
        self
        """
        best_score = -np.inf
        best_model = None

        for seed in range(self.n_restarts):
            model = hmm.GaussianHMM(
                n_components=self.n_components,
                covariance_type=self.covariance_type,
                n_iter=self.n_iter,
                random_state=self.random_state + seed,
                tol=1e-4,
            )
            try:
                model.fit(X)
                score = model.score(X)
                if score > best_score:
                    best_score = score
                    best_model = model
            except Exception:
                continue

        if best_model is None:
            raise RuntimeError("All HMM EM restarts failed — check your training data.")

        self._model = best_model
        self._assign_labels()
        self._fitted = True
        return self

    def predict_regimes(self, X: np.ndarray) -> list[str]:
        """
        Viterbi-decode the most likely state sequence and return regime labels.

        Parameters
        ----------
        X : np.ndarray of shape (n_samples, n_features)
            Scaled observations (transform-only, not fit).

        Returns
        -------
        list[str]
            Regime names, e.g. ["bull", "bull", "sideways", "bear", ...]
        """
        self._check_fitted()
        state_seq = self._model.predict(X)
        return [self._label_map[s] for s in state_seq]

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """
        Return posterior state probabilities via forward-backward algorithm.

        Parameters
        ----------
        X : np.ndarray of shape (n_samples, n_features)

        Returns
        -------
        np.ndarray of shape (n_samples, n_components)
            Columns ordered as [bear, sideways, bull] (ascending mean return).
        """
        self._check_fitted()
        # posteriors[:, state_idx] — reorder to [bear, sideways, bull]
        _, posteriors = self._model.score_samples(X)

        # Build reordered array: col 0 = bear, col 1 = sideways, col 2 = bull
        ordered = np.zeros_like(posteriors)
        for state_idx, label in self._label_map.items():
            col = REGIME_NAMES.index(label)
            ordered[:, col] = posteriors[:, state_idx]
        return ordered

    def get_state_stats(self) -> pd.DataFrame:
        """
        Return a DataFrame with mean and std per regime per feature.

        Returns
        -------
        pd.DataFrame
            Index: regime names (bear/sideways/bull)
            Columns: feature_0_mean, feature_0_std, feature_1_mean, ...
        """
        self._check_fitted()
        rows = {}
        feature_names = ["ret_5d", "rvol_21d", "vix", "yield_spread"]

        for state_idx, label in self._label_map.items():
            mean = self._model.means_[state_idx]
            # covariance_ shape depends on covariance_type
            if self.covariance_type == "diag":
                std = np.sqrt(self._model.covars_[state_idx])
            elif self.covariance_type == "full":
                std = np.sqrt(np.diag(self._model.covars_[state_idx]))
            else:
                std = np.full_like(mean, np.nan)

            row = {}
            for i, fname in enumerate(feature_names):
                row[f"{fname}_mean"] = mean[i]
                row[f"{fname}_std"] = std[i]
            rows[label] = row

        return pd.DataFrame(rows).T.loc[REGIME_NAMES]

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _assign_labels(self) -> None:
        """
        Label states deterministically by mean of feature 0 (ret_5d, ascending).
        Lowest mean → bear, middle → sideways, highest → bull.
        """
        means_ret = self._model.means_[:, 0]       # shape (n_components,)
        sorted_idx = np.argsort(means_ret)         # ascending order
        label_list = REGIME_NAMES[: self.n_components]
        self._label_map = {
            int(sorted_idx[i]): label_list[i]
            for i in range(self.n_components)
        }

    def _check_fitted(self) -> None:
        if not self._fitted:
            raise RuntimeError("RegimeHMM must be fitted before prediction.")
