"""Train the CNN on CIFAR-10. On a laptop CPU an epoch takes about a minute; on a GPU (or free Colab), seconds.
Example: python train.py --epochs 6"""
import argparse
import torch
import torch.nn.functional as F
from data import load_splits, normalize
from model import SmallCNN


def augment(x):
    """Random horizontal flips and random crops of 4-pixel padded images (section 9.1.3).
    A car seen in a mirror is still a car, so here, unlike Fashion-MNIST, flips are safe."""
    flip = torch.rand(len(x)) < 0.5
    x = torch.where(flip[:, None, None, None], x.flip(3), x)
    padded = F.pad(x, (4, 4, 4, 4), mode="reflect")
    i, j = torch.randint(0, 9, (2,))
    return padded[:, :, i:i + 32, j:j + 32]                     # one random crop per mini-batch, for speed


def evaluate(model, x, y, batch=1000):
    model.eval()
    with torch.no_grad():
        guesses = torch.cat([model(normalize(x[i:i + batch])).argmax(1) for i in range(0, len(x), batch)])
    return (guesses == y).float().mean().item()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=6)
    ap.add_argument("--width", type=int, default=16)
    ap.add_argument("--no-augment", action="store_true")
    args = ap.parse_args()
    torch.manual_seed(0)
    (xtr, ytr), (xva, yva), _ = load_splits()
    model = SmallCNN(args.width)
    print(f"{sum(p.numel() for p in model.parameters()):,} parameters")
    steps = args.epochs * (len(xtr) // 128)
    opt = torch.optim.AdamW(model.parameters(), lr=3e-3, weight_decay=5e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=3e-3, total_steps=steps)
    for epoch in range(1, args.epochs + 1):
        model.train()
        order = torch.randperm(len(xtr))
        for start in range(0, len(xtr) - 127, 128):
            idx = order[start:start + 128]
            x = normalize(xtr[idx])
            if not args.no_augment:
                x = augment(x)
            loss = F.cross_entropy(model(x), ytr[idx])
            opt.zero_grad(); loss.backward(); opt.step(); sched.step()
        print(f"epoch {epoch}: last loss {loss.item():.3f}, validation accuracy {evaluate(model, xva, yva):.3f}")
    torch.save({"width": args.width, "state": model.state_dict()}, "cnn.pt")
