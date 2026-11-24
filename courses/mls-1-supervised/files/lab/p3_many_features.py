"""Project 3 (days 4-5): many features at once, vectorized, with feature scaling and feature engineering."""
import time

import numpy as np

from homes import load, rmse, scale, split

BASE = ["median_income", "housing_median_age", "total_rooms", "total_bedrooms", "population", "households",
        "latitude", "longitude"]
ENGINEERED = BASE + ["rooms_per_household", "people_per_household", "log_population", "income_squared"]


def features(df, cols):
    df = df.assign(log_population=np.log1p(df["population"]), income_squared=df["median_income"] ** 2)
    return df[cols].to_numpy(float)


def gd(X, y, alpha, steps):
    m, n = X.shape
    w, b = np.zeros(n), 0.0
    for _ in range(steps):
        err = X @ w + b - y                    # all districts at once: one matrix product, no loop over rows
        w -= alpha * (X.T @ err) / m
        b -= alpha * err.mean()
    return w, b


if __name__ == "__main__":
    tr, te = split(load())
    ytr, yte = tr["median_house_value"].to_numpy() / 1000, te["median_house_value"].to_numpy() / 1000
    Xtr, Xte = features(tr, BASE), features(te, BASE)
    print("1. Feature ranges are very different:")
    for c, lo, hi in zip(BASE, Xtr.min(0), Xtr.max(0)):
        print(f"   {c:20} {lo:10,.1f} to {hi:10,.1f}")

    w, b = gd(Xtr, ytr, 1e-7, 500)
    print(f"\n2. Gradient descent on the raw features (learning rate 1e-7; 3e-7 already blows up): "
          f"test RMSE ${rmse(yte, Xte @ w + b):.0f}k after 500 steps")
    Str, Ste, _, _ = scale(Xtr, Xte)
    t = time.perf_counter()
    w, b = gd(Str, ytr, 0.1, 500)
    print(f"3. The same, after z-score scaling (learning rate 0.1): test RMSE ${rmse(yte, Ste @ w + b):.0f}k "
          f"({(time.perf_counter() - t) * 1000:.0f} ms)")
    print("   the weights (in $1,000s per standard deviation):")
    for c, wi in sorted(zip(BASE, w), key=lambda t: -abs(t[1]))[:5]:
        print(f"   {c:20} {wi:+7.1f}")

    Xtr2, Xte2 = features(tr, ENGINEERED), features(te, ENGINEERED)
    S2tr, S2te, _, _ = scale(Xtr2, Xte2)
    w2, b2 = gd(S2tr, ytr, 0.1, 2000)
    print(f"\n4. With 4 engineered features (rooms and people per household, log population, income squared): "
          f"test RMSE ${rmse(yte, S2te @ w2 + b2):.0f}k")

    loop_t = time.perf_counter()
    for _ in range(5):
        pred = np.array([sum(S2tr[i, j] * w2[j] for j in range(len(w2))) + b2 for i in range(len(S2tr))])
    loop_t = (time.perf_counter() - loop_t) / 5
    vec_t = time.perf_counter()
    for _ in range(5):
        pred_v = S2tr @ w2 + b2
    vec_t = (time.perf_counter() - vec_t) / 5
    print(f"5. Predicting all {len(S2tr):,} training districts: Python loops {loop_t * 1000:.0f} ms, vectorized "
          f"{vec_t * 1000:.2f} ms ({loop_t / vec_t:,.0f} times faster), same answers: {np.allclose(pred, pred_v)}")
