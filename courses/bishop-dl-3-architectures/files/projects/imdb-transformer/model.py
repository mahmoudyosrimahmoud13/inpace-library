"""A transformer encoder for text, with self-attention written out by hand (Bishop, section 12.1)."""
import math
import torch
from torch import nn


class SelfAttention(nn.Module):
    """Multi-head self-attention (sections 12.1.3 to 12.1.6): every word looks at every other word."""
    def __init__(self, d, heads):
        super().__init__()
        self.heads, self.dk = heads, d // heads
        self.qkv = nn.Linear(d, 3 * d)             # queries, keys and values, all heads at once
        self.out = nn.Linear(d, d)

    def forward(self, x, pad_mask):
        B, N, d = x.shape
        q, k, v = self.qkv(x).reshape(B, N, 3, self.heads, self.dk).permute(2, 0, 3, 1, 4)   # each (B, heads, N, dk)
        scores = q @ k.transpose(-2, -1) / math.sqrt(self.dk)          # scaled dot products (equation 12.14)
        scores = scores.masked_fill(pad_mask[:, None, None, :], float("-inf"))   # never attend to padding
        attn = scores.softmax(-1)
        return self.out((attn @ v).transpose(1, 2).reshape(B, N, d))


class Block(nn.Module):
    """Attention + a small MLP, each with a residual connection and layer normalization (section 12.1.7)."""
    def __init__(self, d, heads):
        super().__init__()
        self.ln1, self.ln2 = nn.LayerNorm(d), nn.LayerNorm(d)
        self.attn = SelfAttention(d, heads)
        self.mlp = nn.Sequential(nn.Linear(d, 4 * d), nn.GELU(), nn.Linear(4 * d, d))

    def forward(self, x, pad_mask):
        x = x + self.attn(self.ln1(x), pad_mask)
        return x + self.mlp(self.ln2(x))


class SentimentTransformer(nn.Module):
    def __init__(self, vocab_size, d=64, heads=4, layers=2, max_len=200):
        super().__init__()
        self.embed = nn.Embedding(vocab_size, d, padding_idx=0)
        self.pos = nn.Parameter(torch.zeros(1, max_len, d))           # learned positions (section 12.1.9)
        self.blocks = nn.ModuleList(Block(d, heads) for _ in range(layers))
        self.pool_query = nn.Linear(d, 1)                              # attention pooling: a score per word
        self.head = nn.Linear(d, 2)

    def forward(self, ids, return_weights=False):
        pad = ids == 0
        x = self.embed(ids) + self.pos[:, :ids.shape[1]]
        for block in self.blocks:
            x = block(x, pad)
        w = self.pool_query(x).squeeze(-1).masked_fill(pad, float("-inf")).softmax(-1)   # which words matter
        logits = self.head((w[..., None] * x).sum(1))
        return (logits, w) if return_weights else logits


class BagOfWords(nn.Module):
    """Baseline: average the word embeddings, ignoring order and context completely."""
    def __init__(self, vocab_size, d=64):
        super().__init__()
        self.embed = nn.Embedding(vocab_size, d, padding_idx=0)
        self.head = nn.Linear(d, 2)

    def forward(self, ids):
        mask = (ids > 0).float()[..., None]
        return self.head((self.embed(ids) * mask).sum(1) / mask.sum(1).clamp(min=1))
