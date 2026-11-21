"""California housing (1990 census): 20,640 districts, their median house value and 8 facts about them."""
from pathlib import Path
import pandas as pd
import torch

URL = "https://raw.githubusercontent.com/ageron/handson-ml2/master/datasets/housing/housing.csv"
CACHE = Path("data/housing.csv")
FEATURES = ["median_income", "housing_median_age", "rooms_per_house", "bedroom_share", "people_per_house"]


def load_table():
    if not CACHE.exists():
        CACHE.parent.mkdir(exist_ok=True)
        pd.read_csv(URL).to_csv(CACHE, index=False)
    t = pd.read_csv(CACHE).dropna()
    t["rooms_per_house"] = t.total_rooms / t.households
    t["bedroom_share"] = t.total_bedrooms / t.total_rooms
    t["people_per_house"] = (t.population / t.households).clip(upper=10)   # a few districts are hotels or dorms
    t["value"] = t.median_house_value / 1000                              # in thousands of dollars
    return t


def load_splits(seed=0):
    t = load_table()
    order = torch.randperm(len(t), generator=torch.Generator().manual_seed(seed))
    n_train, n_val = int(0.6 * len(t)), int(0.2 * len(t))
    idx = {"train": order[:n_train], "val": order[n_train:n_train + n_val], "test": order[n_train + n_val:]}
    X = torch.tensor(t[FEATURES].values, dtype=torch.float32)
    loc = torch.tensor(t[["latitude", "longitude"]].values, dtype=torch.float32)
    y = torch.tensor(t["value"].values, dtype=torch.float32)
    mean, std = X[idx["train"]].mean(0), X[idx["train"]].std(0)       # training statistics only
    X = (X - mean) / std
    return {k: (X[i], loc[i], y[i]) for k, i in idx.items()}


if __name__ == "__main__":
    t = load_table()
    print(f"{len(t)} districts; median house value from ${t.value.min():.0f}k to ${t.value.max():.0f}k")
    print(f"districts at the cap of $500k: {(t.median_house_value >= 500000).sum()}")
    print(t[FEATURES + ["value"]].describe().loc[["mean", "std"]].round(2).T)
