"""Draw the learning curves saved by benchmark.py."""
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

results = json.loads(Path("outputs/results.json").read_text())
fig, axes = plt.subplots(1, 2, figsize=(12, 4.2))
for i, (name, r) in enumerate(results.items()):
    ax = axes[0] if i < 5 else axes[1]
    steps, losses = zip(*r["curve"])
    smooth = [sum(losses[max(0, j - 4):j + 1]) / len(losses[max(0, j - 4):j + 1]) for j in range(len(losses))]
    ax.plot(steps, smooth, label=name)
for ax, title in zip(axes, ["optimizers and schedules", "step size, initialization, batch norm"]):
    ax.set_yscale("log"); ax.set_xlabel("training step"); ax.set_title(title); ax.legend(fontsize=8)
axes[0].set_ylim(0.2, 3)
axes[0].set_ylabel("training loss (smoothed, log scale)")
fig.tight_layout(); fig.savefig("outputs/curves.png", dpi=110)
print("saved outputs/curves.png")
