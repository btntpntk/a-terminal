import pandas as pd

from .hmm_model import HMMModel
from .normalizer import Normalizer


def run_walk_forward(features: pd.DataFrame, train_end: str) -> pd.DataFrame:
    train_end_dt = pd.Timestamp(train_end)
    test_dates = features.index[features.index > train_end_dt]

    if features[features.index <= train_end_dt].shape[0] < 50:
        raise ValueError("Insufficient training data before train_end")
    if len(test_dates) == 0:
        raise ValueError("No test data after train_end")

    records = []
    refit_every = 21
    scaler: Normalizer | None = None
    model: HMMModel | None = None

    for i, date in enumerate(test_dates):
        if i % refit_every == 0:
            train_data = features[features.index < date]
            scaler = Normalizer().fit(train_data)
            X_train = scaler.transform(train_data)
            # Pass both scaled AND original data so the model labels states
            # by realized returns, not by estimated means in scaled space.
            model = HMMModel().fit(X_train, train_data.values)

        X_point = scaler.transform(features.loc[[date]])
        regime = model.predict(X_point)[0]
        proba  = model.predict_proba(X_point)

        records.append({
            "date":       date,
            "regime":     regime,
            "p_bull":     float(proba["p_bull"].iloc[0]),
            "p_sideways": float(proba["p_sideways"].iloc[0]),
            "p_bear":     float(proba["p_bear"].iloc[0]),
            "p_crash":    float(proba["p_crash"].iloc[0]),
        })

    return pd.DataFrame(records).set_index("date")
