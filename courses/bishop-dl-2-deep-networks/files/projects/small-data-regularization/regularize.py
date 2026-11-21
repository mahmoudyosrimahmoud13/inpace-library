"""Training with each regularizer of chapter 9, switched on by a config dict."""
import copy
import torch
import torch.nn.functional as F
from torch import nn
from data import load_splits

(XTR, TTR), (XVA, TVA), (XTE, TTE) = load_splits()
g = torch.Generator().manual_seed(0)
SMALL = torch.randperm(len(XTR), generator=g)[:1000]          # only 1,000 training images
X1K, T1K = XTR[SMALL], TTR[SMALL]
XVA, TVA = XVA[:2000], TVA[:2000]                             # a validation set for choices and early stopping


def network(dropout=0.0, conv=False):
    if conv:                                                  # a small convolutional network: a preview of part 3
        return nn.Sequential(nn.Unflatten(1, (1, 28, 28)),
                             nn.Conv2d(1, 16, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
                             nn.Conv2d(16, 32, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
                             nn.Flatten(), nn.Linear(32 * 7 * 7, 10))
    return nn.Sequential(nn.Linear(784, 512), nn.ReLU(), nn.Dropout(dropout),
                         nn.Linear(512, 512), nn.ReLU(), nn.Dropout(dropout),
                         nn.Linear(512, 10))


def augment(x):
    """Shift each image by up to 2 pixels in each direction (section 9.1.3: data augmentation)."""
    imgs = x.reshape(-1, 1, 28, 28)
    padded = F.pad(imgs, (2, 2, 2, 2))
    out = torch.empty_like(imgs)
    dx, dy = torch.randint(0, 5, (2, len(x)))
    for i in range(len(x)):
        out[i] = padded[i, :, dy[i]:dy[i] + 28, dx[i]:dx[i] + 28]
    return out.reshape(-1, 784)


def accuracy(model, x, t):
    model.eval()
    with torch.no_grad():
        return (model(x).argmax(1) == t).float().mean().item()


def train(cfg, seed=0, epochs=100):
    """cfg keys: weight_decay, dropout, augment (bool), early_stopping (bool), conv (bool)."""
    torch.manual_seed(seed)
    model = network(cfg.get("dropout", 0.0), cfg.get("conv", False))
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=cfg.get("weight_decay", 0.0))
    best, best_state, curve = -1.0, None, []
    for epoch in range(epochs):
        model.train()
        order = torch.randperm(len(X1K))
        for start in range(0, len(X1K), 100):
            idx = order[start:start + 100]
            x = augment(X1K[idx]) if cfg.get("augment") else X1K[idx]
            loss = F.cross_entropy(model(x), T1K[idx])
            opt.zero_grad(); loss.backward(); opt.step()
        val = accuracy(model, XVA, TVA)
        curve.append((accuracy(model, X1K, T1K), val))
        if cfg.get("early_stopping") and val > best:              # section 9.3.1
            best, best_state = val, copy.deepcopy(model.state_dict())
    if cfg.get("early_stopping"):
        model.load_state_dict(best_state)
    return model, curve
