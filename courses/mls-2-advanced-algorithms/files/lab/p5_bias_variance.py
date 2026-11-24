"""Project 5 (days 6-7): diagnose the model. Learning curves (more data?) and a regularization sweep (simpler model?),
always on validation data, and the test set touched once at the end."""
import numpy as np
import tensorflow as tf

from digits import X_test, X_train, X_val, y_test, y_train, y_val


def net(lam=0.0, width=64):
    reg = tf.keras.regularizers.l2(lam) if lam else None
    m = tf.keras.Sequential([tf.keras.Input((64,)), tf.keras.layers.Dense(width, "relu", kernel_regularizer=reg),
                             tf.keras.layers.Dense(width, "relu", kernel_regularizer=reg), tf.keras.layers.Dense(10)])
    m.compile(tf.keras.optimizers.Adam(1e-3), tf.keras.losses.SparseCategoricalCrossentropy(from_logits=True),
              metrics=["accuracy"])
    return m


def errors(m, n):
    tf.random.set_seed(0)
    m.fit(X_train[:n], y_train[:n], epochs=150, batch_size=32, verbose=0)
    return 1 - m.evaluate(X_train[:n], y_train[:n], verbose=0)[1], 1 - m.evaluate(X_val, y_val, verbose=0)[1]


if __name__ == "__main__":
    print("1. Learning curve: a 64-64 network trained for 150 epochs on more and more digits")
    print(f"   {'training digits':>16} {'train error':>12} {'validation error':>17}")
    for n in (50, 100, 250, 500, 1078):
        tr, va = errors(net(), n)
        print(f"   {n:16} {tr:12.1%} {va:17.1%}")
    print("   Train error stays at 0 while validation error falls with data: high variance, fixed by more data.\n")
    print("2. Regularization sweep on 250 digits (pick lambda on validation, never on test):")
    best = None
    for lam in (0, 1e-4, 1e-3, 1e-2, 1e-1):
        tr, va = errors(net(lam), 250)
        print(f"   lambda {lam:<7} train error {tr:6.1%}   validation error {va:6.1%}")
        if best is None or va < best[1]:
            best = (lam, va)
    m = net(best[0])
    errors(m, 1078)
    print(f"\n3. Chosen lambda {best[0]}, retrained on all training digits. Test error, measured once: "
          f"{1 - m.evaluate(X_test, y_test, verbose=0)[1]:.1%}")
