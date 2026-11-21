"""Download the SMS Spam Collection (5,574 real text messages) and split it."""
from pathlib import Path
import re
import pandas as pd
import torch

URL = "https://huggingface.co/api/datasets/ucirvine/sms_spam/parquet/plain_text/train/0.parquet"
CACHE = Path("data/sms_spam.parquet")


def load_table():
    if not CACHE.exists():
        CACHE.parent.mkdir(exist_ok=True)
        pd.read_parquet(URL).to_parquet(CACHE)
    return pd.read_parquet(CACHE)                # columns: sms (the text), label (1 = spam)


def tokenize(text):
    """Lower-case words and numbers. 'FREE entry!! Call 0800' -> ['free', 'entry', 'call', '0800']"""
    return re.findall(r"[a-z0-9£$']+", text.lower())


def load_splits(seed=0):
    table = load_table()
    order = torch.randperm(len(table), generator=torch.Generator().manual_seed(seed)).tolist()
    n_train, n_val = int(0.6 * len(order)), int(0.2 * len(order))
    pick = lambda idx: (table.sms.iloc[idx].tolist(), torch.tensor(table.label.iloc[idx].values))
    return pick(order[:n_train]), pick(order[n_train:n_train + n_val]), pick(order[n_train + n_val:])


class Vocabulary:
    """Maps words to columns. Only words seen at least `min_count` times in TRAINING messages are kept."""

    def __init__(self, texts, min_count=2):
        counts = {}
        for text in texts:
            for w in tokenize(text):
                counts[w] = counts.get(w, 0) + 1
        self.words = sorted(w for w, c in counts.items() if c >= min_count)
        self.index = {w: i for i, w in enumerate(self.words)}

    def counts(self, texts):
        """Bag of words: one row per message, one column per word, entry = how many times it appears."""
        X = torch.zeros(len(texts), len(self.words))
        for row, text in enumerate(texts):
            for w in tokenize(text):
                if w in self.index:
                    X[row, self.index[w]] += 1
        return X


if __name__ == "__main__":
    (train_x, train_t), (val_x, val_t), (test_x, test_t) = load_splits()
    print(f"train {len(train_x)}, val {len(val_x)}, test {len(test_x)} messages")
    print(f"spam share in training: {train_t.float().mean():.1%}")
    vocab = Vocabulary(train_x)
    print(f"vocabulary: {len(vocab.words)} words")
    spam = next(x for x, t in zip(train_x, train_t) if t == 1).strip()
    print("a spam message:", spam[:70])
    print("its tokens:    ", tokenize(spam)[:10])
