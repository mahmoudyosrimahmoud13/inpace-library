"""Three ways to guess a paper's topic (Bishop, chapter 13)."""
import torch
from torch import nn


def normalized_adjacency(A):
    """A_hat = D^-1/2 (A + I) D^-1/2: each paper averages itself and its neighbours, scaled by their degrees."""
    A = A + torch.eye(len(A))
    d = A.sum(1).rsqrt()
    return d[:, None] * A * d[None, :]


class MLP(nn.Module):
    """Uses each paper's words only. The citation graph is ignored."""
    def __init__(self, n_in, n_out, hidden=64):
        super().__init__()
        self.net = nn.Sequential(nn.Dropout(0.5), nn.Linear(n_in, hidden), nn.ReLU(), nn.Dropout(0.5), nn.Linear(hidden, n_out))

    def forward(self, X, A_hat):
        return self.net(X)


class GCN(nn.Module):
    """Graph convolutional network: in each layer, a paper's new representation is a learned transformation of
    the average of its own and its neighbours' representations (message passing, section 13.2)."""
    def __init__(self, n_in, n_out, hidden=64):
        super().__init__()
        self.lin1, self.lin2 = nn.Linear(n_in, hidden), nn.Linear(hidden, n_out)
        self.drop = nn.Dropout(0.5)

    def forward(self, X, A_hat):
        h = torch.relu(A_hat @ self.lin1(self.drop(X)))      # aggregate neighbours, then non-linearity
        return A_hat @ self.lin2(self.drop(h))               # a second hop: neighbours of neighbours


def label_propagation(A_hat, y, train, n_classes, steps=20):
    """Uses the graph only, no words, no learning: spread the known labels along citation links."""
    Y = torch.zeros(len(y), n_classes)
    Y[train, y[train]] = 1.0
    F = Y.clone()
    for _ in range(steps):
        F = A_hat @ F
        F[train] = Y[train]                                  # keep the known labels fixed
    return F


class DeepGCN(nn.Module):
    """A GCN with any number of message-passing layers, to watch over-smoothing happen (section 13.3.4)."""
    def __init__(self, n_in, n_out, layers, hidden=64):
        super().__init__()
        sizes = [n_in] + [hidden] * (layers - 1) + [n_out]
        self.lins = nn.ModuleList(nn.Linear(a, b) for a, b in zip(sizes, sizes[1:]))
        self.drop = nn.Dropout(0.5)

    def forward(self, X, A_hat, return_hidden=False):
        h = X
        for i, lin in enumerate(self.lins):
            h = A_hat @ lin(self.drop(h))
            if i < len(self.lins) - 1:
                h = torch.relu(h)
                hidden = h
        return (h, hidden) if return_hidden else h
