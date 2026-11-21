"""Ablation study on 1,000 training images: each regularizer alone, all together, model averaging,
and a different architecture. Then the test set, once."""
import torch
from regularize import train, accuracy, X1K, T1K, XVA, TVA, XTE, TTE

STUDY = {
    "no regularization": {},
    "weight decay 0.1": {"weight_decay": 0.1},
    "dropout 0.5": {"dropout": 0.5},
    "early stopping": {"early_stopping": True},
    "data augmentation (shifts)": {"augment": True},
    "all of the above": {"weight_decay": 0.1, "dropout": 0.5, "early_stopping": True, "augment": True},
    "small CNN, no regularization": {"conv": True},
}
models = {}
print(f"{'setup':30s} {'train acc':>9s} {'val acc':>8s}")
for name, cfg in STUDY.items():
    model, _ = train(cfg)
    models[name] = model
    print(f"{name:30s} {accuracy(model, X1K, T1K):9.3f} {accuracy(model, XVA, TVA):8.3f}")

# How big is the noise? The same setup with different random seeds.
seeds = [accuracy(train({}, seed=s)[0], XVA, TVA) for s in (1, 2, 3)]
print(f"\nno regularization, seeds 1-3: {', '.join(f'{a:.3f}' for a in seeds)}  (spread {max(seeds) - min(seeds):.3f})")

# Model averaging (section 9.6): average the predicted probabilities of 5 networks trained with different seeds
ensemble = [models["dropout 0.5"]] + [train({"dropout": 0.5}, seed=s)[0] for s in (1, 2, 3, 4)]


def ensemble_accuracy(x, t):
    with torch.no_grad():
        p = sum(torch.softmax(m.eval()(x), 1) for m in ensemble)
    return (p.argmax(1) == t).float().mean().item()


print(f"average of 5 dropout networks: val acc {ensemble_accuracy(XVA, TVA):.3f}")

print("\nTEST set (10,000 images), used once:")
print(f"  no regularization            {accuracy(models['no regularization'], XTE, TTE):.3f}")
print(f"  average of 5 dropout MLPs    {ensemble_accuracy(XTE, TTE):.3f}")
print(f"  small CNN                    {accuracy(models['small CNN, no regularization'], XTE, TTE):.3f}")
