"""Which graph is right? Score five structures by how well they predict passengers they never saw (5-fold
cross-validation), and by how well they predict survival."""
import torch
from data import load
from bayesnet import BayesNet

GRAPHS = {
    "no edges (all independent)": {"Class": [], "Sex": [], "Age": [], "Survived": []},
    "naive Bayes (Survived -> all)": {"Survived": [], "Class": ["Survived"], "Sex": ["Survived"], "Age": ["Survived"]},
    "our graph": {"Class": [], "Sex": [], "Age": ["Class"], "Survived": ["Class", "Sex", "Age"]},
    "our graph + Class -> Sex": {"Class": [], "Sex": ["Class"], "Age": ["Class"], "Survived": ["Class", "Sex", "Age"]},
    "every edge (full table)": {"Class": [], "Sex": ["Class"], "Age": ["Class", "Sex"], "Survived": ["Class", "Sex", "Age"]},
}
data = load()
n = len(data["Survived"])
folds = torch.randperm(n, generator=torch.Generator().manual_seed(0)) % 5

print(f"{'graph':32s} {'parameters':>10s} {'held-out log p per passenger':>29s} {'survival accuracy':>18s}")
for name, graph in GRAPHS.items():
    ll = right = 0.0
    for k in range(5):
        tr = {v: x[folds != k] for v, x in data.items()}
        te = {v: x[folds == k] for v, x in data.items()}
        net = BayesNet(graph).fit(tr)
        ll += net.log_likelihood(te)
        J = net.joint()                                    # predict survival from the other three variables
        p_yes = J[te["Class"], te["Sex"], te["Age"], 1] / J[te["Class"], te["Sex"], te["Age"]].sum(-1)
        right += ((p_yes > 0.5).long() == te["Survived"]).sum().item()
    print(f"{name:32s} {net.n_parameters():10d} {ll / n:29.3f} {right / n:18.3f}")
