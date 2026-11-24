"""Project 4 (day 5): softmax for ten classes, the numerically safe way, and Adam against plain gradient descent."""
import numpy as np
import tensorflow as tf

from digits import X_train, X_val, y_train, y_val


def softmax(z):
    z = z - z.max(axis=1, keepdims=True)            # subtracting the max changes nothing mathematically
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


if __name__ == "__main__":
    z = np.array([[2.0, 1.0, 0.1], [1000.0, 999.0, 998.0]])
    with np.errstate(over="ignore", invalid="ignore"):
        naive = np.exp(z) / np.exp(z).sum(1, keepdims=True)
    print(f"1. Naive softmax of [1000, 999, 998]: {naive[1]}  <- overflow")
    print(f"   Safe softmax:                     {np.round(softmax(z)[1], 3)} (same as for [2, 1, 0]: "
          f"{np.round(softmax(np.array([[2.0, 1.0, 0.0]]))[0], 3)})")
    print("   That's why Keras wants from_logits=True: it combines softmax and the loss safely.\n")
    print("2. Ten digits, 64 -> 25 -> 15 -> 10, ReLU, validation accuracy by epoch:")
    for name, opt in [("gradient descent (SGD, lr 0.01)", tf.keras.optimizers.SGD(0.01)),
                      ("SGD, lr 0.1", tf.keras.optimizers.SGD(0.1)),
                      ("Adam, lr 0.001", tf.keras.optimizers.Adam(1e-3))]:
        tf.random.set_seed(0)
        m = tf.keras.Sequential([tf.keras.Input((64,)), tf.keras.layers.Dense(25, "relu"),
                                 tf.keras.layers.Dense(15, "relu"), tf.keras.layers.Dense(10)])
        m.compile(opt, tf.keras.losses.SparseCategoricalCrossentropy(from_logits=True), metrics=["accuracy"])
        acc = m.fit(X_train, y_train, epochs=20, batch_size=32, verbose=0, validation_data=(X_val, y_val)).history["val_accuracy"]
        print(f"   {name:32} epoch 1 {acc[0]:6.1%}  epoch 5 {acc[4]:6.1%}  epoch 20 {acc[-1]:6.1%}")
    probs = tf.nn.softmax(m(X_val[:1])).numpy()[0]
    print(f"\n3. The Adam model on one validation digit (a {y_val[0]}): "
          + ", ".join(f"{d}: {p:.2f}" for d, p in sorted(enumerate(probs), key=lambda t: -t[1])[:3]))
