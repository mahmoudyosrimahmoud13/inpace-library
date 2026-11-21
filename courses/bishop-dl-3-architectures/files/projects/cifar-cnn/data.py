"""CIFAR-10: 60,000 colour photos, 32x32 pixels, 10 classes (Hugging Face hub)."""
from pathlib import Path
import io
import numpy as np
import pandas as pd
import torch
from PIL import Image

URL = "https://huggingface.co/api/datasets/uoft-cs/cifar10/parquet/plain_text/{}/0.parquet"
CLASSES = ["airplane", "car", "bird", "cat", "deer", "dog", "frog", "horse", "ship", "truck"]
MEAN = torch.tensor([0.491, 0.482, 0.447]).view(1, 3, 1, 1)
STD = torch.tensor([0.247, 0.243, 0.262]).view(1, 3, 1, 1)


def load(split):
    """split: 'train' (50,000) or 'test' (10,000). Returns uint8 images (N, 3, 32, 32) and labels."""
    cache = Path(f"data/cifar10_{split}.npz")
    if not cache.exists():
        cache.parent.mkdir(exist_ok=True)
        table = pd.read_parquet(URL.format(split))
        X = np.stack([np.array(Image.open(io.BytesIO(img["bytes"])).convert("RGB")) for img in table["img"]])
        np.savez(cache, X=X.transpose(0, 3, 1, 2), y=table["label"].values)
    d = np.load(cache)
    return torch.from_numpy(d["X"]), torch.from_numpy(d["y"]).long()


def normalize(x_uint8):
    """uint8 images -> floats with mean 0 and standard deviation 1 per colour channel (section 7.4.1)."""
    return (x_uint8.float() / 255 - MEAN) / STD


def load_splits():
    X, y = load("train")
    order = torch.randperm(len(X), generator=torch.Generator().manual_seed(0))
    val, train = order[:5000], order[5000:]
    return (X[train], y[train]), (X[val], y[val]), load("test")


if __name__ == "__main__":
    (xtr, ytr), (xva, yva), (xte, yte) = load_splits()
    print(f"train {tuple(xtr.shape)}, validation {len(xva)}, test {len(xte)}")
    print("per class in training:", torch.bincount(ytr).tolist())
