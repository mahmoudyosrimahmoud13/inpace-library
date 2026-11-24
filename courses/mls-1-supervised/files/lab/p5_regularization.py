"""Project 5 (day 8): overfitting, seen and fixed. Fit polynomials of income and age on only 100 districts,
then add L2 regularization."""
import numpy as np

from homes import load, rmse, split

tr, te = split(load())
small = tr.iloc[:100]                                  # a small training set makes overfitting easy to see


LO = small[["median_income", "housing_median_age"]].min().to_numpy()
HI = small[["median_income", "housing_median_age"]].max().to_numpy()


def poly(df, degree):
    """All products income^i * age^j up to the degree. Inputs are first mapped to -1..1 using the training range
    (and clipped to it), so high powers stay small and a test district can't push them to huge values."""
    x = np.clip(df[["median_income", "housing_median_age"]].to_numpy(), LO, HI)
    x1, x2 = (2 * (x - LO) / (HI - LO) - 1).T
    cols = [x1 ** i * x2 ** j for i in range(degree + 1) for j in range(degree + 1 - i) if i + j > 0]
    return np.column_stack(cols)


def fit(X, y, lam):
    """Ridge regression in closed form: w = (X^T X + lam I)^-1 X^T y, with the bias not penalized."""
    Xb = np.column_stack([np.ones(len(X)), X])
    penalty = lam * np.eye(Xb.shape[1])
    penalty[0, 0] = 0
    return np.linalg.solve(Xb.T @ Xb + penalty, Xb.T @ y)


def predict(X, w):
    return np.column_stack([np.ones(len(X)), X]) @ w


if __name__ == "__main__":
    y, yt = small["median_house_value"].to_numpy() / 1000, te["median_house_value"].to_numpy() / 1000
    print("1. Polynomials of income and age, trained on 100 districts:")
    print(f"   {'degree':>6} {'features':>9} {'train RMSE':>11} {'test RMSE':>10}")
    for d in (1, 2, 4, 6, 8):
        w = fit(poly(small, d), y, 0)
        print(f"   {d:6} {poly(small, d).shape[1]:9} {rmse(y, predict(poly(small, d), w)):10.0f}k "
              f"{rmse(yt, predict(poly(te, d), w)):9.0f}k")
    print("   Training error keeps falling; test error rises: the model learns the 100 districts' noise.\n")
    print("2. Degree 8 with L2 regularization (lambda):")
    for lam in (0, 0.1, 1, 10, 100, 1000):
        w = fit(poly(small, 8), y, lam)
        print(f"   lambda {lam:6}: train {rmse(y, predict(poly(small, 8), w)):4.0f}k, "
              f"test {rmse(yt, predict(poly(te, 8), w)):6.0f}k, largest weight {np.abs(w[1:]).max():10,.0f}")
    big = tr["median_house_value"].to_numpy() / 1000
    w = fit(poly(tr, 8), big, 0)
    print(f"\n3. Or get more data: degree 8, no regularization, all {len(tr):,} training districts: "
          f"test {rmse(yt, predict(poly(te, 8), w)):.0f}k")
