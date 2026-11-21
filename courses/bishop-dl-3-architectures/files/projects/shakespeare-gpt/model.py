"""A small GPT: a decoder-only transformer that predicts the next character (Bishop, section 12.3.1)."""
import math
import torch
from torch import nn


class CausalSelfAttention(nn.Module):
    def __init__(self, d, heads, ctx):
        super().__init__()
        self.heads = heads
        self.qkv, self.out = nn.Linear(d, 3 * d), nn.Linear(d, d)
        # the mask: position t may only look at positions 0..t, never at the future (section 12.3.1)
        self.register_buffer("future", torch.triu(torch.ones(ctx, ctx, dtype=torch.bool), diagonal=1))

    def forward(self, x):
        B, N, d = x.shape
        q, k, v = self.qkv(x).reshape(B, N, 3, self.heads, d // self.heads).permute(2, 0, 3, 1, 4)
        att = (q @ k.transpose(-2, -1)) / math.sqrt(d // self.heads)
        att = att.masked_fill(self.future[:N, :N], float("-inf")).softmax(-1)
        return self.out((att @ v).transpose(1, 2).reshape(B, N, d))


class Block(nn.Module):
    def __init__(self, d, heads, ctx):
        super().__init__()
        self.ln1, self.ln2 = nn.LayerNorm(d), nn.LayerNorm(d)
        self.attn = CausalSelfAttention(d, heads, ctx)
        self.mlp = nn.Sequential(nn.Linear(d, 4 * d), nn.GELU(), nn.Linear(4 * d, d))

    def forward(self, x):
        x = x + self.attn(self.ln1(x))
        return x + self.mlp(self.ln2(x))


class GPT(nn.Module):
    def __init__(self, vocab, d=128, heads=4, layers=4, ctx=128):
        super().__init__()
        self.ctx = ctx
        self.tok, self.pos = nn.Embedding(vocab, d), nn.Embedding(ctx, d)
        self.blocks = nn.Sequential(*[Block(d, heads, ctx) for _ in range(layers)])
        self.ln, self.head = nn.LayerNorm(d), nn.Linear(d, vocab)

    def forward(self, idx):
        x = self.tok(idx) + self.pos(torch.arange(idx.shape[1]))
        return self.head(self.ln(self.blocks(x)))              # logits for the next character at every position

    @torch.no_grad()
    def generate(self, idx, n, temperature=1.0, top_k=None, generator=None):
        """Sample one character at a time and feed it back in (sections 12.2.4 and 12.3.2)."""
        for _ in range(n):
            logits = self(idx[:, -self.ctx:])[:, -1] / temperature
            if top_k:
                kth = logits.topk(top_k).values[:, -1:]
                logits = logits.masked_fill(logits < kth, float("-inf"))
            nxt = torch.multinomial(logits.softmax(-1), 1, generator=generator)
            idx = torch.cat([idx, nxt], 1)
        return idx
