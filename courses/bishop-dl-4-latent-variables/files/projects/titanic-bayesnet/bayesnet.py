"""A discrete Bayesian network (Bishop, section 11.1): a graph, one conditional table per node, exact inference."""
import itertools
import torch
from data import VALUES


class BayesNet:
    def __init__(self, parents):
        """parents: {node: [its parents]}, e.g. {"Class": [], "Survived": ["Class", "Sex"]}"""
        self.parents = parents
        self.order = list(VALUES)                                      # fixed axis order for the joint table

    def fit(self, data, alpha=1.0):
        """Each conditional table p(node | parents) is estimated by counting, plus a pseudo-count alpha."""
        self.cpt = {}
        for node, pars in self.parents.items():
            shape = [len(VALUES[p]) for p in pars] + [len(VALUES[node])]
            counts = torch.full(shape, alpha)
            idx = tuple(data[p] for p in pars) + (data[node],)
            counts.index_put_(idx, torch.ones(len(data[node])), accumulate=True)
            self.cpt[node] = counts / counts.sum(-1, keepdim=True)
        return self

    def joint(self):
        """The full table p(Class, Sex, Age, Survived) as the product of the conditionals (equation 11.6)."""
        J = torch.ones([len(VALUES[v]) for v in self.order])
        for node, pars in self.parents.items():
            axes = [self.order.index(p) for p in pars] + [self.order.index(node)]
            shape = [1] * len(self.order)
            for a, size in zip(axes, self.cpt[node].shape):
                shape[a] = size
            t = self.cpt[node].permute(*sorted(range(len(axes)), key=lambda k: axes[k])).reshape(shape)
            J = J * t
        return J

    def query(self, target, **evidence):
        """p(target | evidence) by summing the joint over everything else, then normalizing (Bayes' theorem)."""
        J = self.joint()
        for v, value in evidence.items():
            keep = torch.zeros(len(VALUES[v])); keep[VALUES[v].index(value)] = 1
            shape = [1] * len(self.order); shape[self.order.index(v)] = -1
            J = J * keep.reshape(shape)
        axis = self.order.index(target)
        p = J.sum(dim=[a for a in range(len(self.order)) if a != axis])
        return dict(zip(VALUES[target], (p / p.sum()).tolist()))

    def log_likelihood(self, data):
        J = self.joint()
        return J[tuple(data[v] for v in self.order)].log().sum().item()

    def n_parameters(self):
        return sum(t[..., :-1].numel() for t in self.cpt.values())     # the last column of each table is implied
