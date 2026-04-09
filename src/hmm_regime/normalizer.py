"""
src/hmm_regime/normalizer.py

WalkForwardScaler — a stateless-after-fit scaler that is ALWAYS fitted
exclusively on training data (data[0 : t-1]).

Design constraints:
  - fit()      : computes mean/std from the supplied training window only
  - transform(): applies pre-fitted mean/std; raises if not yet fitted
  - NEVER use sklearn's StandardScaler fitted on the full sample — that
    constitutes lookahead because future observations influence the mean/std.

Numerical safeguards:
  - Features with zero variance (constant columns) are replaced by 0 after
    transform to avoid divide-by-zero (rare but possible in short windows).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


class WalkForwardScaler:
    """
    Mean-std scaler fitted strictly on past data.

    Usage
    -----
    scaler = WalkForwardScaler()
    scaler.fit(X_train)          # X_train must end at t-1 or earlier
    X_scaled = scaler.transform(X_any)   # X_any can be 1 or more rows
    """

    def __init__(self) -> None:
        self._mean: np.ndarray | None = None
        self._std: np.ndarray | None = None
        self._fitted = False

    def fit(self, X: pd.DataFrame | np.ndarray) -> "WalkForwardScaler":
        """
        Fit scaler on training data.

        Parameters
        ----------
        X : array-like of shape (n_samples, n_features)
            Must contain ONLY rows from t=0 … t-1.

        Returns
        -------
        self
        """
        arr = np.asarray(X, dtype=float)
        self._mean = arr.mean(axis=0)
        self._std = arr.std(axis=0, ddof=0)
        self._fitted = True
        return self

    def transform(self, X: pd.DataFrame | np.ndarray) -> np.ndarray:
        """
        Standardize X using the fitted mean/std.

        Parameters
        ----------
        X : array-like of shape (n_samples, n_features)

        Returns
        -------
        np.ndarray of shape (n_samples, n_features)
        """
        if not self._fitted:
            raise RuntimeError("WalkForwardScaler must be fitted before transform().")

        arr = np.asarray(X, dtype=float)
        # Zero-variance protection: set std to 1 where it's 0 (avoids inf)
        safe_std = np.where(self._std == 0, 1.0, self._std)
        scaled = (arr - self._mean) / safe_std

        # Where std was 0, result should be 0 (not NaN/inf)
        scaled[:, self._std == 0] = 0.0
        return scaled

    def fit_transform(self, X: pd.DataFrame | np.ndarray) -> np.ndarray:
        """Fit and immediately transform the same data (for training window)."""
        return self.fit(X).transform(X)
