"""Project 5: evaluate the model. Perplexity on unseen text against simple baselines, what it learned about the
format of a play, and how much it copies its training data."""
import math
import re
from collections import Counter

import torch

from gpt import load
from p1_tokenizer import BPE
from p4_generate import generate


@torch.no_grad()
def model_loss(model, data, block):
    total, n = 0.0, 0
    for i in range(0, len(data) - block - 1, block):
        x, y = data[i:i + block][None], data[i + 1:i + block + 1][None]
        total += model(x, y)[1].item() * block
        n += block
    return total / n


if __name__ == "__main__":
    model, ckpt = load()
    bpe = BPE.load()
    text = open("shakespeare.txt", encoding="utf-8").read()
    data = bpe.encode(text)
    split = int(0.9 * len(data))
    train, val = data[:split], data[split:]

    uni = Counter(train)
    uni_loss = -sum(math.log((uni[t] + 1) / (len(train) + 512)) for t in val) / len(val)
    big, ctx = Counter(zip(train, train[1:])), Counter(train[:-1])
    big_loss = -sum(math.log((big[a, b] + 1) / (ctx[a] + 512)) for a, b in zip(val, val[1:])) / (len(val) - 1)
    gpt_loss = model_loss(model, torch.tensor(val), model.block)
    print("1. Loss and perplexity on the last 10% of the text, never trained on (lower is better):")
    for name, l in [("uniform guess", math.log(512)), ("token frequencies (unigram)", uni_loss),
                    ("previous token only (bigram)", big_loss), ("TinyGPT", gpt_loss)]:
        print(f"   {name:30} loss {l:.2f}   perplexity {math.exp(l):6.1f}")
    print("   Perplexity is how many tokens the model is, in effect, choosing between at each step.\n")

    torch.manual_seed(3)
    samples = [bpe.decode(generate(model, torch.tensor([bpe.encode("\n\n")]), 150, temperature=0.8)[0].tolist())
               for _ in range(5)]
    speakers = [l for s in samples for l in s.splitlines() if re.fullmatch(r"[A-Z][A-Za-z ]+:", l)]
    print(f"2. Did it learn the format of a play? In 5 samples, {len(speakers)} lines are a speaker's name and a colon:")
    print(f"   {sorted(set(speakers))[:8]}")
    known = set(re.findall(r"^([A-Z][A-Za-z ]+):$", text, re.M))
    print(f"   {sum(s[:-1] in known for s in speakers)} of {len(speakers)} are real characters from the plays\n")

    train_text = bpe.decode(train)
    grams = lambda s, n: {s[i:i + n] for i in range(len(s) - n)}
    gen = "".join(samples)
    for n in (10, 20, 40):
        g = grams(gen, n)
        copied = sum(x in train_text for x in g) / len(g)
        print(f"3. Pieces of {n} characters in the samples found word for word in the training text: {copied:.0%}")
    print("   Short pieces are often common phrases; longer ones are almost never copied: it writes new text in the "
          "style of the plays.")
