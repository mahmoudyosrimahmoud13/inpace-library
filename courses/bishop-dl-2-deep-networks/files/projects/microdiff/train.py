"""Train a microdiff network to separate two interleaved half-moons, after checking its gradients against PyTorch."""
import math
import random
from pathlib import Path
import torch
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from engine import Value
from nn import MLP

random.seed(0)
points, labels = [], []
for i in range(40):                                       # two interleaved half-moons, 40 points each
    a = math.pi * i / 39
    points.append((math.cos(a) - 0.5 + random.gauss(0, 0.1), math.sin(a) - 0.25 + random.gauss(0, 0.1)))
    labels.append(1)
    points.append((0.5 - math.cos(a) + random.gauss(0, 0.1), 0.25 - math.sin(a) + random.gauss(0, 0.1)))
    labels.append(-1)

model = MLP([2, 8, 8, 1])
params = model.parameters()
print(f"{len(params)} parameters, {len(points)} points")


def loss_and_accuracy():
    """Hinge-free and simple: the mean squared error between the output and the label (+1 or -1)."""
    outs = [model([Value(x), Value(y)]) for x, y in points]
    loss = sum(((o - t) ** 2 for o, t in zip(outs, labels)), Value(0.0)) * (1 / len(points))
    acc = sum((o.data > 0) == (t > 0) for o, t in zip(outs, labels)) / len(points)
    return loss, acc


# Check the very first gradient against PyTorch on the same weights
loss, _ = loss_and_accuracy()
loss.backward()
W = [torch.tensor([[w.data for w in n.w] for n in layer], dtype=torch.float64, requires_grad=True) for layer in model.layers]
B = [torch.tensor([n.b.data for n in layer], dtype=torch.float64, requires_grad=True) for layer in model.layers]
h = torch.tensor(points, dtype=torch.float64)
for i, (w, b) in enumerate(zip(W, B)):
    h = h @ w.T + b
    h = torch.tanh(h) if i < len(W) - 1 else h
((h[:, 0] - torch.tensor(labels, dtype=torch.float64)) ** 2).mean().backward()
torch_grads = [g for w, b in zip(W, B) for row_w, gb in zip(w.grad, b.grad) for g in [*row_w.tolist(), gb.item()]]
print(f"largest difference from PyTorch's gradients: {max(abs(p.grad - g) for p, g in zip(params, torch_grads)):.1e}")

velocity = [0.0] * len(params)
for step in range(1, 151):
    loss, acc = loss_and_accuracy()
    loss.backward()
    for i, p in enumerate(params):                        # gradient descent with momentum (section 7.3.1)
        velocity[i] = 0.9 * velocity[i] - 0.05 * p.grad
        p.data += velocity[i]
    if step in (1, 25, 50, 100, 150):
        print(f"step {step:3d}: loss {loss.data:.4f}, accuracy {acc:.3f}")

Path("outputs").mkdir(exist_ok=True)
grid = [(x / 10, y / 10) for y in range(-15, 16) for x in range(-20, 21)]
z = [model([Value(x), Value(y)]).data for x, y in grid]
plt.figure(figsize=(5, 5))
plt.tricontourf([g[0] for g in grid], [g[1] for g in grid], z, levels=[-10, 0, 10], colors=["#f3c7c0", "#c0d7f3"])
plt.scatter(*zip(*points), c=["C0" if t > 0 else "C3" for t in labels], s=12)
plt.title("decision regions learned by microdiff"); plt.axis("equal")
plt.tight_layout(); plt.savefig("outputs/moons.png", dpi=110)
print("saved outputs/moons.png")
