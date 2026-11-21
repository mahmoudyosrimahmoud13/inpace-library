"""Two networks for the inverse problem (Bishop, sections 6.4 and 6.5)."""
import math
import torch
from torch import nn


def body(hidden=128):
    return nn.Sequential(nn.Linear(2, hidden), nn.Tanh(), nn.Linear(hidden, hidden), nn.Tanh())


class Regressor(nn.Module):
    """Predicts the angles directly, trained with squared error = a Gaussian with ONE peak (section 6.4.1)."""
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(body(), nn.Linear(128, 2))

    def loss(self, x, t):
        return ((self(x) - t) ** 2).sum(1).mean()

    def forward(self, x):
        return self.net(x)


class MDN(nn.Module):
    """Mixture density network (section 6.5): the network outputs a whole distribution over the angles,
    a mixture of K Gaussians, each with its own weight pi_k, mean mu_k and width sigma_k."""
    def __init__(self, K=3):
        super().__init__()
        self.K = K
        self.body = body()
        self.head = nn.Linear(128, K * (1 + 2 + 1))          # per component: logit, 2 means, log sigma

    def params(self, x):
        out = self.head(self.body(x))
        logits, mu, log_sigma = out[:, :self.K], out[:, self.K:3 * self.K], out[:, 3 * self.K:]
        return torch.log_softmax(logits, 1), mu.reshape(-1, self.K, 2), log_sigma

    def loss(self, x, t):
        """Negative log likelihood of the mixture (equation 6.43), computed with logsumexp."""
        log_pi, mu, log_sigma = self.params(x)
        d2 = ((t[:, None, :] - mu) ** 2).sum(2)                      # (N, K)
        log_normal = -d2 / (2 * torch.exp(2 * log_sigma)) - 2 * log_sigma - math.log(2 * math.pi)
        return -torch.logsumexp(log_pi + log_normal, 1).mean()

    def forward(self, x):
        """The mean of the most probable component: one good answer, not an average of two."""
        log_pi, mu, _ = self.params(x)
        return mu[torch.arange(len(x)), log_pi.argmax(1)]
