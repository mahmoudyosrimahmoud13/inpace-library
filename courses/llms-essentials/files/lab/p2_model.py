"""Project 2: build the transformer, look inside one attention layer, and check the model before training."""
import math

import torch

from gpt import CONFIG, GPT
from p1_tokenizer import BPE

torch.manual_seed(0)

if __name__ == "__main__":
    bpe = BPE.load()
    model = GPT(**CONFIG).eval()
    n = sum(p.numel() for p in model.parameters())
    print(f"1. A GPT with {CONFIG['layers']} blocks, {CONFIG['heads']} heads, {CONFIG['dim']} numbers per token, "
          f"a window of {CONFIG['block']} tokens: {n:,} parameters")
    for name, p in [("token embeddings", model.tok.weight), ("position embeddings", model.pos.weight),
                    ("one block", None)]:
        count = p.numel() if p is not None else sum(q.numel() for q in model.blocks[0].parameters())
        print(f"   {name:20} {count:8,}")

    s = " To be, or not to be"
    ids = torch.tensor([bpe.encode(s)])
    tokens = [bpe.vocab[i] for i in ids[0]]
    with torch.no_grad():
        logits, _ = model(ids)
    print(f"\n2. {s!r} -> {len(tokens)} tokens {tokens}")
    print(f"   output shape {tuple(logits.shape)}: for each position, a score for each of the {CONFIG['vocab']} tokens")

    w = model.blocks[0].attn.last_weights[0, 0]
    print("\n3. Attention weights of head 1 in block 1 (each row: what that token looks at). Untrained, so even-ish:")
    print("   " + " " * 8 + "".join(f"{t[:6]:>7}" for t in tokens))
    for t, row in zip(tokens, w):
        print(f"   {t[:7]:>8}" + "".join(f"{x:7.2f}" if x > 0 else "      ." for x in row.tolist()))
    print("   The dots are the causal mask: no token can look at a later one.")

    future = ids.clone()
    future[0, -1] = bpe.encode(" banana")[0]
    with torch.no_grad():
        changed, _ = model(future)
    same_before = torch.allclose(logits[0, :-1], changed[0, :-1], atol=1e-6)
    print(f"\n4. Change the last token: are the earlier positions' outputs unchanged? {same_before}")

    data = torch.tensor(bpe.encode(open("shakespeare.txt").read()[:20000]))
    x, y = data[:128].unsqueeze(0), data[1:129].unsqueeze(0)
    with torch.no_grad():
        _, loss = model(x, y)
    print(f"\n5. Loss before training: {loss.item():.2f}. A model guessing uniformly among {CONFIG['vocab']} tokens "
          f"scores ln({CONFIG['vocab']}) = {math.log(CONFIG['vocab']):.2f}, so the start is healthy.")
