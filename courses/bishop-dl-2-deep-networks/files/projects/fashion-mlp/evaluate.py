"""Test the final network once, class by class, against the linear model (softmax regression)."""
import torch
from data import load_splits, CLASSES
from model import mlp
from train import train

_, _, (xte, tte) = load_splits()
saved = torch.load("model.pt")
net = mlp(saved["hidden"]); net.load_state_dict(saved["state"]); net.eval()
linear, _, _, _ = train([], epochs=15)


def per_class(model):
    with torch.no_grad():
        guess = model(xte).argmax(1)
    return torch.stack([(guess[tte == k] == k).float().mean() for k in range(10)]), (guess == tte).float().mean()


lin_k, lin_all = per_class(linear)
net_k, net_all = per_class(net)
print(f"{'class':12s} {'linear':>7s} {'MLP ' + str(saved['hidden']):>12s}")
for k in (net_k - lin_k).argsort(descending=True):
    print(f"{CLASSES[k]:12s} {lin_k[k]:7.3f} {net_k[k]:12.3f}")
print(f"{'ALL (test)':12s} {lin_all:7.3f} {net_all:12.3f}")
