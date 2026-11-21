"""Generate 100 digits with NO label (the unconditional model), and let the judge score them."""
from pathlib import Path
import torch
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from unet import UNet, NULL
from diffusion import sample
from judge import judge_net

model = UNet(); model.load_state_dict(torch.load("diffusion.pt")); model.eval()
judge = judge_net(); judge.load_state_dict(torch.load("judge.pt")); judge.eval()
imgs = sample(model, torch.full((100,), NULL), guidance=0, generator=torch.Generator().manual_seed(0))
with torch.no_grad():
    p = torch.softmax(judge(imgs.reshape(100, -1)), 1)
conf, digit = p.max(1)
print(f"judge is at least 90% sure for {(conf > 0.9).float().mean():.0%} of the 100 generated digits")
print("which digits came out:", torch.bincount(digit, minlength=10).tolist(), "(10 each would be perfectly even)")
Path("outputs").mkdir(exist_ok=True)
fig, axes = plt.subplots(10, 10, figsize=(6, 6))
for img, ax in zip(imgs, axes.flat):
    ax.imshow(img[0], cmap="gray", vmin=-1, vmax=1); ax.axis("off")
fig.tight_layout(); fig.savefig("outputs/generated.png", dpi=90)
print("saved outputs/generated.png")
