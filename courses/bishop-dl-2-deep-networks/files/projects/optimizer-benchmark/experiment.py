"""One training run, fully described by a config dict, returning its learning curve."""
import torch
import torch.nn.functional as F
from torch import nn
from torch.utils.data import DataLoader, TensorDataset
from data import load_splits

(XTR, TTR), (XVA, TVA), _ = load_splits()


def network(batch_norm=False, init_std=None):
    layers, width = [], 784
    for h in [256, 256, 256]:
        layers.append(nn.Linear(width, h))
        if batch_norm:
            layers.append(nn.BatchNorm1d(h))                 # section 7.4.2
        layers.append(nn.ReLU())
        width = h
    layers.append(nn.Linear(width, 10))
    net = nn.Sequential(*layers)
    if init_std is not None:                                 # a deliberately chosen (bad) initialization
        for m in net:
            if isinstance(m, nn.Linear):
                nn.init.normal_(m.weight, std=init_std); nn.init.zeros_(m.bias)
    return net


OPTIMIZERS = {
    "sgd": lambda p, lr: torch.optim.SGD(p, lr=lr),
    "momentum": lambda p, lr: torch.optim.SGD(p, lr=lr, momentum=0.9),
    "rmsprop": lambda p, lr: torch.optim.RMSprop(p, lr=lr),
    "adam": lambda p, lr: torch.optim.Adam(p, lr=lr),
}


def run(cfg, epochs=5, seed=0):
    """cfg: {"opt": "adam", "lr": 1e-3, "schedule": "cosine" or None, "batch_norm": bool, "init_std": float or None}"""
    torch.manual_seed(seed)
    net = network(cfg.get("batch_norm", False), cfg.get("init_std"))
    opt = OPTIMIZERS[cfg["opt"]](net.parameters(), cfg["lr"])
    loader = DataLoader(TensorDataset(XTR, TTR), batch_size=128, shuffle=True)
    steps = epochs * len(loader)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, steps) if cfg.get("schedule") == "cosine" else None
    curve, step = [], 0
    for epoch in range(epochs):
        net.train()
        for x, t in loader:
            loss = F.cross_entropy(net(x), t)
            opt.zero_grad(); loss.backward(); opt.step()
            if sched:
                sched.step()
            step += 1
            if step % 50 == 0:
                curve.append((step, loss.item()))
    net.eval()
    with torch.no_grad():
        val_acc = (net(XVA).argmax(1) == TVA).float().mean().item()
    return {"curve": curve, "val_acc": val_acc, "final_loss": sum(l for _, l in curve[-10:]) / 10}
