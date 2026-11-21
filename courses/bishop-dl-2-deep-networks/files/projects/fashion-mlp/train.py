"""Train one network and report its accuracy. Example: python train.py --hidden 256 256 --epochs 8"""
import argparse
import time
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader, TensorDataset
from data import load_splits
from model import mlp, count_parameters


def accuracy(model, x, t):
    with torch.no_grad():
        return (model(x).argmax(1) == t).float().mean().item()


def train(hidden, epochs=8, seed=0, verbose=False):
    torch.manual_seed(seed)
    (xtr, ttr), (xva, tva), _ = load_splits()
    model = mlp(hidden)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    loader = DataLoader(TensorDataset(xtr, ttr), batch_size=128, shuffle=True)
    start = time.time()
    for epoch in range(1, epochs + 1):
        model.train()
        for x, t in loader:
            loss = F.cross_entropy(model(x), t)
            opt.zero_grad(); loss.backward(); opt.step()
        model.eval()
        if verbose:
            print(f"epoch {epoch}: train accuracy {accuracy(model, xtr, ttr):.3f}, validation {accuracy(model, xva, tva):.3f}")
    return model, accuracy(model, xtr, ttr), accuracy(model, xva, tva), time.time() - start


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--hidden", type=int, nargs="*", default=[256])
    ap.add_argument("--epochs", type=int, default=8)
    args = ap.parse_args()
    model, _, _, _ = train(args.hidden, args.epochs, verbose=True)
    print(f"{count_parameters(model):,} parameters")
    torch.save({"hidden": args.hidden, "state": model.state_dict()}, "model.pt")
