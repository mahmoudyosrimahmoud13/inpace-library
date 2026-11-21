"""Three density models for 'normal' hours (Bishop, chapter 3). Each returns log p(x) for new points."""
import math
import torch


class Gaussian:
    """A multivariate Gaussian fitted by maximum likelihood (section 3.2.7): sample mean and covariance."""
    def fit(self, X):
        self.mu = X.mean(0)
        self.cov = torch.cov(X.T, correction=0)
        return self

    def log_prob(self, X):
        return torch.distributions.MultivariateNormal(self.mu, self.cov).log_prob(X)


class Independent(Gaussian):
    """The same, but assuming temperature and change are independent (a diagonal covariance)."""
    def fit(self, X):
        super().fit(X)
        self.cov = torch.diag(torch.diag(self.cov))
        return self


class KDE:
    """Kernel density estimate (section 3.5.2): a small Gaussian bump on every training point.
    Inputs are standardized first so one width h suits both features."""
    def __init__(self, h):
        self.h = h

    def fit(self, X):
        self.mean, self.std = X.mean(0), X.std(0)
        self.points = (X - self.mean) / self.std
        return self

    def log_prob(self, X):
        Z = (X - self.mean) / self.std
        d2 = torch.cdist(Z, self.points) ** 2                         # squared distance to every training point
        D = X.shape[1]
        log_kernel = -d2 / (2 * self.h ** 2) - D / 2 * math.log(2 * math.pi * self.h ** 2)
        return torch.logsumexp(log_kernel, dim=1) - math.log(len(self.points)) - torch.log(self.std).sum()
