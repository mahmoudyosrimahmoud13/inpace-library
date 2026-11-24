"""Project 3: a small convolutional network that tells coin from background, trained on patches the classic
pipeline labelled for you. Train on the left half of the photo, test on the right half it never saw."""
import cv2
import numpy as np
import torch
from torch import nn

from p2_measure import segment

torch.manual_seed(0)
P = 24                                      # patch size in pixels


def patches(img, mask, x0, x1, step=4):
    """Patches centred on pixels deep inside a coin (label 1) or far from any coin (label 0). Pixels near a coin's
    edge are left out: their label would be a guess."""
    inside = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
    outside = cv2.distanceTransform(255 - mask, cv2.DIST_L2, 5)
    X, y = [], []
    h = P // 2
    for r in range(h, img.shape[0] - h, step):
        for c in range(max(h, x0), min(x1, img.shape[1] - h), step):
            if inside[r, c] > 6 or outside[r, c] > 6:
                X.append(img[r - h:r + h, c - h:c + h])
                y.append(1 if inside[r, c] > 6 else 0)
    return torch.tensor(np.array(X), dtype=torch.float32)[:, None] / 255, torch.tensor(y)


class CoinNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(1, 8, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),      # 24 -> 12
            nn.Conv2d(8, 16, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),     # 12 -> 6
            nn.Conv2d(16, 32, 3, padding=1), nn.ReLU(), nn.AdaptiveAvgPool2d(1),
            nn.Flatten(), nn.Linear(32, 2))

    def forward(self, x):
        return self.net(x)


def augment(x):
    """Random flips, 90-degree turns and brightness from 40% to 130%: the same coin, seen differently."""
    if torch.rand(1) < 0.5:
        x = x.flip(-1)
    x = torch.rot90(x, int(torch.randint(4, (1,))), (-2, -1))
    return (x * (0.4 + 0.9 * torch.rand(x.shape[0], 1, 1, 1))).clamp(0, 1)


if __name__ == "__main__":
    img = cv2.imread("coins.png", cv2.IMREAD_GRAYSCALE)
    mask = segment(img)
    mid = img.shape[1] // 2
    Xtr, ytr = patches(img, mask, 0, mid)
    Xte, yte = patches(img, mask, mid, img.shape[1])
    print(f"1. Patches of {P}x{P}: {len(Xtr):,} for training (left half, {ytr.float().mean():.0%} coin), "
          f"{len(Xte):,} for testing (right half, {yte.float().mean():.0%} coin)")

    bright = Xtr.mean((1, 2, 3))
    best = max(np.linspace(0, 1, 101), key=lambda t: ((bright > t).long() == ytr).float().mean())
    base = ((Xte.mean((1, 2, 3)) > best).long() == yte).float().mean()
    print(f"2. Baseline, 'bright patch = coin' (threshold {best:.2f} chosen on training patches): {base:.1%} right on test")

    model = CoinNet()
    print(f"3. CoinNet: {sum(p.numel() for p in model.parameters()):,} parameters")
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    for epoch in range(10):
        model.train()
        for idx in torch.randperm(len(Xtr)).split(64):
            loss = nn.functional.cross_entropy(model(augment(Xtr[idx])), ytr[idx])
            opt.zero_grad()
            loss.backward()
            opt.step()
        model.eval()
        with torch.no_grad():
            acc = (model(Xte).argmax(1) == yte).float().mean()
        print(f"   epoch {epoch + 1}: loss {loss.item():.3f}, test accuracy {acc:.1%}")
    with torch.no_grad():
        pred = model(Xte).argmax(1)
    tp, fp = int(((pred == 1) & (yte == 1)).sum()), int(((pred == 1) & (yte == 0)).sum())
    fn, tn = int(((pred == 0) & (yte == 1)).sum()), int(((pred == 0) & (yte == 0)).sum())
    print(f"\n4. On the right half: {tp} coin patches found, {fn} missed; {tn} background right, {fp} called coin")
    rule = (Xte.mean((1, 2, 3)) > best).long()
    fixed = int(((rule != yte) & (pred == yte)).sum())
    print(f"   the brightness rule got {int((rule != yte).sum())} test patches wrong; CoinNet got {fixed} of those "
          f"right: patches that brightness alone can't settle")
    torch.save(model.state_dict(), "coinnet.pt")
    print("   saved coinnet.pt")
