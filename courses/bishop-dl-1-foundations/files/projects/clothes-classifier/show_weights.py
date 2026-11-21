"""Each class has 784 weights, one per pixel: draw them as images to see what the model looks for."""
import torch
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from data import CLASSES
from models import SoftmaxRegression

model = SoftmaxRegression()
model.load_state_dict(torch.load("softmax.pt"))
W = model.linear.weight.detach()
fig, axes = plt.subplots(2, 5, figsize=(10, 4.4))
for k, ax in enumerate(axes.flat):
    lim = W[k].abs().max()
    ax.imshow(W[k].reshape(28, 28), cmap="RdBu_r", vmin=-lim, vmax=lim)
    ax.set_title(CLASSES[k]); ax.axis("off")
fig.suptitle("Weights per class: red pixels raise the score, blue pixels lower it")
fig.tight_layout(); fig.savefig("outputs/weights.png", dpi=110)
print("saved outputs/weights.png")
