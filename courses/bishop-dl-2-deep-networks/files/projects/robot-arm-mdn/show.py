"""Draw the arms each network proposes for a few target points."""
from pathlib import Path
import torch
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from arm import L1, forward
from models import Regressor, MDN

reg, mdn = Regressor(), MDN()
reg.load_state_dict(torch.load("regressor.pt")); mdn.load_state_dict(torch.load("mdn.pt"))
targets = torch.tensor([[0.9, -0.6], [1.2, 0.5], [0.3, 1.1]])


def draw(ax, theta, **style):
    a, b = theta
    elbow = (L1 * torch.cos(a), L1 * torch.sin(a))
    hand = forward(theta[None])[0]
    ax.plot([0, elbow[0], hand[0]], [0, elbow[1], hand[1]], "-o", ms=3, **style)


Path("outputs").mkdir(exist_ok=True)
fig, axes = plt.subplots(1, 3, figsize=(11, 3.8))
with torch.no_grad():
    log_pi, mu, _ = mdn.params(targets)
    for i, ax in enumerate(axes):
        for k in range(mdn.K):
            w = log_pi[i, k].exp().item()
            if w > 0.05:
                draw(ax, mu[i, k], color="C0", alpha=0.3 + 0.7 * w, label=f"MDN component, weight {w:.2f}")
        draw(ax, reg(targets[i:i + 1])[0], color="C3", label="squared-error network")
        ax.plot(*targets[i], "k*", ms=14, label="target")
        ax.set_aspect("equal"); ax.set_xlim(-0.6, 1.8); ax.set_ylim(-1.3, 1.5); ax.legend(fontsize=7, loc="best")
        print(f"target ({targets[i, 0]:+.1f}, {targets[i, 1]:+.1f}): MDN weights "
              + ", ".join(f"{p:.2f}" for p in log_pi[i].exp()))
fig.tight_layout(); fig.savefig("outputs/arms.png", dpi=110)
print("saved outputs/arms.png")
