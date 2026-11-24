"""Project 2: check every batch of data before it can reach a model, and version the data like code."""
import hashlib
import json
import shutil
from pathlib import Path

import pandas as pd

from common import DATA, HERE

STORE = HERE / ".datastore"            # content-addressed copies: the idea behind DVC
LOCK = HERE / "data.lock.json"         # which version of each file the project uses (commit this file to git)

RULES = {   # column: (lowest allowed, highest allowed)
    "season": (1, 4), "yr": (0, 1), "mnth": (1, 12), "hr": (0, 23), "holiday": (0, 1), "weekday": (0, 6),
    "workingday": (0, 1), "weathersit": (1, 4), "temp": (0, 1), "atemp": (0, 1), "hum": (0, 1),
    "windspeed": (0, 1), "casual": (0, None), "registered": (0, None), "cnt": (0, None)}


def validate(df):
    """Return a list of problems; an empty list means the batch may be used."""
    problems = []
    missing = [c for c in ["dteday", *RULES] if c not in df.columns]
    if missing:
        return [f"missing columns: {missing}"]
    for col, (lo, hi) in RULES.items():
        if not pd.api.types.is_numeric_dtype(df[col]):
            problems.append(f"{col}: not numeric")
            continue
        bad = df[col].isna() | (df[col] < lo) | ((df[col] > hi) if hi is not None else False)
        if bad.any():
            problems.append(f"{col}: {int(bad.sum())} values outside [{lo}, {hi if hi is not None else '...'}], "
                            f"e.g. {df.loc[bad, col].iloc[0]}")
    dup = df.duplicated(["dteday", "hr"]).sum()
    if dup:
        problems.append(f"{dup} duplicated hours")
    if "cnt" in df and ((df["casual"] + df["registered"]) != df["cnt"]).any():
        problems.append("casual + registered != cnt in some rows")
    return problems


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def snapshot(path, note=""):
    """Save a copy of the file under its hash, and record that hash as the version in use."""
    h = file_hash(path)
    STORE.mkdir(exist_ok=True)
    target = STORE / h
    if not target.exists():
        shutil.copyfile(path, target)
    lock = json.loads(LOCK.read_text()) if LOCK.exists() else {}
    history = lock.get(Path(path).name, {}).get("history", [])
    if not history or history[-1]["hash"] != h:
        history.append({"hash": h, "rows": sum(1 for _ in open(path)) - 1, "note": note})
    lock[Path(path).name] = {"hash": h, "history": history}
    LOCK.write_text(json.dumps(lock, indent=1))
    return h


def checkout(name, h, to):
    """Get back any version you ever snapshotted."""
    shutil.copyfile(STORE / h, to)


if __name__ == "__main__":
    df = pd.read_csv(DATA)
    print(f"1. The real data: {validate(df) or 'no problems'}")

    bad = df.head(500).copy()
    bad.loc[3, "temp"] = 21.5                        # Celsius from a new weather feed
    bad.loc[7, "cnt"] = -4                           # a bug upstream
    bad = pd.concat([bad, bad.iloc[[10]]])           # the same hour loaded twice
    bad.loc[12, "hum"] = None                        # a sensor gap
    print("2. A broken batch:")
    for p in validate(bad):
        print("   -", p)
    print(f"   A batch without 'hum': {validate(df.drop(columns=['hum']))}")

    print("\n3. Versioning the data")
    shutil.rmtree(STORE, ignore_errors=True)       # start the demonstration from an empty store
    LOCK.unlink(missing_ok=True)
    work = HERE / "data" / "hour_work.csv"
    shutil.copyfile(DATA, work)
    v1 = snapshot(work, "two years of hours")
    extra = df.tail(24).copy()
    extra["dteday"] = "2013-01-01"
    pd.concat([df, extra]).to_csv(work, index=False)
    v2 = snapshot(work, "one more day arrives")
    v2_again = snapshot(work, "no change")
    print(f"   v1 = {v1}, v2 = {v2}, snapshot again without changes = {v2_again} (same, no new copy)")
    print(f"   data.lock.json: {json.loads(LOCK.read_text())['hour_work.csv']['history']}")
    checkout("hour_work.csv", v1, work)
    print(f"   checkout v1 -> hash {file_hash(work)}, {sum(1 for _ in open(work)) - 1:,} rows: back exactly")
    print(f"   store: {sorted(p.name for p in STORE.iterdir())}, "
          f"{sum(p.stat().st_size for p in STORE.iterdir()) / 1e6:.1f} MB")
    work.unlink()
