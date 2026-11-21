"""Choose the degree M and the penalty lambda by 5-fold cross-validation (Bishop, section 1.2.6),
then measure the chosen model ONCE on the test set."""
import argparse
from pathlib import Path
import torch
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from data import load_splits
from train import fit, rmse

DEGREES = range(1, 9)
LAMBDAS = [0.0, 0.1, 10.0]


def cross_val(x, t, degree, lam, folds=5):
    idx = torch.arange(len(x))
    errors = []
    for k in range(folds):
        held = idx % folds == k
        model = fit(x[~held], t[~held], degree, lam)
        errors.append(rmse(model, x[held], t[held]))
    return sum(errors) / folds


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-train", type=int, default=None, help="use only this many cars for training")
    args = ap.parse_args()
    splits, (mean, std) = load_splits()
    x = torch.cat([splits["train"][0], splits["val"][0]])
    t = torch.cat([splits["train"][1], splits["val"][1]])
    if args.n_train:
        x, t = x[:args.n_train], t[:args.n_train]
    print(f"choosing with {len(x)} cars\n")
    print("degree " + "".join(f"  lambda={lam:<5g}" for lam in LAMBDAS))
    scores = {}
    for degree in DEGREES:
        row = [cross_val(x, t, degree, lam) for lam in LAMBDAS]
        scores.update({(degree, lam): s for lam, s in zip(LAMBDAS, row)})
        print(f"{degree:6d} " + "".join(f"  {s:12.2f}" for s in row))

    best = min(scores, key=scores.get)
    # Several models score almost the same. Prefer the simplest one within 1% of the best:
    # lowest degree first, then the strongest penalty.
    near = [k for k in scores if scores[k] <= 1.01 * scores[best]]
    degree, lam = min(near, key=lambda k: (k[0], -k[1]))
    model = fit(x, t, degree, lam)
    x_test, t_test = splits["test"]
    print(f"\nbest score: degree {best[0]}, lambda {best[1]:g} (cross-validation RMSE {scores[best]:.2f})")
    print(f"chosen (simplest within 1%): degree {degree}, lambda {lam:g} (cross-validation RMSE {scores[degree, lam]:.2f})")
    print(f"test RMSE of the chosen model: {rmse(model, x_test, t_test):.2f} mpg")
    print(f"test RMSE of 'always guess the average': {((t_test - t.mean()) ** 2).mean().sqrt():.2f} mpg")

    Path("outputs").mkdir(exist_ok=True)
    grid = torch.linspace(x.min(), x.max(), 200)
    with torch.no_grad():
        plt.scatter(x * std + mean, t, s=8, alpha=0.5, label="cars used for fitting")
        plt.plot(grid * std + mean, model(grid), "r", label=f"chosen model (M={degree})")
    plt.xlabel("horsepower"); plt.ylabel("miles per gallon"); plt.legend()
    name = f"outputs/fit_n{len(x)}.png"
    plt.savefig(name, dpi=120)
    print("saved", name)
