"""Judge the GAN the same way a person would want: are the clothes recognizable, are all 10 kinds made, and are they
new rather than copies? A separate CNN trained on real Fashion-MNIST is the judge."""
import math
import torch
import torch.nn.functional as F
from torch import nn
from data import load, CLASSES
from models import generator, Z

torch.manual_seed(0)
x, y = load("train"); xt, yt = load("t10k")
judge = nn.Sequential(nn.Unflatten(1, (1, 28, 28)), nn.Conv2d(1, 32, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
                      nn.Conv2d(32, 64, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2), nn.Flatten(), nn.Linear(64 * 49, 10))
opt = torch.optim.Adam(judge.parameters(), 1e-3)
for epoch in range(2):
    order = torch.randperm(len(x))
    for s in range(0, len(x), 128):
        i = order[s:s + 128]
        loss = F.cross_entropy(judge(x[i] * 2 - 1), y[i]); opt.zero_grad(); loss.backward(); opt.step()
judge.eval()
with torch.no_grad():
    print(f"judge accuracy on real test clothes: {(judge(xt * 2 - 1).argmax(1) == yt).float().mean():.3f}\n")

G = generator(); G.load_state_dict(torch.load("generator.pt")); G.eval()


def report(name, imgs):
    with torch.no_grad():
        p = torch.softmax(judge(imgs), 1)
    sure = (p.max(1).values > 0.9).float().mean().item()
    counts = torch.bincount(p.argmax(1), minlength=10)
    q = counts.float() / counts.sum()
    variety = math.exp(-(q[q > 0] * q[q > 0].log()).sum().item())       # effective number of kinds, max 10
    nearest = torch.cdist(imgs, x[:20000] * 2 - 1).min(1).values.median().item()
    print(f"{name:22s} judge sure {sure:4.0%}   kinds of clothes {variety:4.1f} of 10   "
          f"distance to nearest training image {nearest:5.1f}")
    return counts


with torch.no_grad():
    fake = G(torch.randn(1000, Z, generator=torch.Generator().manual_seed(3)))
report("real test images", xt[:1000] * 2 - 1)
counts = report("GAN samples", fake)
print("\nwhat the GAN makes, according to the judge:")
print("  " + ", ".join(f"{CLASSES[k]} {counts[k].item()}" for k in counts.argsort(descending=True)))
