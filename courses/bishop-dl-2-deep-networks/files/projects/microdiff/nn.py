"""A neural network made of nothing but Value objects."""
import random
from engine import Value


class Neuron:
    def __init__(self, n_in, act=True):
        self.w = [Value(random.gauss(0, n_in ** -0.5)) for _ in range(n_in)]
        self.b = Value(0.0)
        self.act = act

    def __call__(self, x):
        a = sum((wi * xi for wi, xi in zip(self.w, x)), self.b)
        return a.tanh() if self.act else a

    def parameters(self):
        return self.w + [self.b]


class MLP:
    def __init__(self, sizes):
        self.layers = [[Neuron(a, act=(i < len(sizes) - 2)) for _ in range(b)]
                       for i, (a, b) in enumerate(zip(sizes, sizes[1:]))]

    def __call__(self, x):
        for layer in self.layers:
            x = [neuron(x) for neuron in layer]
        return x[0]

    def parameters(self):
        return [p for layer in self.layers for n in layer for p in n.parameters()]
