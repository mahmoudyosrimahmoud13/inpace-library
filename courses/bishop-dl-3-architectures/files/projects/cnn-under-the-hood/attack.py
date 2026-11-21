"""Adversarial attacks (section 10.3.4): change every pixel by an invisible amount, in exactly the direction that
hurts the network most (the fast gradient sign method), and watch accuracy collapse."""
from pathlib import Path
import torch
import torch.nn.functional as F
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from data import load, normalize, CLASSES, MEAN, STD
from model import SmallCNN

saved = torch.load("cnn.pt")
model = SmallCNN(saved["width"]); model.load_state_dict(saved["state"]); model.eval()
X, y = load("test")
X, y = X[:2000], y[:2000]


def normalize_float(x01):
    """Like data.normalize, for images already scaled to [0, 1]."""
    return (x01 - MEAN) / STD


def fgsm(images_uint8, labels, eps):
    """Move each pixel by eps (out of 255) up or down, following the sign of the loss gradient."""
    x = (images_uint8.float() / 255).requires_grad_(True)
    F.cross_entropy(model(normalize_float(x)), labels).backward()
    return (x + eps / 255 * x.grad.sign()).clamp(0, 1).detach()


print(f"{'change per pixel':>17s} {'accuracy':>9s}")
for eps in [0, 1, 2, 4, 8]:
    adv = fgsm(X, y, eps) if eps else X.float() / 255
    with torch.no_grad():
        acc = (model(normalize_float(adv)).argmax(1) == y).float().mean().item()
    print(f"{eps:>13d}/255 {acc:9.3f}")

# Show one attacked image next to the original
Path("outputs").mkdir(exist_ok=True)
k = 6                                                   # a car the model classifies correctly
adv = fgsm(X[k:k + 1], y[k:k + 1], 4)
with torch.no_grad():
    before = CLASSES[model(normalize(X[k:k + 1])).argmax(1).item()]
    after = CLASSES[model(normalize_float(adv)).argmax(1).item()]
fig, axes = plt.subplots(1, 3, figsize=(7, 2.6))
axes[0].imshow(X[k].permute(1, 2, 0)); axes[0].set_title(f"original: {before}")
axes[1].imshow(adv[0].permute(1, 2, 0)); axes[1].set_title(f"attacked: {after}")
diff = (adv[0] - X[k].float() / 255)
axes[2].imshow(((diff - diff.min()) / (diff.max() - diff.min()).clamp(min=1e-8)).permute(1, 2, 0)); axes[2].set_title("the change, enlarged")
for ax in axes: ax.axis("off")
fig.tight_layout(); fig.savefig("outputs/attack.png", dpi=120)
print(f"\nimage {k}: '{before}' before the attack, '{after}' after changing each pixel by at most 4/255")
