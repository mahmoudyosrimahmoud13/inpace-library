"""Fit each model on normal hours, raise an alarm when an hour is too unlikely, and score the alarms
against the engineers' failure labels."""
from pathlib import Path
import torch
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from data import hourly_features, failure_windows, TRAIN
from models import Gaussian, Independent, KDE

table = hourly_features()
X_all = torch.tensor(table.values, dtype=torch.float32)
train_mask = torch.tensor((table.index >= TRAIN[0]) & (table.index < TRAIN[1]))
X_train = X_all[train_mask]
windows = failure_windows()
in_window = torch.zeros(len(table), dtype=torch.bool)
for a, b in windows:
    in_window |= torch.tensor((table.index >= a) & (table.index <= b))

# Choose the KDE width by likelihood on held-out normal hours (the last 20% of the training period)
cut = int(0.8 * len(X_train))
widths = [0.05, 0.1, 0.2, 0.3, 0.5, 1.0]
scores = {h: KDE(h).fit(X_train[:cut]).log_prob(X_train[cut:]).mean().item() for h in widths}
h = max(scores, key=scores.get)
print("KDE width h -> held-out log-likelihood:", ", ".join(f"{w}: {s:.2f}" for w, s in scores.items()))
print(f"chosen h = {h}\n")

test = ~train_mask                                 # everything outside the training period
days_normal = (test & ~in_window).sum().item() / 24
results = {}
for name, model in [("independent Gaussian", Independent()), ("full Gaussian", Gaussian()), (f"KDE (h={h})", KDE(h))]:
    model.fit(X_train)
    logp = model.log_prob(X_all)
    threshold = torch.quantile(model.log_prob(X_train), 0.005)  # 0.5% of normal training hours would raise an alarm
    alarm = logp < threshold
    found = []
    for a, b in windows:
        hours = torch.tensor((table.index >= a) & (table.index <= b))
        found.append(bool((alarm & hours).any()))
    false = (alarm & test & ~in_window).sum().item()
    results[name] = (logp, threshold, alarm)
    print(f"{name:22s} failures found {sum(found)}/4 {['yes' if f else 'no' for f in found]}, "
          f"false alarms {false / days_normal:.2f} per day")

# Plot the temperature with the alarms of the best model and the labelled windows
Path("outputs").mkdir(exist_ok=True)
logp, threshold, alarm = results[f"KDE (h={h})"]
fig, ax = plt.subplots(figsize=(11, 3.5))
ax.plot(table.index, table.temp, lw=0.7, color="0.3")
for a, b in windows:
    ax.axvspan(a, b, color="orange", alpha=0.3)
ax.axvspan(*TRAIN, color="green", alpha=0.08)
ax.scatter(table.index[alarm.numpy()], table.temp[alarm.numpy()], color="red", s=10, zorder=3)
ax.set_ylabel("temperature"); ax.set_title("KDE alarms (red), labelled failures (orange), training period (green)")
fig.tight_layout(); fig.savefig("outputs/alarms.png", dpi=120)
print("\nsaved outputs/alarms.png")
