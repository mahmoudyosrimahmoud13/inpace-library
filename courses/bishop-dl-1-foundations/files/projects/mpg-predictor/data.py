"""Download the Auto MPG data and split it into train / validation / test sets."""
from pathlib import Path
import pandas as pd
import torch

URL = "https://raw.githubusercontent.com/plotly/datasets/master/auto-mpg.csv"
CACHE = Path("data/auto-mpg.csv")


def load_table():
    if not CACHE.exists():
        CACHE.parent.mkdir(exist_ok=True)
        pd.read_csv(URL).to_csv(CACHE, index=False)
    return pd.read_csv(CACHE).dropna()          # 6 cars have no horsepower value


def load_splits(feature="horsepower", seed=0):
    """Return (x, t) tensors for train, val and test. x is standardized with the TRAIN mean and std only."""
    table = load_table()
    x = torch.tensor(table[feature].values, dtype=torch.float32)
    t = torch.tensor(table["mpg"].values, dtype=torch.float32)
    order = torch.randperm(len(x), generator=torch.Generator().manual_seed(seed))
    n_train, n_val = int(0.6 * len(x)), int(0.2 * len(x))
    parts = order[:n_train], order[n_train:n_train + n_val], order[n_train + n_val:]
    mean, std = x[parts[0]].mean(), x[parts[0]].std()
    scale = lambda v: (v - mean) / std
    return {name: (scale(x[idx]), t[idx]) for name, idx in zip(["train", "val", "test"], parts)}, (mean, std)


if __name__ == "__main__":
    splits, _ = load_splits()
    for name, (x, t) in splits.items():
        print(f"{name:5s}: {len(x):3d} cars, mean mpg {t.mean():.1f}")
