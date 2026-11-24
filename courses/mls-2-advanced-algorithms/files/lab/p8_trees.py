"""Project 8 (days 10-11): decision trees. Information gain by hand for one split, then a tree, a random forest and
gradient boosting against the neural network."""
import time

import numpy as np
import tensorflow as tf
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.tree import DecisionTreeClassifier

from digits import X_test, X_train, y_test, y_train
from p5_bias_variance import net


def entropy(y):
    p = np.bincount(y, minlength=10) / len(y)
    p = p[p > 0]
    return float(-(p * np.log2(p)).sum())


if __name__ == "__main__":
    H = entropy(y_train)
    best = max(((H - (np.mean(X_train[:, j] > t) * entropy(y_train[X_train[:, j] > t]) +
                      np.mean(X_train[:, j] <= t) * entropy(y_train[X_train[:, j] <= t])), j, t)
                for j in range(64) for t in (0.25, 0.5, 0.75)
                if 0 < np.sum(X_train[:, j] > t) < len(y_train)))
    gain, j, t = best
    print(f"1. Entropy of the labels: {H:.2f} bits (ten even classes would be {np.log2(10):.2f})")
    print(f"   best first split by information gain: pixel {j} (row {j // 8}, column {j % 8}) > {t}, gain {gain:.2f} bits")
    tree = DecisionTreeClassifier(criterion="entropy", random_state=0).fit(X_train, y_train)
    f0, t0 = tree.tree_.feature[0], tree.tree_.threshold[0]
    g0 = H - (np.mean(X_train[:, f0] > t0) * entropy(y_train[X_train[:, f0] > t0]) +
              np.mean(X_train[:, f0] <= t0) * entropy(y_train[X_train[:, f0] <= t0]))
    print(f"   scikit-learn tries every threshold, not only three, and picks pixel {f0} > {t0:.3f}, gain {g0:.2f} bits\n")
    print("2. On the test digits:")
    for name, mk in [("one decision tree", lambda: DecisionTreeClassifier(random_state=0)),
                     ("random forest, 300 trees", lambda: RandomForestClassifier(300, random_state=0)),
                     ("gradient boosting", lambda: HistGradientBoostingClassifier(random_state=0))]:
        s = time.perf_counter()
        acc = mk().fit(X_train, y_train).score(X_test, y_test)
        print(f"   {name:26} {acc:6.1%}   ({time.perf_counter() - s:.1f} s)")
    tf.random.set_seed(0)
    s = time.perf_counter()
    m = net(1e-3)
    m.fit(X_train, y_train, epochs=150, batch_size=32, verbose=0)
    print(f"   {'neural network (project 5)':26} {m.evaluate(X_test, y_test, verbose=0)[1]:6.1%}   ({time.perf_counter() - s:.1f} s)")
    print("\n   One tree overfits; many trees vote it away. On 64 clean pixels, ensembles of trees match or beat a small")
    print("   network, and train in seconds. Networks pull ahead on bigger images, sound and text.")
