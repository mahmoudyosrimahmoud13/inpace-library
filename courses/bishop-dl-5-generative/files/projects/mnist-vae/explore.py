"""Look at what the two VAEs learned: reconstructions, brand-new digits, and the 2-D latent space as a map."""
from pathlib import Path
import torch
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from data import load
from vae import VAE

x_test, y_test = load("test")
models = {}
for latent in (2, 16):
    m = VAE(latent); m.load_state_dict(torch.load(f"vae_latent{latent}.pt")); m.eval(); models[latent] = m
Path("outputs").mkdir(exist_ok=True)
g = torch.Generator().manual_seed(0)

with torch.no_grad():
    # 1. reconstructions and new samples from both models
    fig, axes = plt.subplots(5, 10, figsize=(10, 5.4))
    rows = [("test images", x_test[:10])]
    for latent, m in models.items():
        rows.append((f"rebuilt, {latent}-D", torch.sigmoid(m.decode(m.encode(x_test[:10])[0]))))
    for latent, m in models.items():
        rows.append((f"new, {latent}-D", torch.sigmoid(m.decode(torch.randn(10, latent, generator=g)))))
    for r, (label, imgs) in enumerate(rows):
        for c in range(10):
            axes[r, c].imshow(imgs[c].reshape(28, 28), cmap="gray"); axes[r, c].axis("off")
        axes[r, 0].set_title(label, fontsize=8, loc="left")
    fig.tight_layout(); fig.savefig("outputs/reconstructions_and_samples.png", dpi=90); plt.close(fig)

    # 2. the 2-D latent space: where each test digit lands, and what each point decodes to
    m = models[2]
    mu = m.encode(x_test)[0]
    fig, axes = plt.subplots(1, 2, figsize=(11, 5))
    sc = axes[0].scatter(*mu.T, c=y_test, cmap="tab10", s=2)
    axes[0].legend(*sc.legend_elements(), fontsize=7, loc="upper right", title="digit"); axes[0].set_title("test digits in latent space")
    grid = torch.linspace(-2.5, 2.5, 15)
    zz = torch.cartesian_prod(grid, grid.flip(0))[:, [0, 1]]
    imgs = torch.sigmoid(m.decode(zz)).reshape(15, 15, 28, 28)
    big = imgs.permute(1, 2, 0, 3).reshape(15 * 28, 15 * 28)
    axes[1].imshow(big, cmap="gray"); axes[1].axis("off"); axes[1].set_title("decoding a grid of latent points")
    fig.tight_layout(); fig.savefig("outputs/latent_map.png", dpi=90); plt.close(fig)

    # 3. how clearly does each digit get its own area? Average distance to the 5 nearest same-digit neighbours
    #    vs to other digits, in the 2-D space
    d = torch.cdist(mu[:2000], mu[:2000]); d.fill_diagonal_(float("inf"))
    nearest = d.topk(5, largest=False).indices
    same = (y_test[:2000][nearest] == y_test[:2000][:, None]).float().mean().item()
print(f"in the 2-D latent space, {same:.1%} of each digit's 5 nearest neighbours are the same digit "
      "(the VAE was never told the labels)")
print("saved outputs/reconstructions_and_samples.png and outputs/latent_map.png")
