"""Train the GPT on Tiny Shakespeare and measure it in bits per character, like the compressors of part 1."""
import argparse
import math
import torch
import torch.nn.functional as F
from data import load_splits
from model import GPT

ap = argparse.ArgumentParser()
ap.add_argument("--steps", type=int, default=1500)
args = ap.parse_args()

torch.manual_seed(0)
train, test = load_splits()
chars = sorted(set(train + test))
stoi = {c: i for i, c in enumerate(chars)}
encode = lambda s: torch.tensor([stoi[c] for c in s])
tr, te = encode(train), encode(test)
model = GPT(len(chars))
print(f"{sum(p.numel() for p in model.parameters()):,} parameters, context {model.ctx} characters")


def batch(data, size=32):
    i = torch.randint(0, len(data) - model.ctx - 1, (size,))
    x = torch.stack([data[j:j + model.ctx] for j in i])
    return x, torch.stack([data[j + 1:j + model.ctx + 1] for j in i])     # targets: the same text, shifted by one


@torch.no_grad()
def bits_per_char(data, n=20):
    model.eval()
    g = torch.Generator().manual_seed(1)
    losses = []
    for _ in range(n):
        i = torch.randint(0, len(data) - model.ctx - 1, (32,), generator=g)
        x = torch.stack([data[j:j + model.ctx] for j in i]); y = torch.stack([data[j + 1:j + model.ctx + 1] for j in i])
        losses.append(F.cross_entropy(model(x).flatten(0, 1), y.flatten()).item())
    model.train()
    return sum(losses) / n / math.log(2)                     # cross-entropy in nats -> bits


opt = torch.optim.AdamW(model.parameters(), lr=3e-3, weight_decay=0.1)
sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=3e-3, total_steps=args.steps)
for step in range(1, args.steps + 1):
    x, y = batch(tr)
    loss = F.cross_entropy(model(x).flatten(0, 1), y.flatten())
    opt.zero_grad(); loss.backward()
    torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
    opt.step(); sched.step()
    if step % 300 == 0 or step == 1:
        print(f"step {step:5d}: test {bits_per_char(te):.3f} bits/char")
torch.save({"model": model.state_dict(), "chars": chars}, "gpt.pt")
