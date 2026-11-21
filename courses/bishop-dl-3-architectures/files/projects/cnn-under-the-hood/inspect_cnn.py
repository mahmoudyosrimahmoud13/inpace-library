"""Look inside the trained CNN (Bishop, section 10.3): its first-layer filters, and saliency maps
showing which pixels decided each prediction."""
from pathlib import Path
import torch
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from data import load, normalize, CLASSES
from model import SmallCNN

saved = torch.load("cnn.pt")
model = SmallCNN(saved["width"]); model.load_state_dict(saved["state"]); model.eval()
Path("outputs").mkdir(exist_ok=True)

# 1. First-layer filters (section 10.3.2): each is a 3x3 colour patch the network slides over the image
W = model.features[0][0].weight.detach()                     # (width, 3, 3, 3)
fig, axes = plt.subplots(2, W.shape[0] // 2, figsize=(W.shape[0] // 2, 2.2))
for w, ax in zip(W, axes.flat):
    img = (w - w.min()) / (w.max() - w.min())
    ax.imshow(img.permute(1, 2, 0)); ax.axis("off")
fig.suptitle("first-layer filters, scaled to show their colours"); fig.tight_layout()
fig.savefig("outputs/filters.png", dpi=110)
print(f"saved outputs/filters.png ({W.shape[0]} filters of 3x3 pixels x 3 colours)")

# 2. Saliency maps (section 10.3.3): how much would each pixel change the score of the predicted class?
X, y = load("test")
idx = torch.arange(8)
x = normalize(X[idx]).requires_grad_(True)
scores = model(x)
pred = scores.argmax(1)
scores[torch.arange(len(idx)), pred].sum().backward()
saliency = x.grad.abs().amax(1)                              # strongest colour channel per pixel
fig, axes = plt.subplots(2, 8, figsize=(12, 3.4))
for k in range(8):
    axes[0, k].imshow(X[idx[k]].permute(1, 2, 0)); axes[0, k].axis("off")
    axes[0, k].set_title(f"{CLASSES[pred[k]]}" + ("" if pred[k] == y[idx[k]] else f"\n(is {CLASSES[y[idx[k]]]})"), fontsize=8)
    axes[1, k].imshow(saliency[k], cmap="hot"); axes[1, k].axis("off")
fig.suptitle("prediction (top) and saliency: pixels that most affect it (bottom)"); fig.tight_layout()
fig.savefig("outputs/saliency.png", dpi=110)
print("saved outputs/saliency.png")
for k in range(8):
    print(f"image {k}: true {CLASSES[y[idx[k]]]:8s} predicted {CLASSES[pred[k]]}")
