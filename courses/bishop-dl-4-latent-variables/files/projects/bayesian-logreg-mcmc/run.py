"""Sample the posterior with both samplers, compare how well they explore, then use the samples to predict
with honest uncertainty."""
from pathlib import Path
import torch
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from model import X, t, test, find_map
from samplers import metropolis, mala

STEPS, BURN = 5000, 1000


def effective_sample_size(x):
    """How many independent samples a correlated chain is worth (sum of autocorrelations until they turn negative)."""
    x = x - x.mean()
    n, var = len(x), (x * x).mean()
    rho_sum = 0.0
    for lag in range(1, n // 2):
        rho = (x[:-lag] * x[lag:]).mean() / var
        if rho < 0:
            break
        rho_sum += rho
    return n / (1 + 2 * rho_sum)


w_map = find_map()
chains = {"random-walk Metropolis": metropolis(w_map, STEPS, 0.2), "Langevin (MALA)": mala(w_map, STEPS, 0.2)}
print(f"{'sampler':24s} {'acceptance':>10s} {'effective samples (worst / median weight)':>42s}")
for name, (samples, acc) in chains.items():
    ess = torch.tensor([effective_sample_size(samples[BURN:, j]) for j in range(samples.shape[1])])
    print(f"{name:24s} {acc:10.2f} {ess.min():22.0f} / {ess.median():.0f}   (of {STEPS - BURN} kept)")

# Prediction: average the probability over posterior samples, instead of trusting one weight vector
samples = chains["Langevin (MALA)"][0][BURN:]
p_samples = torch.sigmoid(X[test] @ samples.T)                     # (patients, samples)
p_bayes, p_spread = p_samples.mean(1), p_samples.std(1)
p_map = torch.sigmoid(X[test] @ w_map)
for name, p in [("MAP (one weight vector)", p_map), ("posterior average", p_bayes)]:
    ll = (t[test] * p.log() + (1 - t[test]) * (1 - p).log()).mean()
    print(f"\n{name:24s} test accuracy {((p > 0.5) == t[test].bool()).double().mean():.3f}, "
          f"test log likelihood per patient {ll:.3f}", end="")
print()

# Which patients is the model unsure about? The ones whose probability varies most across the posterior.
print("\nmost uncertain test patients:")
for i in p_spread.argsort(descending=True)[:4]:
    lo, hi = p_samples[i].quantile(0.05).item(), p_samples[i].quantile(0.95).item()
    print(f"  truth {'benign   ' if t[test][i] else 'malignant'} MAP says {p_map[i]:.2f}, posterior {p_bayes[i]:.2f} "
          f"(90% interval {lo:.2f} to {hi:.2f})")

Path("outputs").mkdir(exist_ok=True)
fig, ax = plt.subplots(figsize=(8, 3))
for name, (s, _) in chains.items():
    ax.plot(s[:, 1], lw=0.7, label=name)
ax.set_xlabel("step"); ax.set_ylabel("weight of 'mean radius'"); ax.legend(fontsize=8)
fig.tight_layout(); fig.savefig("outputs/traces.png", dpi=110)
print("\nsaved outputs/traces.png")
