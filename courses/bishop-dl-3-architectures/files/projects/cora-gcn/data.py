"""Cora: 2,708 machine-learning papers, the 5,429 citations between them, the words each paper uses (1,433 yes/no
features) and its topic (7 classes). From the repository of the original GCN paper (Kipf & Welling)."""
from pathlib import Path
from urllib.request import urlopen
import numpy as np
import torch

URL = "https://raw.githubusercontent.com/tkipf/pygcn/master/data/cora/"


def fetch(name):
    path = Path("data") / name
    if not path.exists():
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(urlopen(URL + name).read())
    return path


def load():
    content = np.genfromtxt(fetch("cora.content"), dtype=str)
    ids = {pid: i for i, pid in enumerate(content[:, 0])}
    X = torch.tensor(content[:, 1:-1].astype(np.float32))
    topics = sorted(set(content[:, -1]))
    y = torch.tensor([topics.index(t) for t in content[:, -1]])
    edges = [(ids[a], ids[b]) for a, b in np.genfromtxt(fetch("cora.cites"), dtype=str) if a in ids and b in ids]
    A = torch.zeros(len(ids), len(ids))
    for i, j in edges:
        A[i, j] = A[j, i] = 1.0                    # a citation links two papers, whichever direction
    return X, y, A, topics


def split(y, seed=0):
    """The usual small-label setting: only 20 labelled papers per topic for training (140 in all),
    500 for validation, 1,000 for testing."""
    order = torch.randperm(len(y), generator=torch.Generator().manual_seed(seed))
    train = torch.cat([order[y[order] == k][:20] for k in range(int(y.max()) + 1)])
    rest = order[~torch.isin(order, train)]
    return train, rest[:500], rest[500:1500]


if __name__ == "__main__":
    X, y, A, topics = load()
    print(f"{X.shape[0]} papers, {int(A.sum().item() // 2)} citation links, {X.shape[1]} word features")
    print("topics:", ", ".join(f"{t} ({(y == k).sum().item()})" for k, t in enumerate(topics)))
    print(f"average citations per paper: {A.sum(1).mean():.1f}")
    same = sum(y[i] == y[j] for i, j in A.nonzero().tolist()) / len(A.nonzero())
    print(f"links between papers of the same topic: {same:.1%}")
