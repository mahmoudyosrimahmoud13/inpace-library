"""Basis functions (Bishop, section 4.1.1): the model stays linear in its weights, but not in its inputs."""
import torch


class LocationBasis:
    """Gaussian bumps on a grid over California: phi_j(location) = exp(-|location - centre_j|^2 / (2 s^2))."""
    def __init__(self, n=12, s=0.5):
        lat = torch.linspace(32.5, 42.0, n)
        lon = torch.linspace(-124.3, -114.3, n)
        self.centres = torch.cartesian_prod(lat, lon)             # n * n centres, in degrees
        self.s = s

    def __call__(self, loc):
        return torch.exp(-torch.cdist(loc, self.centres) ** 2 / (2 * self.s ** 2))


def design(X, loc, basis=None):
    """The design matrix Phi (equation 4.15): a column of ones for the bias, the features, and the basis functions."""
    cols = [torch.ones(len(X), 1), X]
    if basis is not None:
        cols.append(basis(loc))
    return torch.cat(cols, dim=1)


def fit_closed_form(Phi, y, lam):
    """Regularized least squares (equation 4.27): w = (lam I + Phi^T Phi)^-1 Phi^T y. The bias is not penalized."""
    penalty = lam * torch.eye(Phi.shape[1])
    penalty[0, 0] = 0
    return torch.linalg.solve(Phi.T @ Phi + penalty, Phi.T @ y)


def rmse(Phi, w, y):
    return ((Phi @ w - y) ** 2).mean().sqrt().item()
