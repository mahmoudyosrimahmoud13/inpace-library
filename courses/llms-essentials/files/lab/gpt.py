"""A small GPT: token and position embeddings, a stack of transformer blocks (causal self-attention + MLP), and
a head that scores every token in the vocabulary. The same design as GPT-2, only tiny."""
import math

import torch
from torch import nn
from torch.nn import functional as F

CONFIG = {"vocab": 512, "block": 128, "dim": 128, "heads": 4, "layers": 4, "dropout": 0.1}


class SelfAttention(nn.Module):
    def __init__(self, dim, heads, block, dropout):
        super().__init__()
        self.heads = heads
        self.qkv = nn.Linear(dim, 3 * dim)       # queries, keys and values for all heads at once
        self.out = nn.Linear(dim, dim)
        self.drop = nn.Dropout(dropout)
        self.register_buffer("mask", torch.tril(torch.ones(block, block)).bool())   # see only the past

    def forward(self, x, cache=None):
        B, T, C = x.shape
        q, k, v = self.qkv(x).split(C, dim=2)
        q, k, v = (t.view(B, T, self.heads, C // self.heads).transpose(1, 2) for t in (q, k, v))
        if cache is not None:                    # generation with a KV cache: reuse the keys and values so far
            if "k" in cache:
                k, v = torch.cat([cache["k"], k], 2), torch.cat([cache["v"], v], 2)
            cache["k"], cache["v"] = k, v
        S = k.shape[2]
        att = (q @ k.transpose(-2, -1)) / math.sqrt(k.shape[-1])          # how much each token looks at each other
        att = att.masked_fill(~self.mask[S - T:S, :S], float("-inf"))
        self.last_weights = att.softmax(-1)
        y = self.drop(self.last_weights) @ v
        return self.out(y.transpose(1, 2).contiguous().view(B, T, C))


class Block(nn.Module):
    def __init__(self, dim, heads, block, dropout):
        super().__init__()
        self.ln1, self.ln2 = nn.LayerNorm(dim), nn.LayerNorm(dim)
        self.attn = SelfAttention(dim, heads, block, dropout)
        self.mlp = nn.Sequential(nn.Linear(dim, 4 * dim), nn.GELU(), nn.Linear(4 * dim, dim), nn.Dropout(dropout))

    def forward(self, x, cache=None):
        x = x + self.attn(self.ln1(x), cache)    # residual connections: each block adds to the stream
        return x + self.mlp(self.ln2(x))


class GPT(nn.Module):
    def __init__(self, vocab, block, dim, heads, layers, dropout):
        super().__init__()
        self.block = block
        self.tok = nn.Embedding(vocab, dim)
        self.pos = nn.Embedding(block, dim)
        self.blocks = nn.ModuleList(Block(dim, heads, block, dropout) for _ in range(layers))
        self.ln = nn.LayerNorm(dim)
        self.head = nn.Linear(dim, vocab, bias=False)
        self.head.weight = self.tok.weight       # weight tying, as in GPT-2
        self.apply(self._init)

    @staticmethod
    def _init(m):
        """Small random starting weights, as GPT-2 does. PyTorch's default for embeddings (spread 1.0) would make
        the first predictions wildly confident and the starting loss huge."""
        if isinstance(m, (nn.Linear, nn.Embedding)):
            nn.init.normal_(m.weight, std=0.02)
        if isinstance(m, nn.Linear) and m.bias is not None:
            nn.init.zeros_(m.bias)

    def forward(self, idx, targets=None, caches=None, start=0):
        T = idx.shape[1]
        x = self.tok(idx) + self.pos(torch.arange(start, start + T, device=idx.device))
        for i, b in enumerate(self.blocks):
            x = b(x, caches[i] if caches is not None else None)
        logits = self.head(self.ln(x))
        loss = None if targets is None else F.cross_entropy(logits.view(-1, logits.shape[-1]), targets.view(-1))
        return logits, loss


def load(path="tinygpt.pt"):
    ckpt = torch.load(path, weights_only=True)
    model = GPT(**ckpt["config"])
    model.load_state_dict(ckpt["model"])
    return model.eval(), ckpt
