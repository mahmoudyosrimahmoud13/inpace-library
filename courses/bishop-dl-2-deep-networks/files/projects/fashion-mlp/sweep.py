"""How wide, how deep? Train several architectures for the same 8 epochs and compare."""
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from train import train
from model import count_parameters

ARCHITECTURES = [[], [16], [64], [256], [1024], [256, 256], [256, 256, 256], [64, 64, 64, 64, 64, 64]]
rows = []
print(f"{'hidden layers':24s} {'parameters':>10s} {'train acc':>10s} {'val acc':>8s}")
for hidden in ARCHITECTURES:
    model, tr, va, _ = train(hidden)
    n = count_parameters(model)
    rows.append((hidden, n, tr, va))
    print(f"{str(hidden) if hidden else 'none (linear)':24s} {n:10,d} {tr:10.3f} {va:8.3f}")

Path("outputs").mkdir(exist_ok=True)
plt.figure(figsize=(6, 4))
for hidden, n, tr, va in rows:
    plt.scatter(n, va, color="C0" if len(hidden) <= 1 else "C3")
    plt.annotate(str(hidden) if hidden else "linear", (n, va), fontsize=7, xytext=(4, -3), textcoords="offset points")
plt.xscale("log"); plt.xlabel("parameters"); plt.ylabel("validation accuracy")
plt.title("blue: one hidden layer or none, red: deeper")
plt.tight_layout(); plt.savefig("outputs/sweep.png", dpi=120)
print("saved outputs/sweep.png")
