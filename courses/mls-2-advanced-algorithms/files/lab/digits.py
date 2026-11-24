"""Shared data for the Digit reader project: 1,797 handwritten digits, 8x8 pixels each (scikit-learn's copy of the
UCI optical digits test set). Split once, the same way in every project."""
import os

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
import numpy as np
from sklearn.datasets import load_digits
from sklearn.model_selection import train_test_split

d = load_digits()
X = d.data.astype("float32") / 16.0            # pixel values 0..16 -> 0..1
y = d.target
X_train, X_rest, y_train, y_rest = train_test_split(X, y, test_size=0.4, random_state=0, stratify=y)
X_val, X_test, y_val, y_test = train_test_split(X_rest, y_rest, test_size=0.5, random_state=0, stratify=y_rest)


def show(img):
    """An 8x8 digit as text."""
    chars = " .:-=+*#%@"
    return "\n".join("   " + "".join(chars[min(9, int(v * 9.99))] * 2 for v in row) for row in img.reshape(8, 8))
