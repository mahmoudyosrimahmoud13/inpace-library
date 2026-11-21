"""14,505 news sentences where every word is tagged with its part of speech (noun, verb, ...), in the Penn Treebank
tag set (NN = noun, VBD = past-tense verb, DT = determiner, ...). From the Hugging Face hub."""
from pathlib import Path
import pandas as pd

URL = "https://huggingface.co/api/datasets/batterydata/pos_tagging/parquet/default/{}/0.parquet"


def load(split):
    cache = Path(f"data/pos_{split}.parquet")
    if not cache.exists():
        cache.parent.mkdir(exist_ok=True)
        pd.read_parquet(URL.format(split)).to_parquet(cache)
    t = pd.read_parquet(cache)
    return [(list(w), list(l)) for w, l in zip(t.words, t.labels)]


if __name__ == "__main__":
    train, test = load("train"), load("test")
    print(f"train {len(train):,} sentences ({sum(len(w) for w, _ in train):,} words), test {len(test):,} sentences")
    words, tags = train[0]
    print(" ".join(f"{w}/{t}" for w, t in zip(words[:10], tags[:10])))
