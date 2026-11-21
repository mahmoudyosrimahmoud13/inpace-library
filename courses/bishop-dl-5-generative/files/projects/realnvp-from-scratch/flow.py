"""Real NVP, a coupling flow (Bishop, section 18.1), written from scratch.

The flow maps data x to latent z, one coupling layer at a time. In each layer, half of the coordinates pass through
unchanged and decide how the other half is scaled and shifted:  z_B = exp(s(x_A)) * x_B + t(x_A).
That is easy to invert, and its Jacobian is triangular, so log |det J| is just the sum of s (equation 18.14)."""
import math
import torch
from torch import nn


class Coupling(nn.Module):
    def __init__(self, flip, hidden=64):
        super().__init__()
        self.flip = flip                                  # which coordinate stays fixed in this layer
        self.net = nn.Sequential(nn.Linear(1, hidden), nn.ReLU(), nn.Linear(hidden, hidden), nn.ReLU(),
                                 nn.Linear(hidden, 2))     # outputs a scale s and a shift t

    def split(self, v):
        a, b = v[:, :1], v[:, 1:]
        return (b, a) if self.flip else (a, b)

    def join(self, a, b):
        return torch.cat([b, a], 1) if self.flip else torch.cat([a, b], 1)

    def forward(self, x):                                 # data -> latent, and log |det J|
        a, b = self.split(x)
        s, t = self.net(a).chunk(2, 1)
        s = torch.tanh(s)                                 # keep the scales gentle: stabler training
        return self.join(a, b * torch.exp(s) + t), s.sum(1)

    def inverse(self, z):                                 # latent -> data, for sampling
        a, b = self.split(z)
        s, t = self.net(a).chunk(2, 1)
        return self.join(a, (b - t) * torch.exp(-torch.tanh(s)))


class RealNVP(nn.Module):
    def __init__(self, layers=8):
        super().__init__()
        self.layers = nn.ModuleList(Coupling(flip=i % 2 == 1) for i in range(layers))

    def log_prob(self, x):
        """log p(x) = log N(z | 0, I) + sum of log |det J| over the layers (equations 18.1 and 18.7)."""
        log_det = torch.zeros(len(x))
        for layer in self.layers:
            x, ld = layer(x)
            log_det = log_det + ld
        return -0.5 * (x ** 2).sum(1) - math.log(2 * math.pi) + log_det

    @torch.no_grad()
    def sample(self, n, generator=None):
        z = torch.randn(n, 2, generator=generator)
        for layer in reversed(self.layers):
            z = layer.inverse(z)
        return z
