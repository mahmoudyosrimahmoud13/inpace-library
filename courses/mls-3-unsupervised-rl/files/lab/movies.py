"""Shared data for the Movie night project: MovieLens 100K, 100,000 ratings (1 to 5 stars) of 1,682 movies by 943
people, from GroupLens (grouplens.org). The licence doesn't allow passing the files on, so the first run downloads
them from GroupLens into data/ml-100k."""
import io
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

DIR = Path(__file__).parent / "data" / "ml-100k"
URL = "https://files.grouplens.org/datasets/movielens/ml-100k.zip"
GENRES = ["unknown", "Action", "Adventure", "Animation", "Children's", "Comedy", "Crime", "Documentary", "Drama",
          "Fantasy", "Film-Noir", "Horror", "Musical", "Mystery", "Romance", "Sci-Fi", "Thriller", "War", "Western"]


def fetch():
    if (DIR / "u.data").exists():
        return
    print("Downloading MovieLens 100K from GroupLens (5 MB)...")
    with urllib.request.urlopen(URL) as r:
        z = zipfile.ZipFile(io.BytesIO(r.read()))
    DIR.mkdir(parents=True, exist_ok=True)
    for name in ("u.data", "u.item", "u.user"):
        (DIR / name).write_bytes(z.read(f"ml-100k/{name}"))


def ratings():
    fetch()
    return pd.read_csv(DIR / "u.data", sep="\t", names=["user", "movie", "rating", "time"])


def movies():
    fetch()
    cols = ["movie", "title", "date", "video", "url"] + GENRES
    df = pd.read_csv(DIR / "u.item", sep="|", names=cols, encoding="latin-1")
    df["year"] = pd.to_datetime(df["date"], format="%d-%b-%Y", errors="coerce").dt.year
    return df.drop(columns=["video", "url", "date"])


def split(r, frac=0.9, seed=0):
    """Hold out 10% of the ratings at random: the model must predict ratings it never saw."""
    idx = np.random.default_rng(seed).permutation(len(r))
    n = int(frac * len(r))
    return r.iloc[idx[:n]], r.iloc[idx[n:]]
