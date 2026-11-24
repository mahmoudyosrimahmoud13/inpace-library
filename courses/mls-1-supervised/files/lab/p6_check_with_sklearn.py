"""Project 6 (days 9-10): check everything you built against scikit-learn, then see how far a stronger model goes.
If your from-scratch versions match a trusted library, you really understand them."""
import time

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import LinearRegression, LogisticRegression

from homes import load, rmse, scale, split
from p3_many_features import ENGINEERED, features, gd
from p4_logistic import sigmoid, train

if __name__ == "__main__":
    tr, te = split(load())
    y, yt = tr["median_house_value"].to_numpy() / 1000, te["median_house_value"].to_numpy() / 1000
    X, Xt, _, _ = scale(features(tr, ENGINEERED), features(te, ENGINEERED))

    w, b = gd(X, y, 0.1, 5000)
    sk = LinearRegression().fit(X, y)
    print("1. Linear regression, 12 features:")
    print(f"   yours (gradient descent, 5,000 steps)  test RMSE ${rmse(yt, Xt @ w + b):.2f}k")
    print(f"   scikit-learn (exact solution)          test RMSE ${rmse(yt, sk.predict(Xt)):.2f}k")
    print(f"   largest difference between the two sets of weights: {np.abs(w - sk.coef_).max():.3f}")

    c, ct = (y > 250).astype(float), (yt > 250).astype(float)
    w2, b2 = train(X, c, steps=5000)
    lr = LogisticRegression(C=np.inf, max_iter=5000).fit(X, c)   # C=inf: no regularization, like yours
    mine = (sigmoid(Xt @ w2 + b2) > 0.5)
    print("\n2. Logistic regression, expensive or not:")
    print(f"   yours          test accuracy {(mine == ct).mean():.2%}")
    print(f"   scikit-learn   test accuracy {lr.score(Xt, ct):.2%}   (same answer on {(mine == lr.predict(Xt)).mean():.1%} of districts)")

    t = time.perf_counter()
    gb = HistGradientBoostingRegressor(random_state=0).fit(X, y)
    print(f"\n3. Beyond straight lines: gradient boosted trees (the refresh's part 2) on the same features: "
          f"test RMSE ${rmse(yt, gb.predict(Xt)):.0f}k in {time.perf_counter() - t:.1f} s")
    print("   Location matters in curved ways (coast, cities) that one weight per feature can't capture.")
