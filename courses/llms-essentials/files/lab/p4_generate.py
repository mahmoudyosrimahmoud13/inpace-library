"""Project 4: generate text. Sampling settings change the character of the output; a KV cache changes the speed."""
import time

import torch

from gpt import load
from p1_tokenizer import BPE


@torch.no_grad()
def generate(model, idx, n, temperature=1.0, top_k=None, top_p=None, use_cache=False):
    caches = [dict() for _ in model.blocks] if use_cache else None
    pos = 0
    x = idx
    for _ in range(n):
        if use_cache:
            if idx.shape[1] > model.block:
                break                                     # this simple cache stops at the window size
            logits, _ = model(x, caches=caches, start=pos)
            pos += x.shape[1]
        else:
            logits, _ = model(idx[:, -model.block:])
        logits = logits[0, -1] / max(temperature, 1e-6)
        if top_k:
            cut = torch.topk(logits, top_k).values[-1]
            logits[logits < cut] = float("-inf")
        probs = logits.softmax(-1)
        if top_p:
            p, i = probs.sort(descending=True)
            keep = p.cumsum(0) - p < top_p                # the smallest set of tokens covering top_p
            probs = torch.zeros_like(probs).scatter(0, i[keep], p[keep])
            probs /= probs.sum()
        nxt = probs.argmax()[None] if temperature == 0 else torch.multinomial(probs, 1)
        idx = torch.cat([idx, nxt[None]], 1)
        x = nxt[None]
    return idx


if __name__ == "__main__":
    model, ckpt = load()
    bpe = BPE.load()
    prompt = torch.tensor([bpe.encode("JULIET:\nO Romeo,")])
    print(f"The model from project 3 (validation loss {ckpt['val_loss']:.2f}). Prompt: 'JULIET:\\nO Romeo,'\n")
    for name, kw in [("greedy (temperature 0)", {"temperature": 0}),
                     ("temperature 0.7", {"temperature": 0.7}),
                     ("temperature 1.5", {"temperature": 1.5}),
                     ("temperature 1.0, top-k 20", {"temperature": 1.0, "top_k": 20}),
                     ("temperature 1.0, top-p 0.9", {"temperature": 1.0, "top_p": 0.9})]:
        torch.manual_seed(7)
        out = bpe.decode(generate(model, prompt, 40, **kw)[0].tolist())
        print(f"{name}:\n   {out!r}\n")

    torch.manual_seed(0)
    a = generate(model, prompt, 100, temperature=0)
    b = generate(model, prompt, 100, temperature=0, use_cache=True)
    print(f"With and without the KV cache, greedy output is identical: {torch.equal(a, b)}")
    for cache in (False, True):
        t = time.perf_counter()
        for _ in range(3):
            generate(model, prompt, 100, temperature=0, use_cache=cache)
        ms = (time.perf_counter() - t) / 300 * 1000
        print(f"   {'with' if cache else 'without'} KV cache: {ms:.1f} ms per token")
