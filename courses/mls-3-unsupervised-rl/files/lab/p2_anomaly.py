"""Project 2 (day 2): anomaly detection. Plant 15 fake 'bot' accounts among the 943 real raters, then catch them
with a Gaussian model of normal behaviour, its threshold chosen on a small labelled set."""
import numpy as np
import pandas as pd

from movies import ratings


def user_features(r):
    g = r.groupby("user")
    days = g["time"].agg(lambda t: (t.max() - t.min()) / 86400 + 1)
    f = pd.DataFrame({"log_count": np.log(g.size()), "mean": g["rating"].mean(), "std": g["rating"].std(),
                      "share_5": g["rating"].apply(lambda x: (x == 5).mean()),
                      "log_per_day": np.log(g.size() / days)})
    return f


def bots(r, n=15, seed=1):
    """Accounts that rate 80 to 200 random movies within an hour, almost all 5 stars: rating fraud."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        uid, k, t0 = 10_000 + i, rng.integers(80, 200), r["time"].max()
        for mv in rng.choice(1682, k, replace=False) + 1:
            rows.append((uid, mv, 5 if rng.random() < 0.95 else 4, t0 + int(rng.integers(0, 3600))))
    return pd.DataFrame(rows, columns=r.columns)


def fit(X):
    return X.mean(0), X.var(0)


def density(X, mu, var):
    """p(x): the product of one Gaussian per feature (features treated as independent)."""
    return np.prod(np.exp(-(X - mu) ** 2 / (2 * var)) / np.sqrt(2 * np.pi * var), axis=1)


if __name__ == "__main__":
    r = ratings()
    f = user_features(pd.concat([r, bots(r)]))
    f["bot"] = f.index >= 10_000
    rng = np.random.default_rng(0)
    real = f[~f["bot"]].sample(frac=1, random_state=0)
    fake = f[f["bot"]].sample(frac=1, random_state=0)
    train = real.iloc[:600]                                   # normal accounts only: learn what normal looks like
    val = pd.concat([real.iloc[600:770], fake.iloc[:7]])      # a few labelled ones, to choose the threshold
    test = pd.concat([real.iloc[770:], fake.iloc[7:]])
    cols = ["log_count", "mean", "std", "share_5", "log_per_day"]
    print("1. Normal accounts against the bots (means):")
    print(f.groupby("bot")[cols].mean().round(2).rename(index={False: "   real", True: "   bots"}).to_string())
    mu, var = fit(train[cols].to_numpy())
    pv, pt = density(val[cols].to_numpy(), mu, var), density(test[cols].to_numpy(), mu, var)
    best = (0, None)
    for eps in np.logspace(-12, 0, 200):
        pred, y = pv < eps, val["bot"].to_numpy()
        tp = np.sum(pred & y)
        f1 = 2 * tp / max(pred.sum() + y.sum(), 1)
        if f1 > best[0]:
            best = (f1, eps)
    eps = best[1]
    pred, y = pt < eps, test["bot"].to_numpy()
    print(f"\n2. Threshold chosen on validation (F1 {best[0]:.2f}): p(x) < {eps:.1e}")
    print(f"   test set: {np.sum(pred & y)} of {y.sum()} bots caught, {np.sum(pred & ~y)} of {(~y).sum()} real accounts flagged")
    flagged = test[pred & ~y]
    if len(flagged):
        print(f"   the real accounts flagged look unusual too: {flagged[['log_count', 'mean', 'share_5']].round(2).to_dict('records')[:2]}")
