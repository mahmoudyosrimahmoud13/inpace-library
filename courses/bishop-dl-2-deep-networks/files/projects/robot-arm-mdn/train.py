"""Train both networks on 20,000 random poses and measure how close each one's answer puts the hand."""
import torch
from arm import forward, sample
from models import Regressor, MDN

torch.manual_seed(0)
x_tr, t_tr = sample(20000, seed=0)
x_te, t_te = sample(2000, seed=1)


def fit(model, steps=4000):
    opt = torch.optim.Adam(model.parameters(), lr=3e-3)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, steps)
    for step in range(steps):
        idx = torch.randint(0, len(x_tr), (256,))
        loss = model.loss(x_tr[idx], t_tr[idx])
        opt.zero_grad(); loss.backward(); opt.step(); sched.step()
    return model


def reach_error(model):
    """Distance between where we asked the hand to go and where the predicted angles really put it."""
    with torch.no_grad():
        return (forward(model(x_te)) - x_te).norm(dim=1)


for name, model in [("squared-error network", Regressor()), ("mixture density network", MDN())]:
    fit(model)
    err = reach_error(model)
    print(f"{name:24s} median miss {err.median():.3f}, worst 10% miss more than {err.quantile(0.9):.3f} "
          f"(arm length {1.7})")
    torch.save(model.state_dict(), "mdn.pt" if isinstance(model, MDN) else "regressor.pt")
