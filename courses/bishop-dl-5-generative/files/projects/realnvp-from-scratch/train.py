"""Fit Real NVP to each data set by maximum likelihood, and compare its test log-likelihood with a single Gaussian
and a 10-component Gaussian mixture (scikit-learn), the density models of chapters 3 and 15."""
from pathlib import Path
import torch
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.mixture import GaussianMixture
from data import DATASETS, load
from flow import RealNVP

Path("outputs").mkdir(exist_ok=True)
fig, axes = plt.subplots(2, 3, figsize=(10, 6.5))
print(f"{'data set':16s} {'Gaussian':>9s} {'mixture of 10':>14s} {'Real NVP':>9s}   (test log-likelihood per point)")
for col, name in enumerate(DATASETS):
    torch.manual_seed(0)
    train, test = load(name)
    flow = RealNVP()
    opt = torch.optim.Adam(flow.parameters(), lr=2e-3)
    for step in range(3000):
        batch = train[torch.randint(0, len(train), (256,))]
        loss = -flow.log_prob(batch).mean()               # maximum likelihood (equation 18.3)
        opt.zero_grad(); loss.backward(); opt.step()
    with torch.no_grad():
        ll_flow = flow.log_prob(test).mean().item()
    gauss = GaussianMixture(1, random_state=0).fit(train.numpy())
    gmm = GaussianMixture(10, random_state=0).fit(train.numpy())
    print(f"{name:16s} {gauss.score(test.numpy()):9.3f} {gmm.score(test.numpy()):14.3f} {ll_flow:9.3f}")

    samples = flow.sample(2000, generator=torch.Generator().manual_seed(2))
    axes[0, col].scatter(*test.T, s=2, alpha=0.4); axes[0, col].set_title(f"{name}: real test data")
    axes[1, col].scatter(*samples.T, s=2, alpha=0.4, color="C1"); axes[1, col].set_title("Real NVP samples")
    for ax in axes[:, col]:
        ax.set_xlim(-2.5, 2.5); ax.set_ylim(-2.5, 2.5); ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
    torch.save(flow.state_dict(), f"flow_{name.replace(' ', '_')}.pt")
fig.tight_layout(); fig.savefig("outputs/samples.png", dpi=100)
print("saved outputs/samples.png")
