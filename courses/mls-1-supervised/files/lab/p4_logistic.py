"""Project 4 (days 6-7): logistic regression from scratch. Is a district expensive (median value above $250k)?"""
import numpy as np

from homes import load, scale, split
from p3_many_features import ENGINEERED, features


def sigmoid(z):
    return 1 / (1 + np.exp(-np.clip(z, -500, 500)))   # clip: exp of a huge number overflows


def train(X, y, alpha=0.5, steps=3000, lam=0.0):
    m, n = X.shape
    w, b = np.zeros(n), 0.0
    for _ in range(steps):
        p = sigmoid(X @ w + b)
        w -= alpha * ((X.T @ (p - y)) / m + lam / m * w)
        b -= alpha * (p - y).mean()
    return w, b


def log_loss(y, p):
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


if __name__ == "__main__":
    tr, te = split(load())
    ytr, yte = (tr["median_house_value"] > 250_000).to_numpy(float), (te["median_house_value"] > 250_000).to_numpy(float)
    Xtr, Xte, _, _ = scale(features(tr, ENGINEERED), features(te, ENGINEERED))
    print(f"1. {ytr.mean():.0%} of training districts are 'expensive'. Always saying 'no' is {1 - yte.mean():.0%} "
          f"right on the test set: the accuracy to beat.")
    w, b = train(Xtr, ytr)
    p = sigmoid(Xte @ w + b)
    print(f"2. Logistic regression: test accuracy {((p > 0.5) == yte).mean():.1%}, log loss {log_loss(yte, p):.3f}")
    print("   strongest features (positive: more likely expensive):")
    for c, wi in sorted(zip(ENGINEERED, w), key=lambda t: -abs(t[1]))[:4]:
        print(f"   {c:22} {wi:+.2f}")
    tp = ((p > 0.5) & (yte == 1)).sum()
    print(f"3. Of {int(yte.sum())} expensive test districts it finds {tp} ({tp / yte.sum():.0%}); of those it calls "
          f"expensive, {tp / (p > 0.5).sum():.0%} are")
    i = np.argsort(np.abs(p - 0.5))[:3]
    print("4. The three districts it was least sure about:")
    for k in i:
        print(f"   value ${te['median_house_value'].iloc[k] / 1000:.0f}k, income ${te['median_income'].iloc[k] * 10:.0f}k: "
              f"P(expensive) = {p[k]:.2f}")
