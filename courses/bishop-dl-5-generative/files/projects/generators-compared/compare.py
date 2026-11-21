"""Three generators, one judge: quality, variety, novelty and speed, measured the same way for each."""
import math
import time
from pathlib import Path
import torch
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from data import load
from gan import generator, Z
from vae import VAE
from unet import UNet, NULL
from diffusion import sample
from judge import judge_net

N = 200
x_train, _ = load("train")
judge = judge_net(); judge.load_state_dict(torch.load("judge.pt")); judge.eval()
G = generator(); G.load_state_dict(torch.load("gan_digits.pt")); G.eval()
vae = VAE(16); vae.load_state_dict(torch.load("vae_latent16.pt")); vae.eval()
unet = UNet(); unet.load_state_dict(torch.load("diffusion.pt")); unet.eval()
g = torch.Generator().manual_seed(0)
makers = {
    "GAN": lambda: G(torch.randn(N, Z, generator=g)),                                         # pixels in [-1, 1]
    "VAE (16-D)": lambda: torch.sigmoid(vae.decode(torch.randn(N, 16, generator=g))) * 2 - 1,
    "diffusion": lambda: sample(unet, torch.full((N,), NULL), guidance=0, generator=g).reshape(N, -1),
}
real = load("test")[0][:N] * 2 - 1                 # real digits the generators never saw
rows, grids = [], {}
print(f"{'model':12s} {'judge sure':>10s} {'digit variety':>14s} {'distance to nearest training digit':>35s} {'ms per image':>12s}")
for name, make in [("real (test)", lambda: real)] + list(makers.items()):
    start = time.time()
    with torch.no_grad():
        imgs = make()
    ms = 1000 * (time.time() - start) / N
    with torch.no_grad():
        p = torch.softmax(judge(imgs), 1)
    sure = (p.max(1).values > 0.9).float().mean().item()
    counts = torch.bincount(p.argmax(1), minlength=10).float()
    q = counts / counts.sum()
    variety = math.exp(-(q[q > 0] * q[q > 0].log()).sum().item())          # "effective number of digits", max 10
    nearest = torch.cdist(imgs, x_train[:20000] * 2 - 1).min(1).values.median().item()
    print(f"{name:12s} {sure:10.0%} {variety:14.1f} {nearest:35.1f} {ms if name != 'real (test)' else 0:12.1f}")
    grids[name] = imgs[:16]

Path("outputs").mkdir(exist_ok=True)
fig, axes = plt.subplots(4, 16, figsize=(12, 3.4))
for r, (name, imgs) in enumerate(grids.items()):
    for c in range(16):
        axes[r, c].imshow(imgs[c].reshape(28, 28), cmap="gray", vmin=-1, vmax=1); axes[r, c].axis("off")
    axes[r, 0].set_title(name, fontsize=8, loc="left")
fig.tight_layout(); fig.savefig("outputs/side_by_side.png", dpi=90)
print("saved outputs/side_by_side.png")
