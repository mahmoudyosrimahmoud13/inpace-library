"""A polynomial regression model: y(x, w) = w0 + w1 x + ... + wM x^M  (Bishop, section 1.2)."""
import torch
from torch import nn


class Polynomial(nn.Module):
    def __init__(self, degree):
        super().__init__()
        self.degree = degree
        self.linear = nn.Linear(degree, 1)        # the bias is w0, the weights are w1..wM

    def features(self, x):
        return torch.stack([x ** j for j in range(1, self.degree + 1)], dim=1)

    def forward(self, x):
        return self.linear(self.features(x)).squeeze(1)
