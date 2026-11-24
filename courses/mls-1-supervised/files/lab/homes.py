"""Shared data for the Homes project: California districts from the 1990 census (20,640 districts, public data,
the version used in Aurélien Géron's Hands-On Machine Learning). Each row is a district; the target is its median
house value."""
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).parent / "data" / "housing.csv"


def load():
    df = pd.read_csv(DATA)
    df["total_bedrooms"] = df["total_bedrooms"].fillna(df["total_bedrooms"].median())   # 207 districts lack it
    df["rooms_per_household"] = df["total_rooms"] / df["households"]
    df["people_per_household"] = df["population"] / df["households"]
    df = df[df["median_house_value"] < 500_000]       # values were capped at 500,001: those rows are not real prices
    return df.sample(frac=1, random_state=42).reset_index(drop=True)


def split(df, frac=0.8):
    n = int(len(df) * frac)
    return df.iloc[:n], df.iloc[n:]


def scale(train, test):
    """z-score with the training set's mean and spread (never the test set's)."""
    mu, sd = train.mean(0), train.std(0)
    return (train - mu) / sd, (test - mu) / sd, mu, sd


def rmse(y, p):
    return float(np.sqrt(np.mean((np.asarray(y) - np.asarray(p)) ** 2)))
