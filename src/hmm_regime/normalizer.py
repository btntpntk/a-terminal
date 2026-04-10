import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler


class Normalizer:
    def __init__(self) -> None:
        self._scaler = StandardScaler()

    def fit(self, X: pd.DataFrame) -> "Normalizer":
        self._scaler.fit(X)
        return self

    def transform(self, X: pd.DataFrame) -> np.ndarray:
        return self._scaler.transform(X)
