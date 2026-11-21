"""K-means only finds a local minimum of the distortion J. Does the starting point matter? 5 seeds, two inits."""
import torch
from sklearn.datasets import load_sample_image
from kmeans import kmeans

pixels = torch.tensor(load_sample_image("china.jpg").reshape(-1, 3), dtype=torch.float32)
sample = pixels[torch.randperm(len(pixels), generator=torch.Generator().manual_seed(0))[:20000]]
for init in ["random", "++"]:
    finals, firsts = [], []
    for seed in range(5):
        _, _, history = kmeans(sample, 16, seed=seed, init=init)
        firsts.append(history[0]); finals.append(history[-1])
    name = "K-means++" if init == "++" else "random points"
    print(f"{name:14s} J at start {sum(firsts) / 5 / 1e6:7.1f} M, after 30 steps: "
          + ", ".join(f"{f / 1e6:.1f}" for f in finals) + " M")
