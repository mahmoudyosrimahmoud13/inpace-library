"""IMDB movie reviews: 50,000 reviews labelled positive or negative (Stanford, via the Hugging Face hub)."""
from pathlib import Path
import re
from collections import Counter
import pandas as pd
import torch

URL = "https://huggingface.co/api/datasets/stanfordnlp/imdb/parquet/plain_text/{}/0.parquet"
MAX_LEN = 200                                     # keep the first 200 words of each review


def load_table(split):
    cache = Path(f"data/imdb_{split}.parquet")
    if not cache.exists():
        cache.parent.mkdir(exist_ok=True)
        pd.read_parquet(URL.format(split)).to_parquet(cache)
    return pd.read_parquet(cache)                  # columns: text, label (1 = positive)


def words(text):
    return re.findall(r"[a-z']+", text.lower().replace("<br />", " "))


class Vocab:
    """The 20,000 most common training words get an id; 0 is padding, 1 is 'unknown word'."""
    def __init__(self, texts, size=20000):
        counts = Counter(w for t in texts for w in words(t))
        self.itos = ["<pad>", "<unk>"] + [w for w, _ in counts.most_common(size - 2)]
        self.stoi = {w: i for i, w in enumerate(self.itos)}

    def encode(self, texts):
        ids = torch.zeros(len(texts), MAX_LEN, dtype=torch.long)
        for row, t in enumerate(texts):
            seq = [self.stoi.get(w, 1) for w in words(t)][:MAX_LEN]
            ids[row, :len(seq)] = torch.tensor(seq, dtype=torch.long)
        return ids


def load_splits():
    train, test = load_table("train"), load_table("test")
    order = torch.randperm(len(train), generator=torch.Generator().manual_seed(0)).tolist()
    tr, va = train.iloc[order[2500:]], train.iloc[order[:2500]]
    vocab = Vocab(tr.text)
    pack = lambda t: (vocab.encode(t.text.tolist()), torch.tensor(t.label.values))
    return vocab, pack(tr), pack(va), pack(test)


if __name__ == "__main__":
    vocab, (xtr, ytr), (xva, yva), (xte, yte) = load_splits()
    print(f"train {len(xtr)}, validation {len(xva)}, test {len(xte)} reviews; positive share {ytr.float().mean():.2f}")
    print("first review, first 12 words:", " ".join(vocab.itos[i] for i in xtr[0, :12]))
    print(f"words outside the vocabulary in test: {(xte == 1).sum() / (xte > 0).sum():.1%}")
