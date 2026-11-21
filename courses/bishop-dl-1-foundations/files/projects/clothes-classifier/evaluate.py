"""Final evaluation on the 10,000 test images (used once): accuracy, what gets confused, whether the
probabilities can be trusted (calibration), and a reject option (Bishop, section 5.2.3)."""
from pathlib import Path
import torch
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from data import load_splits, CLASSES
from models import GaussianClassifier, SoftmaxRegression

(xtr, ttr), _, (xte, tte) = load_splits()
model = SoftmaxRegression()
model.load_state_dict(torch.load("softmax.pt"))
with torch.no_grad():
    probs = {"softmax regression": torch.softmax(model(xte), 1),
             "Gaussian classifier": torch.softmax(GaussianClassifier().fit(xtr, ttr).logits(xte), 1)}

p = probs["softmax regression"]
guess = p.argmax(1)
print(f"TEST accuracy, softmax regression: {(guess == tte).float().mean():.3f}\n")

confusion = torch.zeros(10, 10, dtype=torch.long)
confusion.index_put_((tte, guess), torch.ones_like(tte), accumulate=True)
print("per-class accuracy:")
for k in confusion.diag().float().div(confusion.sum(1)).argsort():
    worst = confusion[k].clone(); worst[k] = 0
    print(f"  {CLASSES[k]:10s} {confusion[k, k] / confusion[k].sum():.2f}   most often mistaken for {CLASSES[worst.argmax()]}")


def calibration(p, t, bins=10):
    """Group predictions by confidence; in a calibrated model, 80%-confident predictions are right 80% of the time."""
    conf, guess = p.max(1)
    edges = torch.linspace(0, 1, bins + 1)
    rows, ece = [], 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf > lo) & (conf <= hi)
        if m.sum() > 0:
            acc, c = (guess[m] == t[m]).float().mean().item(), conf[m].mean().item()
            rows.append((c, acc))
            ece += m.float().mean().item() * abs(acc - c)          # expected calibration error
    return rows, ece


Path("outputs").mkdir(exist_ok=True)
plt.figure(figsize=(4.5, 4.5))
plt.plot([0, 1], [0, 1], "k:", label="perfectly calibrated")
print()
for name, q in probs.items():
    rows, ece = calibration(q, tte)
    print(f"{name:20s} expected calibration error {ece:.3f}")
    plt.plot(*zip(*rows), "o-", label=name)
plt.xlabel("confidence"); plt.ylabel("accuracy"); plt.legend(); plt.title("Calibration on the test set")
plt.tight_layout(); plt.savefig("outputs/calibration.png", dpi=120)

print("\nreject option: refuse the least confident images, and pass them to a human")
conf = p.max(1).values
for share in [0.0, 0.1, 0.2, 0.3]:
    theta = torch.quantile(conf, share)
    keep = conf >= theta
    print(f"  refuse {share:.0%} (confidence below {theta:.2f}): accuracy on the rest {(guess[keep] == tte[keep]).float().mean():.3f}")
print("\nsaved outputs/calibration.png")
