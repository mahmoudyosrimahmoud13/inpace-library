"""Draw what the location bumps learned: the price difference that location alone adds, all over California."""
from pathlib import Path
import torch
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from data import load_splits
from basis import LocationBasis

d = load_splits()
basis = LocationBasis()
w = torch.load("model.pt")["w"]
w_loc = w[-basis.centres.shape[0]:]                     # the weights of the 144 location bumps

lat, lon = torch.meshgrid(torch.linspace(32.5, 42, 200), torch.linspace(-124.5, -114, 200), indexing="ij")
grid = torch.stack([lat.flatten(), lon.flatten()], 1)
effect = (basis(grid) @ w_loc).reshape(200, 200)
loc = d["train"][1]
near = torch.cdist(grid, loc[::20]).min(1).values.reshape(200, 200) < 0.25
effect[~near] = float("nan")                            # only draw where there are houses

Path("outputs").mkdir(exist_ok=True)
plt.figure(figsize=(6, 6.5))
plt.pcolormesh(lon, lat, effect, cmap="RdBu_r", vmin=-150, vmax=150, shading="auto")
plt.colorbar(label="effect of location on price ($1000s)")
for name, (la, lo) in {"San Francisco": (37.77, -122.42), "Los Angeles": (34.05, -118.24),
                       "Sacramento": (38.58, -121.49), "Fresno": (36.74, -119.79), "San Diego": (32.72, -117.16)}.items():
    plt.plot(lo, la, "k.", ms=4); plt.text(lo + 0.15, la, name, fontsize=8)
plt.xlabel("longitude"); plt.ylabel("latitude"); plt.title("What 144 basis functions learned")
plt.tight_layout(); plt.savefig("outputs/price_map.png", dpi=120)
for name, (la, lo) in {"San Francisco": (37.77, -122.42), "Fresno": (36.74, -119.79)}.items():
    print(f"location effect at {name:13s}: {(basis(torch.tensor([[la, lo]])) @ w_loc).item():+.0f}k dollars")
print("saved outputs/price_map.png")
