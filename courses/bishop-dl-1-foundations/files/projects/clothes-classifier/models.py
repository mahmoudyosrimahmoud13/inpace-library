"""Two ways to build a 10-class classifier (Bishop, chapter 5)."""
import torch
from torch import nn


class GaussianClassifier:
    """Generative (section 5.3): one Gaussian per class with a SHARED covariance, then Bayes' theorem.
    Fitted in closed form, no training loop. The decision boundaries come out linear."""
    def fit(self, X, t, eps=0.05):
        K = int(t.max()) + 1
        self.means = torch.stack([X[t == k].mean(0) for k in range(K)])
        centred = X - self.means[t]
        cov = centred.T @ centred / len(X) + eps * torch.eye(X.shape[1])   # eps: many border pixels are always 0
        self.precision = torch.linalg.inv(cov)
        self.log_prior = torch.log(torch.bincount(t, minlength=K).float() / len(t))
        return self

    def logits(self, X):
        # a_k(x) = w_k^T x + w_k0  with  w_k = S^-1 mu_k,  w_k0 = -mu_k^T S^-1 mu_k / 2 + ln p(C_k)
        W = self.means @ self.precision
        b = -0.5 * (W * self.means).sum(1) + self.log_prior
        return X @ W.T + b


class SoftmaxRegression(nn.Module):
    """Discriminative (section 5.4.4): model p(C_k | x) = softmax(W x + b) directly, train by cross-entropy."""
    def __init__(self, D=784, K=10):
        super().__init__()
        self.linear = nn.Linear(D, K)

    def forward(self, X):
        return self.linear(X)
