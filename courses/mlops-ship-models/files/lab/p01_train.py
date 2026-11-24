"""Project 1: from a notebook to a training script you can rerun and trust.

Bikecast predicts how many bikes will be rented in an hour. This script trains it the way the rest of the course
expects: fixed settings, a split by time, a baseline to beat, and a check for leaks."""
import json
import time

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import train_test_split

from common import FEATURES, TARGET, between, load, score

SETTINGS = {"train_start": "2011-01-08", "train_end": "2012-01-01", "valid_end": "2012-03-01",
            "max_iter": 300, "learning_rate": 0.05, "max_leaf_nodes": 31, "seed": 42}


def baseline(train):
    """The model to beat: the average count for this hour on working days or days off."""
    table = train.groupby(["hr", "workingday"])[TARGET].mean()
    return lambda df: table.loc[list(zip(df["hr"], df["workingday"]))].to_numpy()


def make_model(s):
    return HistGradientBoostingRegressor(loss="poisson", max_iter=s["max_iter"], learning_rate=s["learning_rate"],
                                         max_leaf_nodes=s["max_leaf_nodes"], random_state=s["seed"])


def train(s=SETTINGS, df=None, features=FEATURES):
    df = load() if df is None else df
    tr = between(df, s["train_start"], s["train_end"])
    va = between(df, s["train_end"], s["valid_end"])
    model = make_model(s).fit(tr[features], tr[TARGET])
    return model, tr, va


if __name__ == "__main__":
    df = load()
    print(f"Data: {len(df):,} hours from {df['time'].min():%Y-%m-%d} to {df['time'].max():%Y-%m-%d}, "
          f"{df[TARGET].sum():,} rentals\n")

    # 1. The leak: casual + registered = cnt, exactly. A model with them looks perfect and is useless.
    leak = (df["casual"] + df["registered"] == df[TARGET]).mean()
    rnd_tr, rnd_te = train_test_split(df, test_size=0.2, random_state=0)
    leaky = make_model(SETTINGS).fit(rnd_tr[FEATURES + ["casual", "registered"]], rnd_tr[TARGET])
    print(f"1. casual + registered == cnt in {leak:.0%} of rows. With them as features:")
    print(f"   MAE {score(rnd_te[TARGET], leaky.predict(rnd_te[FEATURES + ['casual', 'registered']]))['mae']:.1f} "
          "bikes: too good to be true, because at prediction time nobody knows them yet\n")

    # 2. A random split against a time split.
    m = make_model(SETTINGS).fit(rnd_tr[FEATURES + ["yr"]], rnd_tr[TARGET])
    r = score(rnd_te[TARGET], m.predict(rnd_te[FEATURES + ["yr"]]))
    t = time.perf_counter()
    model, tr, va = train()
    secs = time.perf_counter() - t
    v = score(va[TARGET], model.predict(va[FEATURES]))
    b = score(va[TARGET], baseline(tr)(va))
    print("2. How good is it? Depends how you test:")
    print(f"   random 80/20 split           MAE {r['mae']:5.1f}   (future hours leak into training)")
    print(f"   train 2011, test Jan-Feb 2012 MAE {v['mae']:5.1f}   RMSE {v['rmse']:5.1f}   bias {v['bias']:+.1f}")
    print(f"   baseline (hour x workday)     MAE {b['mae']:5.1f}   RMSE {b['rmse']:5.1f}   bias {b['bias']:+.1f}")
    print(f"   trained on {len(tr):,} hours in {secs:.1f} s\n")

    # 3. Reproducible: same settings, same data -> same model.
    again, _, _ = train()
    same = np.allclose(model.predict(va[FEATURES]), again.predict(va[FEATURES]))
    print(f"3. Train twice with the same settings: identical predictions = {same}")
    json.dump({"settings": SETTINGS, "valid": v, "baseline": b}, open("p01_result.json", "w"), indent=1)
    print("   settings and scores saved to p01_result.json")
