"""A multilayer perceptron of any width and depth (Bishop, section 6.2)."""
from torch import nn


def mlp(hidden, D=784, K=10):
    """hidden=[] gives softmax regression; hidden=[256, 256] gives two hidden layers of 256 ReLU units."""
    layers, width = [], D
    for h in hidden:
        layers += [nn.Linear(width, h), nn.ReLU()]
        width = h
    layers.append(nn.Linear(width, K))
    return nn.Sequential(*layers)


def count_parameters(model):
    return sum(p.numel() for p in model.parameters())
