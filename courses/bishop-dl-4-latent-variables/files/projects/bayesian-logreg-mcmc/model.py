"""Bayesian logistic regression on the breast cancer data: the posterior over weights we want to sample from."""
import torch
from sklearn.datasets import load_breast_cancer

d = load_breast_cancer()
X = torch.tensor(d.data, dtype=torch.float64)
t = torch.tensor(d.target, dtype=torch.float64)                  # 1 = benign, 0 = malignant
order = torch.randperm(len(X), generator=torch.Generator().manual_seed(0))
train, test = order[:400], order[400:]
mean, std = X[train].mean(0), X[train].std(0)
X = torch.cat([torch.ones(len(X), 1, dtype=torch.float64), (X - mean) / std], 1)   # bias column + 30 features
D = X.shape[1]
PRIOR_STD = 1.0


def log_posterior(w):
    """log p(w | data) up to a constant: Bernoulli log likelihood of the training set + Gaussian prior."""
    a = X[train] @ w
    log_lik = (t[train] * a - torch.nn.functional.softplus(a)).sum()
    return log_lik - 0.5 * (w ** 2).sum() / PRIOR_STD ** 2


def grad_log_posterior(w):
    w = w.detach().requires_grad_(True)
    log_posterior(w).backward()                                   # autograd gives the gradient for Langevin
    return w.grad


def find_map():
    """The most probable weights (MAP), by L-BFGS: a good place to start the chains."""
    w = torch.zeros(D, dtype=torch.float64, requires_grad=True)
    opt = torch.optim.LBFGS([w], max_iter=200, line_search_fn="strong_wolfe")

    def closure():
        opt.zero_grad(); loss = -log_posterior(w); loss.backward(); return loss
    opt.step(closure)
    return w.detach()
