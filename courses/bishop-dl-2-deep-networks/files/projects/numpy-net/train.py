"""Train a numpy-net network on MNIST and test it."""
import numpy as np
from data import load
from nn import Linear, ReLU, Network, SGD

X, y = load("train")
X_test, y_test = load("test")
rng = np.random.default_rng(0)
net = Network(Linear(784, 128, rng), ReLU(), Linear(128, 64, rng), ReLU(), Linear(64, 10, rng))
opt = SGD(net, lr=0.05, momentum=0.9)


def accuracy(X, y):
    return (net.forward(X).argmax(1) == y).mean()


for epoch in range(1, 6):
    order = rng.permutation(len(X))
    total = 0.0
    for start in range(0, len(X), 64):
        idx = order[start:start + 64]
        total += net.loss(X[idx], y[idx]) * len(idx)
        net.backward()
        opt.step()
    print(f"epoch {epoch}: training loss {total / len(X):.4f}, training accuracy {accuracy(X, y):.4f}")
print(f"TEST accuracy: {accuracy(X_test, y_test):.4f} on {len(y_test):,} digits it never saw")
