"""Project 8: watch the model in production, catch drift, and retrain.

The champion was trained on data up to April 2012. Here it runs week by week from May to December 2012: every week
it predicts, the real counts arrive, and monitoring checks the inputs (drift) and the errors. Three policies are
compared: never retrain, retrain on a schedule, and retrain when monitoring raises an alert."""
import numpy as np
import pandas as pd

from common import FEATURES, TARGET, between, load, score
from p01_train import SETTINGS, make_model


def psi(expected, actual, bins=10):
    """Population stability index (used in the exercises): how much a feature's distribution moved. Bins come from
    the reference data.
    Under 0.1 is stable, 0.1 to 0.25 is a moderate shift, over 0.25 is a big one."""
    edges = np.unique(np.quantile(expected, np.linspace(0, 1, bins + 1)))
    edges[0], edges[-1] = -np.inf, np.inf
    e = np.histogram(expected, edges)[0] / len(expected) + 1e-4
    a = np.histogram(actual, edges)[0] / len(actual) + 1e-4
    return float(np.sum((a - e) * np.log(a / e)))


def fit(df, end):
    """Train on everything up to `end`. The reference for monitoring is the last 4 weeks before `end`: what 'normal'
    looked like just before the model went live. (A whole year would show seasons as drift.)"""
    cut = pd.Timestamp(end) - pd.Timedelta(days=28)
    ref = between(df, cut, end)
    held_out = make_model(SETTINGS).fit(*xy(between(df, SETTINGS["train_start"], cut)))
    ref_mae = score(ref[TARGET], held_out.predict(ref[FEATURES]))["mae"]   # an honest error, on unseen weeks
    tr = between(df, SETTINGS["train_start"], end)
    model = make_model(SETTINGS).fit(*xy(tr))                               # then train on everything
    return model, tr, ref_mae


def xy(d):
    return d[FEATURES], d[TARGET]


def simulate(df, policy, start="2012-05-01", end="2013-01-01", verbose=False):
    model, ref, ref_mae = fit(df, start)
    weeks = pd.date_range(start, end, freq="7D")
    errors, retrains, bad_weeks, rows = [], 0, 0, []
    for i, (a, b) in enumerate(zip(weeks[:-1], weeks[1:])):
        wk = between(df, a, b)
        pred = model.predict(wk[FEATURES])
        s = score(wk[TARGET], pred)                       # the labels arrive at the end of the week
        errors.append(np.abs(wk[TARGET] - pred))
        # Input drift. A tree model can't predict beyond what it saw, so the key signal here is how many hours have
        # a demand level (last_week_avg) higher than anything in training.
        beyond = float((wk["last_week_avg"] > ref["last_week_avg"].max()).mean())
        # Errors are noisy week to week (weather, holidays): alert only after 2 bad weeks in a row.
        bad_weeks = bad_weeks + 1 if s["mae"] > 1.3 * ref_mae else 0
        alert = bad_weeks >= 2 or beyond > 0.5
        rows.append({"week": f"{a:%b %d}", "mae": s["mae"], "vs_ref": s["mae"] / ref_mae, "bias": s["bias"],
                     "beyond_training": beyond,
                     "alert": "ALERT" if alert else ""})
        retrain = (policy == "on alert" and alert) or (policy == "every 4 weeks" and (i + 1) % 4 == 0)
        if retrain:
            model, ref, ref_mae = fit(df, b)              # all data up to now, and a fresh reference
            bad_weeks, retrains = 0, retrains + 1
            rows[-1]["alert"] += " -> retrained"
    all_err = np.concatenate(errors)
    return {"policy": policy, "mae": float(all_err.mean()), "retrains": retrains}, pd.DataFrame(rows)


if __name__ == "__main__":
    df = load()
    res, rows = simulate(df, "on alert")
    print("Week by week with 'retrain on alert'. vs_ref = this week's MAE against the error measured before going live;")
    print("beyond_training = share of hours with a demand level above anything the model trained on.")
    show = rows[["week", "mae", "vs_ref", "bias", "beyond_training", "alert"]].copy()
    show["vs_ref"] = show["vs_ref"].map(lambda x: f"{x:.2f}x")
    show["beyond_training"] = show["beyond_training"].map(lambda x: f"{x:.0%}")
    print(show.to_string(index=False, float_format=lambda x: f"{x:6.1f}"))
    print()
    print(f"{'policy':16} {'MAE May-Dec':>12} {'retrains':>9}")
    for policy in ["never", "every 4 weeks", "on alert"]:
        r, _ = simulate(df, policy)
        print(f"{policy:16} {r['mae']:12.1f} {r['retrains']:9}")
