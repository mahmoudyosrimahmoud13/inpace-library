"""Project 2 (day 3): backpropagation by hand for a small network, checked against numerical gradients and
TensorFlow's automatic differentiation. Task: is this digit a zero?"""
import numpy as np
import tensorflow as tf

from digits import X_train, y_train

rng = np.random.default_rng(0)
X, y = X_train[:200].astype(np.float64), (y_train[:200] == 0).astype(np.float64)[:, None]
W1, b1 = rng.normal(0, 0.3, (64, 16)), np.zeros(16)
W2, b2 = rng.normal(0, 0.3, (16, 1)), np.zeros(1)


def sigmoid(z):
    return 1 / (1 + np.exp(-z))


def loss(W1, b1, W2, b2):
    p = sigmoid(np.maximum(0, X @ W1 + b1) @ W2 + b2)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def backprop(W1, b1, W2, b2):
    """The chain rule, layer by layer, from the loss back to every weight."""
    z1 = X @ W1 + b1
    a1 = np.maximum(0, z1)                       # ReLU
    p = sigmoid(a1 @ W2 + b2)
    m = len(X)
    dz2 = (p - y) / m                            # sigmoid + log loss: the gradient is simply p - y
    dW2, db2 = a1.T @ dz2, dz2.sum(0)
    dz1 = (dz2 @ W2.T) * (z1 > 0)                # back through W2, then through ReLU
    return X.T @ dz1, dz1.sum(0), dW2, db2


if __name__ == "__main__":
    grads = backprop(W1, b1, W2, b2)
    print(f"1. Loss of the untrained network: {loss(W1, b1, W2, b2):.4f}")
    eps, worst = 1e-6, 0.0
    params = [W1, b1, W2, b2]
    for name, P, G in zip(["W1", "b1", "W2", "b2"], params, grads):
        for idx in [(3, 2), (40, 7)] if P.ndim == 2 and P.shape[0] > 40 else [tuple(0 for _ in P.shape)]:
            old = P[idx]
            P[idx] = old + eps
            up = loss(*params)
            P[idx] = old - eps
            down = loss(*params)
            P[idx] = old
            num = (up - down) / (2 * eps)
            worst = max(worst, abs(num - G[idx]))
            print(f"2. d loss / d {name}{list(idx)}: backprop {G[idx]: .8f}   numerical {num: .8f}")
    print(f"   largest difference: {worst:.1e}  (gradient check passed: {worst < 1e-7})")

    tv = [tf.Variable(p) for p in params]
    with tf.GradientTape() as tape:
        a1 = tf.nn.relu(X @ tv[0] + tv[1])
        p = tf.sigmoid(a1 @ tv[2] + tv[3])
        l = -tf.reduce_mean(y * tf.math.log(p) + (1 - y) * tf.math.log(1 - p))
    tg = tape.gradient(l, tv)
    print(f"3. TensorFlow's automatic gradients equal yours: {all(np.allclose(a, b.numpy()) for a, b in zip(grads, tg))}")
