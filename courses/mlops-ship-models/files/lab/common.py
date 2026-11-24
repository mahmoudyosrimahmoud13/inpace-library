"""Shared pieces of Bikecast: load the data, split it by time, build features, score predictions."""
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
DATA = HERE / "data" / "hour.csv"
# No month or season: with one year of history they only memorize last year's level (see project 1's lesson).
FEATURES = ["hr", "weekday", "workingday", "holiday", "weathersit", "temp", "atemp", "hum", "windspeed",
            "last_week_avg"]
TARGET = "cnt"


def load(path=DATA):
    """Hourly bike rentals in Washington D.C., 2011-2012 (UCI Bike Sharing, CC BY 4.0). One row per hour."""
    df = pd.read_csv(path, parse_dates=["dteday"])
    df["time"] = df["dteday"] + pd.to_timedelta(df["hr"], unit="h")
    return add_history(df)


def add_history(df):
    """One feature from the past, so the model sees demand growing: the average hourly count over the 7 days
    before this hour. It's known at prediction time. (A few hours are missing from the data, so it's computed by
    time, not by row.)"""
    counts = df.set_index("time")[TARGET]
    week = pd.Timedelta(days=7)
    df = df.copy()
    avg = counts.rolling("7D", closed="left").mean()
    df["last_week_avg"] = avg.reindex(df["time"]).to_numpy()
    df.loc[df["time"] < df["time"].min() + week, "last_week_avg"] = np.nan
    return df


def between(df, start, end):
    """Rows from `start` up to, but not including, `end` (dates like "2012-03-01")."""
    return df[(df["time"] >= start) & (df["time"] < end)]


def score(y, pred):
    y, pred = np.asarray(y, float), np.asarray(pred, float)
    return {"mae": float(np.mean(np.abs(y - pred))), "rmse": float(np.sqrt(np.mean((y - pred) ** 2))),
            "bias": float(np.mean(pred - y))}
