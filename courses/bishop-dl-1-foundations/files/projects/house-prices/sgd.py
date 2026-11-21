"""The same model trained by stochastic gradient descent (Bishop, section 4.1.5), the way you'd train it if the
data didn't fit in memory, and the way every network in this book is trained."""
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset
from data import load_splits
from basis import LocationBasis, design, rmse

torch.manual_seed(0)
d = load_splits()
basis = LocationBasis()
P_tr, P_va = design(*d["train"][:2], basis), design(*d["val"][:2], basis)
y_tr, y_va = d["train"][2], d["val"][2]

model = nn.Linear(P_tr.shape[1], 1, bias=False)          # the column of ones in Phi already gives the bias
opt = torch.optim.SGD(model.parameters(), lr=0.02, momentum=0.9, weight_decay=1e-6)
# (weight_decay plays the role of lambda)
loader = DataLoader(TensorDataset(P_tr, y_tr), batch_size=64, shuffle=True)
# Big steps first, small steps at the end, so SGD settles into the minimum instead of bouncing around it
schedule = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=30)
for epoch in range(1, 31):
    for P, y in loader:
        loss = ((model(P).squeeze(1) - y) ** 2).mean()
        opt.zero_grad(); loss.backward(); opt.step()
    schedule.step()
    if epoch in (1, 2, 5, 10, 20, 30):
        w = model.weight.detach().squeeze(0)
        print(f"epoch {epoch:2d}: train RMSE ${rmse(P_tr, w, y_tr):.1f}k, validation RMSE ${rmse(P_va, w, y_va):.1f}k")
