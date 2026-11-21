"""K-means clustering in PyTorch (Bishop, section 15.1), with K-means++ initialization."""
import torch


def init_plus_plus(X, K, g):
    """K-means++: each new centre is a random data point, chosen with probability proportional to its squared
    distance from the nearest centre so far. Spreads the starting centres out."""
    centres = X[torch.randint(len(X), (1,), generator=g)]
    for _ in range(K - 1):
        d2 = torch.cdist(X, centres).min(1).values ** 2
        centres = torch.cat([centres, X[torch.multinomial(d2, 1, generator=g)]])
    return centres


def kmeans(X, K, iters=30, seed=0, init="++"):
    """Returns centres (K, D), the cluster of each point (N,), and the distortion J after each iteration."""
    g = torch.Generator().manual_seed(seed)
    centres = init_plus_plus(X, K, g) if init == "++" else X[torch.randperm(len(X), generator=g)[:K]].clone()
    history = []
    for _ in range(iters):
        labels = torch.cdist(X, centres).argmin(1)                               # E step: nearest centre
        history.append(((X - centres[labels]) ** 2).sum().item())                 # distortion J (equation 15.1)
        for k in range(K):                                                         # M step: mean of each cluster
            members = X[labels == k]
            if len(members):
                centres[k] = members.mean(0)
    return centres, labels, history
