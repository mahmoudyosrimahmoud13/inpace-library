"""Project 3: pretrain the GPT on Shakespeare: predict the next token, again and again. Watch the loss fall and
the samples turn from noise into something like a play."""
import math
import time

import torch

from gpt import CONFIG, GPT
from p1_tokenizer import BPE

torch.manual_seed(1337)
torch.set_num_threads(max(1, torch.get_num_threads()))
STEPS, BATCH, LR = 2500, 32, 1e-3


def batches(data, block, batch):
    i = torch.randint(len(data) - block - 1, (batch,))
    return torch.stack([data[j:j + block] for j in i]), torch.stack([data[j + 1:j + block + 1] for j in i])


@torch.no_grad()
def estimate(model, data, n=40):
    model.eval()
    losses = [model(*batches(data, model.block, BATCH))[1].item() for _ in range(n)]
    model.train()
    return sum(losses) / n


@torch.no_grad()
def sample(model, bpe, prompt, n=40):
    model.eval()
    idx = torch.tensor([bpe.encode(prompt)])
    for _ in range(n):
        logits, _ = model(idx[:, -model.block:])
        idx = torch.cat([idx, torch.multinomial(logits[0, -1].softmax(-1), 1)[None]], 1)
    model.train()
    return bpe.decode(idx[0].tolist())


if __name__ == "__main__":
    bpe = BPE.load()
    data = torch.tensor(bpe.encode(open("shakespeare.txt", encoding="utf-8").read()))
    split = int(0.9 * len(data))
    train, val = data[:split], data[split:]          # the last 10% of the plays is never trained on
    model = GPT(**CONFIG)
    opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=0.1)
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1, (s + 1) / 100) * 0.5 * (1 + math.cos(math.pi * s / STEPS)))
    print(f"{len(train):,} training tokens, {len(val):,} validation tokens; {STEPS} steps of {BATCH} x {CONFIG['block']} tokens\n")
    t = time.perf_counter()
    for step in range(STEPS + 1):
        if step % 500 == 0:
            tl, vl = estimate(model, train), estimate(model, val)
            print(f"step {step:5}  train loss {tl:.2f}  validation loss {vl:.2f}  ({time.perf_counter() - t:.0f} s)")
            torch.manual_seed(step)
            print("   sample: " + repr(sample(model, bpe, "ROMEO:\n")[:110]))
        if step == STEPS:
            break
        x, y = batches(train, model.block, BATCH)
        _, loss = model(x, y)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        sched.step()
    torch.save({"model": model.state_dict(), "config": CONFIG, "val_loss": vl, "steps": STEPS}, "tinygpt.pt")
    print(f"\nSaved tinygpt.pt. Validation loss {vl:.2f} means the right next token gets, on average, a probability "
          f"like 1 in {math.exp(vl):.0f} (it started at 1 in {CONFIG['vocab']}).")
