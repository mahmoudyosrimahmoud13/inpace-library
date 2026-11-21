"""Learning curve (section 9.3): how does accuracy grow with the number of training images?
Every run gets the same number of update steps (1,500 mini-batches of 100), whatever its data size."""
from pathlib import Path
import torch
import torch.nn.functional as F
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from regularize import network, accuracy, XTR, TTR, XVA, TVA

sizes, results = [500, 1000, 2000, 5000, 10000, 20000], []
print(f"{'images':>7s} {'train acc':>9s} {'val acc':>8s}")
for n in sizes:
    torch.manual_seed(0)
    x, t = XTR[:n], TTR[:n]
    model = network()
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=0.0)
    for step in range(1500):
        idx = torch.randint(0, n, (100,))
        loss = F.cross_entropy(model(x[idx]), t[idx])
        opt.zero_grad(); loss.backward(); opt.step()
    tr, va = accuracy(model, x, t), accuracy(model, XVA, TVA)
    results.append((tr, va))
    print(f"{n:7d} {tr:9.3f} {va:8.3f}")

Path("outputs").mkdir(exist_ok=True)
plt.figure(figsize=(5.5, 3.8))
plt.plot(sizes, [r[0] for r in results], "o-", label="training accuracy")
plt.plot(sizes, [r[1] for r in results], "o-", label="validation accuracy")
plt.axhline(0.826, color="0.5", ls=":", label="best regularized model, 1,000 images")
plt.xscale("log"); plt.xlabel("training images"); plt.ylabel("accuracy"); plt.legend(fontsize=8)
plt.tight_layout(); plt.savefig("outputs/learning_curve.png", dpi=120)
print("saved outputs/learning_curve.png")
