"""Project 6 (day 8): the ML development loop. Train, look at the mistakes, add data that targets them (augmentation),
and measure again."""
import numpy as np
import tensorflow as tf
from scipy.ndimage import shift

from digits import X_train, X_val, show, y_train, y_val
from p5_bias_variance import net


def shifted(X, y, rng):
    """Each digit moved by one pixel in a random direction: new, realistic examples for free."""
    out = [shift(x.reshape(8, 8), rng.integers(-1, 2, 2), order=0).ravel() for x in X]
    return np.array(out, np.float32), y


if __name__ == "__main__":
    tf.random.set_seed(0)
    m = net()
    m.fit(X_train, y_train, epochs=60, batch_size=32, verbose=0)
    pred = m.predict(X_val, verbose=0).argmax(1)
    wrong = np.nonzero(pred != y_val)[0]
    print(f"1. Validation accuracy {np.mean(pred == y_val):.1%}: {len(wrong)} mistakes of {len(y_val)}")
    pairs = {}
    for i in wrong:
        pairs[(y_val[i], pred[i])] = pairs.get((y_val[i], pred[i]), 0) + 1
    print("   most common: " + ", ".join(f"{t} read as {p} ({n}x)" for (t, p), n in sorted(pairs.items(), key=lambda t: -t[1])[:4]))
    i = wrong[0]
    print(f"   one of them, a {y_val[i]} read as {pred[i]}:\n{show(X_val[i])}")

    rng = np.random.default_rng(0)
    Xs = [X_train] + [shifted(X_train, y_train, rng)[0] for _ in range(3)]
    Xa, ya = np.concatenate(Xs), np.concatenate([y_train] * 4)
    tf.random.set_seed(0)
    m2 = net()
    m2.fit(Xa, ya, epochs=60, batch_size=32, verbose=0)
    pred2 = m2.predict(X_val, verbose=0).argmax(1)
    print(f"\n2. Add 3 shifted copies of every training digit ({len(Xa):,} examples) and retrain: validation accuracy "
          f"{np.mean(pred2 == y_val):.1%} ({int(np.sum(pred2 != y_val))} mistakes)")
    print(f"   of the {len(wrong)} earlier mistakes, {int(np.sum(pred2[wrong] == y_val[wrong]))} are now right")
