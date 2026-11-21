"""MNIST handwritten digits (70,000 images, 28x28) from the Hugging Face hub, as NumPy arrays."""
from pathlib import Path
import io
import numpy as np
import pandas as pd
from PIL import Image

URL = "https://huggingface.co/api/datasets/ylecun/mnist/parquet/mnist/{}/0.parquet"


def load(split):
    cache = Path(f"data/mnist_{split}.npz")
    if not cache.exists():
        cache.parent.mkdir(exist_ok=True)
        table = pd.read_parquet(URL.format(split))
        X = np.stack([np.array(Image.open(io.BytesIO(img["bytes"]))) for img in table["image"]])
        np.savez_compressed(cache, X=X, y=table["label"].values)
    d = np.load(cache)
    return d["X"].reshape(len(d["X"]), -1).astype(np.float32) / 255, d["y"].astype(np.int64)


if __name__ == "__main__":
    X, y = load("train")
    print(X.shape, y[:10], f"pixel range {X.min()}..{X.max()}")
