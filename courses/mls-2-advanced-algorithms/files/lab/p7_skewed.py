"""Project 7 (day 9): a rare class. 'Is it a 9?' is true for 1 digit in 10: accuracy misleads, so use precision,
recall and the threshold."""
import numpy as np
import tensorflow as tf

from digits import X_train, X_val, y_train, y_val

if __name__ == "__main__":
    yt, yv = (y_train == 9).astype(float), (y_val == 9).astype(float)
    print(f"1. {yv.mean():.0%} of validation digits are 9s. A model that always says 'not a 9' is {1 - yv.mean():.0%} accurate.")
    tf.random.set_seed(0)
    m = tf.keras.Sequential([tf.keras.Input((64,)), tf.keras.layers.Dense(16, "relu"), tf.keras.layers.Dense(1, "sigmoid")])
    m.compile("adam", "binary_crossentropy")
    m.fit(X_train, yt, epochs=40, batch_size=32, verbose=0)
    p = m.predict(X_val, verbose=0).ravel()
    print("\n2. The same model at different thresholds:")
    print(f"   {'threshold':>9} {'accuracy':>9} {'precision':>10} {'recall':>7} {'F1':>6}")
    for t in (0.1, 0.3, 0.5, 0.7, 0.9):
        pred = p >= t
        tp = np.sum(pred & (yv == 1))
        prec = tp / max(pred.sum(), 1)
        rec = tp / yv.sum()
        f1 = 2 * prec * rec / max(prec + rec, 1e-9)
        print(f"   {t:9} {np.mean(pred == yv):9.1%} {prec:10.1%} {rec:7.1%} {f1:6.2f}")
    print("\n   Precision: of the digits called 9, how many are. Recall: of the real 9s, how many were found.")
    print("   Raising the threshold buys precision with recall. Pick it for the cost of each mistake.")
