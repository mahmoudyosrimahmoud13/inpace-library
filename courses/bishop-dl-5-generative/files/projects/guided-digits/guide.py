"""Ask for each digit, at four guidance scales, and measure what guidance buys and what it costs (equation 20.60).
- accuracy: how often the judge sees the digit that was asked for
- variety:  how different the samples of the same digit are from each other (average pixel distance between pairs)"""
from pathlib import Path
import torch
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from unet import UNet
from diffusion import sample
from judge import judge_net

model = UNet(); model.load_state_dict(torch.load("diffusion.pt")); model.eval()
judge = judge_net(); judge.load_state_dict(torch.load("judge.pt")); judge.eval()
asked = torch.arange(10).repeat_interleave(10)               # ten of each digit, 0 to 9
grids = {}
print(f"{'guidance':>8s} {'right digit':>12s} {'judge sure':>11s} {'variety within a digit':>23s}")
for lam in [0, 1, 3, 6]:
    imgs = sample(model, asked, guidance=lam, generator=torch.Generator().manual_seed(0))
    flat = imgs.reshape(100, -1)
    with torch.no_grad():
        p = torch.softmax(judge(flat), 1)
    right = (p.argmax(1) == asked).float().mean().item()
    sure = (p.max(1).values > 0.9).float().mean().item()
    variety = torch.stack([torch.pdist(flat[asked == d]).mean() for d in range(10)]).mean().item()
    note = "  (no label used)" if lam == 0 else ""
    print(f"{lam:8d} {right:12.0%} {sure:11.0%} {variety:23.1f}{note}")
    grids[lam] = imgs

Path("outputs").mkdir(exist_ok=True)
fig, axes = plt.subplots(4, 20, figsize=(13, 3.2))
for r, (lam, imgs) in enumerate(grids.items()):
    for c in range(20):                                     # two samples of each digit
        k = (c // 2) * 10 + (c % 2)
        axes[r, c].imshow(imgs[k, 0], cmap="gray", vmin=-1, vmax=1); axes[r, c].axis("off")
    axes[r, 0].set_title(f"guidance {lam}", fontsize=8, loc="left")
fig.tight_layout(); fig.savefig("outputs/guidance.png", dpi=90)
print("saved outputs/guidance.png")
