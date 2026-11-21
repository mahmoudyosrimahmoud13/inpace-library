"""Fit one polynomial by minimizing the regularized sum-of-squares error (Bishop, equation 1.4)."""
import argparse
import torch
from data import load_splits
from model import Polynomial


def fit(x, t, degree, lam=0.0, steps=500):
    torch.manual_seed(0)
    model = Polynomial(degree)
    opt = torch.optim.LBFGS(model.parameters(), lr=1, max_iter=steps, line_search_fn="strong_wolfe")

    def closure():
        opt.zero_grad()
        error = 0.5 * ((model(x) - t) ** 2).sum()
        penalty = 0.5 * lam * (model.linear.weight ** 2).sum()   # the bias is not penalized
        loss = error + penalty
        loss.backward()
        return loss

    opt.step(closure)
    return model


def rmse(model, x, t):
    with torch.no_grad():
        return ((model(x) - t) ** 2).mean().sqrt().item()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--degree", type=int, default=2)
    ap.add_argument("--lam", type=float, default=0.0)
    args = ap.parse_args()
    splits, _ = load_splits()
    model = fit(*splits["train"], args.degree, args.lam)
    for name in ["train", "val"]:
        print(f"degree {args.degree}, lambda {args.lam:g}: {name} RMSE {rmse(model, *splits[name]):.2f} mpg")
