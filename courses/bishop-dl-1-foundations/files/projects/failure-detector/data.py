"""Temperature of a large industrial machine, every 5 minutes for 11 weeks (Numenta Anomaly Benchmark).
Engineers labelled four periods around known failures. We turn the readings into one point per hour."""
from pathlib import Path
from urllib.request import urlopen
import json
import pandas as pd
import torch

BASE = "https://raw.githubusercontent.com/numenta/NAB/master/"
FILE = "realKnownCause/machine_temperature_system_failure.csv"
CACHE = Path("data/machine_temperature.csv")
LABELS = Path("data/combined_windows.json")
TRAIN = ("2013-12-18", "2014-01-20")          # 33 days with no labelled failure: what "normal" looks like


def load_readings():
    if not CACHE.exists():
        CACHE.parent.mkdir(exist_ok=True)
        CACHE.write_bytes(urlopen(BASE + "data/" + FILE).read())
    return pd.read_csv(CACHE, parse_dates=["timestamp"]).set_index("timestamp")["value"]


def failure_windows():
    if not LABELS.exists():
        LABELS.parent.mkdir(exist_ok=True)
        LABELS.write_bytes(urlopen(BASE + "labels/combined_windows.json").read())
    labels = json.loads(LABELS.read_text())[FILE]
    return [(pd.Timestamp(a), pd.Timestamp(b)) for a, b in labels]


def hourly_features():
    """Each hour -> (mean temperature, change since the previous hour)."""
    hourly = load_readings().resample("1h").mean().dropna()
    table = pd.DataFrame({"temp": hourly, "change": hourly.diff()}).dropna()
    return table


if __name__ == "__main__":
    table = hourly_features()
    print(f"{len(table)} hours from {table.index[0]:%Y-%m-%d} to {table.index[-1]:%Y-%m-%d}")
    train = table.loc[TRAIN[0]:TRAIN[1]]
    print(f"training hours (normal operation): {len(train)}")
    print(train.describe().loc[["mean", "std", "min", "max"]].round(2))
    for a, b in failure_windows():
        print(f"labelled failure window: {a:%Y-%m-%d %H:%M} to {b:%Y-%m-%d %H:%M}")
