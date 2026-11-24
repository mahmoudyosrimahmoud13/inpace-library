"""Project 1: a byte-pair encoding (BPE) tokenizer, built from scratch and trained on Shakespeare.

Text in, numbers out: start from single characters, then repeatedly merge the most frequent pair of tokens into a
new token. Every later project uses this tokenizer."""
import json
import re
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
TEXT = (HERE / "shakespeare.txt").read_text(encoding="utf-8")
SPLIT = re.compile(r" ?[A-Za-z]+| ?[0-9]+| ?[^A-Za-z0-9\s]+|\s+")   # merges never cross word boundaries


class BPE:
    def __init__(self, merges=None, chars=None):
        self.chars = chars or sorted(set(TEXT))
        self.merges = [tuple(m) for m in (merges or [])]
        self.vocab = list(self.chars) + ["".join(m) for m in self.merges]
        self.ids = {t: i for i, t in enumerate(self.vocab)}
        self.rank = {m: i for i, m in enumerate(self.merges)}

    @classmethod
    def train(cls, text, vocab_size):
        bpe = cls()
        words = Counter(SPLIT.findall(text))
        seqs = {w: list(w) for w in words}
        while len(bpe.vocab) < vocab_size:
            pairs = Counter()
            for w, n in words.items():
                s = seqs[w]
                for a, b in zip(s, s[1:]):
                    pairs[a, b] += n
            if not pairs:
                break
            best = max(pairs, key=pairs.get)
            for w in words:
                seqs[w] = cls._merge(seqs[w], best)
            bpe.merges.append(best)
            bpe.vocab.append(best[0] + best[1])
        return cls(bpe.merges, bpe.chars)

    @staticmethod
    def _merge(seq, pair):
        out, i = [], 0
        while i < len(seq):
            if i + 1 < len(seq) and (seq[i], seq[i + 1]) == pair:
                out.append(seq[i] + seq[i + 1])
                i += 2
            else:
                out.append(seq[i])
                i += 1
        return out

    def _word(self, w):
        seq = list(w)
        while len(seq) > 1:
            ranked = [(self.rank.get((a, b), 1 << 30), i) for i, (a, b) in enumerate(zip(seq, seq[1:]))]
            r, i = min(ranked)
            if r == 1 << 30:
                break
            seq = seq[:i] + [seq[i] + seq[i + 1]] + seq[i + 2:]
        return seq

    def encode(self, text):
        return [self.ids[t] for w in SPLIT.findall(text) for t in self._word(w)]

    def decode(self, ids):
        return "".join(self.vocab[i] for i in ids)

    def save(self, path):
        Path(path).write_text(json.dumps({"chars": self.chars, "merges": self.merges}))

    @classmethod
    def load(cls, path=HERE / "tokenizer.json"):
        d = json.loads(Path(path).read_text())
        return cls(d["merges"], d["chars"])


if __name__ == "__main__":
    print(f"Shakespeare: {len(TEXT):,} characters, {len(set(TEXT))} different ones\n")
    t = time.perf_counter()
    bpe = BPE.train(TEXT, 512)
    print(f"1. Trained a BPE tokenizer with {len(bpe.vocab)} tokens in {time.perf_counter() - t:.0f} s")
    print(f"   the first merges: {[''.join(m) for m in bpe.merges[:12]]}")
    print(f"   some of the last: {[''.join(m) for m in bpe.merges[-8:]]}")
    s = "Shall I compare thee to a summer's day?"
    ids = bpe.encode(s)
    print(f"\n2. {s!r}\n   -> {len(ids)} tokens: {[bpe.vocab[i] for i in ids]}")
    print(f"   -> ids {ids}")
    print(f"   decode(encode(text)) == text: {bpe.decode(ids) == s}")
    all_ids = bpe.encode(TEXT)
    print(f"\n3. The whole text: {len(TEXT):,} characters -> {len(all_ids):,} tokens "
          f"({len(TEXT) / len(all_ids):.2f} characters per token)")
    for w in ["the", " the", "Romeo", " Juliet", " unbelievable", " computer"]:
        print(f"   {w!r:16} -> {[bpe.vocab[i] for i in bpe.encode(w)]}")
    print(f"   round trip on the whole text: {bpe.decode(all_ids) == TEXT}")
    bpe.save(HERE / "tokenizer.json")
    print("   saved tokenizer.json")
