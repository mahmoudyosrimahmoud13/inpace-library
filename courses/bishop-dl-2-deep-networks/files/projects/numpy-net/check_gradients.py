"""Never trust hand-written gradients. Check them two ways: finite differences (section 8.1.4), and PyTorch."""
import sys
import numpy as np
import torch
from nn import Linear, Tanh, ReLU, Network

if "--bug" in sys.argv:                       # plant a classic mistake: forget the square in tanh's derivative
    Tanh.backward = lambda self, g: g * (1 - self.y)
    print("(with a planted bug in Tanh.backward)")

rng = np.random.default_rng(0)
net = Network(Linear(5, 4, rng), Tanh(), Linear(4, 3, rng), ReLU(), Linear(3, 3, rng))
x = rng.normal(size=(8, 5)).astype(np.float32)
labels = rng.integers(0, 3, 8)

net.loss(x, labels)
net.backward()
ours = [g.copy() for _, g in net.params()]

# 1. Finite differences, in float64, one parameter at a time: (E(w + eps) - E(w - eps)) / (2 eps)
for layer in net.layers:
    for name in ("W", "b"):
        if hasattr(layer, name):
            setattr(layer, name, getattr(layer, name).astype(np.float64))
x64 = x.astype(np.float64)
worst = 0.0
for (p, _), g in zip(net.params(), ours):
    for idx in np.ndindex(p.shape):
        old = p[idx]
        p[idx] = old + 1e-6; up = net.loss(x64, labels)
        p[idx] = old - 1e-6; down = net.loss(x64, labels)
        p[idx] = old
        numeric = (up - down) / 2e-6
        worst = max(worst, abs(numeric - g[idx]) / max(1e-8, abs(numeric) + abs(g[idx])))
print(f"finite differences: worst relative error {worst:.1e} over {sum(p.size for p, _ in net.params())} parameters")

# 2. PyTorch autograd on the same network with the same weights
params = [torch.tensor(p, requires_grad=True) for p, _ in net.params()]
W1, b1, W2, b2, W3, b3 = params
h = torch.relu(torch.tanh(torch.tensor(x64) @ W1 + b1) @ W2 + b2) @ W3 + b3
torch.nn.functional.cross_entropy(h, torch.tensor(labels)).backward()
diff = max((p.grad.numpy() - g).__abs__().max() for p, g in zip(params, ours))
print(f"PyTorch autograd:   largest difference {diff:.1e}")
