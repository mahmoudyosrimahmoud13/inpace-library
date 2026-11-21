"""Predict the fuel use of a new car from its horsepower, with the chosen model (degree 2, lambda 0.1)."""
import argparse
import torch
from data import load_splits
from train import fit

ap = argparse.ArgumentParser()
ap.add_argument("horsepower", type=float, nargs="+")
args = ap.parse_args()

splits, (mean, std) = load_splits()
x = torch.cat([splits["train"][0], splits["val"][0]])
t = torch.cat([splits["train"][1], splits["val"][1]])
model = fit(x, t, degree=2, lam=0.1)
with torch.no_grad():
    for hp in args.horsepower:
        mpg = model(torch.tensor([(hp - mean) / std])).item()
        print(f"{hp:5.0f} hp -> {mpg:4.1f} mpg  ({235.2 / mpg:4.1f} litres per 100 km)")
