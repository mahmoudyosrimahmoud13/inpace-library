"""Project 1 (day 2): a line through the data. Predict a district's house value from its median income, and see
the cost function as a bowl."""
import numpy as np

from homes import load, split

df = load()
train, test = split(df)
x, y = train["median_income"].to_numpy(), train["median_house_value"].to_numpy() / 1000   # value in $1,000s


def cost(w, b, x=x, y=y):
    """Squared error cost J(w, b) = 1/(2m) * sum((w*x + b - y)^2)."""
    return float(np.mean((w * x + b - y) ** 2) / 2)


if __name__ == "__main__":
    print(f"{len(df):,} districts ({len(train):,} to train, {len(test):,} to test). Income is in $10,000s.\n")
    print(f"1. Correlation between median income and house value: {np.corrcoef(x, y)[0, 1]:.2f}")
    ws, bs = np.linspace(0, 70, 141), np.linspace(-50, 150, 201)
    grid = np.array([[cost(w, b) for w in ws] for b in bs])
    i, j = np.unravel_index(grid.argmin(), grid.shape)
    print(f"2. Cost on a grid of {grid.size:,} (w, b) pairs: lowest {grid.min():,.0f} at w = {ws[j]:.1f}, b = {bs[i]:.1f}")
    for w, b in [(0, y.mean()), (20, 50), (ws[j], bs[i])]:
        print(f"   w = {w:5.1f}, b = {b:6.1f}  ->  cost {cost(w, b):9,.0f}")
    W, B = np.polyfit(x, y, 1)
    print(f"3. The exact least-squares line: value = {W:.1f} x income + {B:.1f}  (cost {cost(W, B):,.0f})")
    xt, yt = test["median_income"].to_numpy(), test["median_house_value"].to_numpy() / 1000
    err = np.sqrt(np.mean((W * xt + B - yt) ** 2))
    print(f"4. On the test districts: typical error (RMSE) ${err:.0f}k; predicting the average for everyone: "
          f"${np.sqrt(np.mean((y.mean() - yt) ** 2)):.0f}k")
    print(f"   A district with median income $50,000 (x = 5): predicted ${W * 5 + B:.0f}k")
