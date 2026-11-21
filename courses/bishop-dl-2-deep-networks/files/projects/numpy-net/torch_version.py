"""The same network, optimizer and settings in PyTorch: if numpy-net is right, the results should be close."""
import numpy as np
import torch
from torch import nn
from data import load

torch.manual_seed(0)
X, y = map(torch.tensor, load("train"))
X_test, y_test = map(torch.tensor, load("test"))
net = nn.Sequential(nn.Linear(784, 128), nn.ReLU(), nn.Linear(128, 64), nn.ReLU(), nn.Linear(64, 10))
opt = torch.optim.SGD(net.parameters(), lr=0.05, momentum=0.9)
for epoch in range(1, 6):
    order = torch.randperm(len(X))
    for start in range(0, len(X), 64):
        idx = order[start:start + 64]
        loss = nn.functional.cross_entropy(net(X[idx]), y[idx])
        opt.zero_grad(); loss.backward(); opt.step()
with torch.no_grad():
    print(f"PyTorch, same settings: TEST accuracy {(net(X_test).argmax(1) == y_test).float().mean():.4f}")
