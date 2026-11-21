"""Three 2-D data sets with shapes a single Gaussian can't describe. 2-D, so every result can be drawn."""
import math
import torch
from sklearn.datasets import make_moons


def two_moons(n, seed):
    x, _ = make_moons(n, noise=0.06, random_state=seed)
    return torch.tensor((x - [0.5, 0.25]) / [0.9, 0.5], dtype=torch.float32)


def ring(n, seed):
    g = torch.Generator().manual_seed(seed)
    a = torch.rand(n, generator=g) * 2 * math.pi
    r = 1.5 + 0.1 * torch.randn(n, generator=g)
    return torch.stack([r * torch.cos(a), r * torch.sin(a)], 1)


def eight_gaussians(n, seed):
    g = torch.Generator().manual_seed(seed)
    k = torch.randint(0, 8, (n,), generator=g).float() * (2 * math.pi / 8)
    centres = 1.6 * torch.stack([torch.cos(k), torch.sin(k)], 1)
    return centres + 0.15 * torch.randn(n, 2, generator=g)


DATASETS = {"two moons": two_moons, "ring": ring, "eight Gaussians": eight_gaussians}


def load(name):
    """5,000 training points and 2,000 test points."""
    make = DATASETS[name]
    return make(5000, 0), make(2000, 1)
