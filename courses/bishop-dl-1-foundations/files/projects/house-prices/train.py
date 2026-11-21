"""Compare models on the validation set, choose lambda, then test the final model once."""
import torch
from data import load_splits
from basis import LocationBasis, design, fit_closed_form, rmse

d = load_splits()
(Xtr, Ltr, ytr), (Xva, Lva, yva), (Xte, Lte, yte) = d["train"], d["val"], d["test"]
print(f"always guess the average:     validation RMSE ${((yva - ytr.mean()) ** 2).mean().sqrt():.1f}k")

w = fit_closed_form(design(Xtr, Ltr), ytr, 0.0)
print(f"linear in the 5 features:     validation RMSE ${rmse(design(Xva, Lva), w, yva):.1f}k")

Phi_raw = lambda X, L: design(torch.cat([X, (L - Ltr.mean(0)) / Ltr.std(0)], 1), L)
w = fit_closed_form(Phi_raw(Xtr, Ltr), ytr, 0.0)
print(f"+ latitude and longitude:     validation RMSE ${rmse(Phi_raw(Xva, Lva), w, yva):.1f}k")

print("\n+ 144 Gaussian basis functions over the map:")
basis = LocationBasis()
P_tr, P_va = design(Xtr, Ltr, basis), design(Xva, Lva, basis)
scores = {}
for lam in [0.0, 0.01, 0.1, 1.0, 10.0, 100.0]:
    try:
        w = fit_closed_form(P_tr, ytr, lam)
    except torch.linalg.LinAlgError:
        print(f"  lambda {lam:<6g} cannot be solved: the matrix is singular")
        continue
    scores[lam] = rmse(P_va, w, yva)
    print(f"  lambda {lam:<6g} train RMSE ${rmse(P_tr, w, ytr):.1f}k   validation RMSE ${scores[lam]:.1f}k")
lam = min(scores, key=scores.get)

# Final model: refit on train + validation with the chosen lambda, then the test set, once
X = torch.cat([Xtr, Xva]); L = torch.cat([Ltr, Lva]); y = torch.cat([ytr, yva])
w = fit_closed_form(design(X, L, basis), y, lam)
print(f"\nchosen lambda = {lam:g}. TEST RMSE ${rmse(design(Xte, Lte, basis), w, yte):.1f}k")
torch.save({"w": w, "lam": lam}, "model.pt")
