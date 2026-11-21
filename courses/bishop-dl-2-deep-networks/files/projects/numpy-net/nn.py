"""numpy-net: a tiny neural network library with backpropagation written by hand (Bishop, section 8.1).

Every layer has two methods:
  forward(x)      computes the output, and remembers what backward will need
  backward(g)     g = dE/d(output); stores dE/d(parameters) and returns dE/d(input)
"""
import numpy as np


class Linear:
    def __init__(self, n_in, n_out, rng):
        self.W = rng.normal(0, np.sqrt(2 / n_in), (n_in, n_out)).astype(np.float32)   # He initialization
        self.b = np.zeros(n_out, dtype=np.float32)

    def forward(self, x):
        self.x = x
        return x @ self.W + self.b

    def backward(self, g):
        self.dW = self.x.T @ g              # equation 8.10: (input z at one end) x (delta at the other end)
        self.db = g.sum(0)
        return g @ self.W.T                 # equation 8.13: deltas flow back through the same weights

    def params(self):
        return [(self.W, self.dW), (self.b, self.db)]


class ReLU:
    def forward(self, x):
        self.mask = x > 0
        return x * self.mask

    def backward(self, g):
        return g * self.mask                # h'(a) is 1 where a > 0, else 0

    def params(self):
        return []


class Tanh:
    def forward(self, x):
        self.y = np.tanh(x)
        return self.y

    def backward(self, g):
        return g * (1 - self.y ** 2)        # tanh'(a) = 1 - tanh(a)^2

    def params(self):
        return []


class SoftmaxCrossEntropy:
    """Softmax output + cross-entropy error, averaged over the batch. Its delta is (y - t) / N (equation 8.11)."""
    def forward(self, a, labels):
        a = a - a.max(1, keepdims=True)
        self.y = np.exp(a) / np.exp(a).sum(1, keepdims=True)
        self.labels = labels
        return -np.log(self.y[np.arange(len(labels)), labels] + 1e-12).mean()

    def backward(self):
        g = self.y.copy()
        g[np.arange(len(self.labels)), self.labels] -= 1
        return g / len(self.labels)


class Network:
    def __init__(self, *layers):
        self.layers = layers
        self.loss_fn = SoftmaxCrossEntropy()

    def forward(self, x):
        for layer in self.layers:
            x = layer.forward(x)
        return x

    def loss(self, x, labels):
        return self.loss_fn.forward(self.forward(x), labels)

    def backward(self):
        g = self.loss_fn.backward()
        for layer in reversed(self.layers):     # backward: the same layers, in the opposite order
            g = layer.backward(g)

    def params(self):
        return [p for layer in self.layers for p in layer.params()]


class SGD:
    def __init__(self, net, lr=0.1, momentum=0.9):
        self.net, self.lr, self.momentum = net, lr, momentum
        self.velocity = {}

    def step(self):
        for i, (p, grad) in enumerate(self.net.params()):
            v = self.momentum * self.velocity.get(i, 0) - self.lr * grad
            self.velocity[i] = v
            p += v                              # in place: the layer's own array changes
