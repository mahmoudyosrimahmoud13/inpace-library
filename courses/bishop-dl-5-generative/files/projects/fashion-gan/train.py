"""Train the GAN on Fashion-MNIST, saving a grid of generated images after some epochs."""
import argparse
from pathlib import Path
import torch
import torch.nn.functional as F
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from data import load
from models import generator, discriminator, Z

ap = argparse.ArgumentParser()
ap.add_argument("--epochs", type=int, default=15)
args = ap.parse_args()
torch.manual_seed(0)
x, _ = load("train")
x = x * 2 - 1                                       # pixels in [-1, 1], to match the generator's tanh
G, D = generator(), discriminator()
opt_g = torch.optim.Adam(G.parameters(), lr=2e-4, betas=(0.5, 0.999))
opt_d = torch.optim.Adam(D.parameters(), lr=2e-4, betas=(0.5, 0.999))
fixed_z = torch.randn(64, Z, generator=torch.Generator().manual_seed(1))   # the same 64 inputs every time
Path("outputs").mkdir(exist_ok=True)


def save_grid(epoch):
    G.eval()
    with torch.no_grad():
        imgs = G(fixed_z).reshape(-1, 28, 28)
    G.train()
    fig, axes = plt.subplots(8, 8, figsize=(6, 6))
    for img, ax in zip(imgs, axes.flat):
        ax.imshow(img, cmap="gray", vmin=-1, vmax=1); ax.axis("off")
    fig.suptitle(f"after {epoch} epochs"); fig.tight_layout()
    fig.savefig(f"outputs/epoch_{epoch:02d}.png", dpi=80); plt.close(fig)


for epoch in range(1, args.epochs + 1):
    order = torch.randperm(len(x))
    for s in range(0, len(x) - 127, 128):
        real = x[order[s:s + 128]]
        fake = G(torch.randn(128, Z))
        # 1. discriminator: push real towards 1 and fake towards 0 (the cross-entropy of equation 17.6)
        d_loss = F.binary_cross_entropy_with_logits(D(real), torch.ones(128, 1)) + \
                 F.binary_cross_entropy_with_logits(D(fake.detach()), torch.zeros(128, 1))
        opt_d.zero_grad(); d_loss.backward(); opt_d.step()
        # 2. generator: make the discriminator say 1 for fakes (the non-saturating version, equation 17.10)
        g_loss = F.binary_cross_entropy_with_logits(D(fake), torch.ones(128, 1))
        opt_g.zero_grad(); g_loss.backward(); opt_g.step()
    with torch.no_grad():
        d_real = torch.sigmoid(D(real)).mean().item(); d_fake = torch.sigmoid(D(fake)).mean().item()
    print(f"epoch {epoch:2d}: D says real {d_real:.2f}, fake {d_fake:.2f}   losses D {d_loss.item():.2f}, G {g_loss.item():.2f}")
    if epoch in (1, 3, 8, args.epochs):
        save_grid(epoch)
torch.save(G.state_dict(), "generator.pt")
