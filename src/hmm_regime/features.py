import numpy as np
import pandas as pd


def compute_features(prices: pd.DataFrame) -> pd.DataFrame:
    close = prices["Close"]
    log_return = np.log(close / close.shift(1))
    vol_21d = log_return.rolling(21).std()

    feat = pd.DataFrame(
        {"log_return": log_return, "vol_21d": vol_21d},
        index=prices.index,
    )
    return feat.dropna()
