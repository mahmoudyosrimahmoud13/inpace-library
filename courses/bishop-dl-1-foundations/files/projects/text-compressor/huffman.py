"""A real compressor: a Huffman code built from the training text's character frequencies.
Shannon's theorem (section 2.5.1) says no code can average fewer bits than the entropy; Huffman gets within 1 bit."""
import bz2
import gzip
import heapq
import torch
from data import load_splits


def huffman_code(freqs):
    """freqs: {char: count}. Returns {char: '0101...'} with frequent characters getting short codes."""
    heap = [(f, i, {c: ""}) for i, (c, f) in enumerate(freqs.items())]
    heapq.heapify(heap)
    tie = len(heap)
    while len(heap) > 1:
        f1, _, left = heapq.heappop(heap)          # the two rarest groups ...
        f2, _, right = heapq.heappop(heap)
        merged = {c: "0" + code for c, code in left.items()} | {c: "1" + code for c, code in right.items()}
        heapq.heappush(heap, (f1 + f2, tie, merged))  # ... are joined, adding one bit to each of their codes
        tie += 1
    return heap[0][2]


def encode(text, code):
    return "".join(code[c] for c in text)


def decode(bits, code):
    back, out, current = {v: k for k, v in code.items()}, [], ""
    for b in bits:
        current += b
        if current in back:                         # no code is the start of another, so this is unambiguous
            out.append(back[current])
            current = ""
    return "".join(out)


if __name__ == "__main__":
    train, test = load_splits()
    alphabet = sorted(set(train) | set(test))
    freqs = {c: train.count(c) + 1 for c in alphabet}
    code = huffman_code(freqs)
    for c in [" ", "e", "t", "z", "Z", "&"]:
        print(f"{c!r:5s} appears {freqs[c] - 1:7,d} times -> code {code[c]}")

    bits = encode(test, code)
    assert decode(bits, code) == test, "decoding must give back the exact text"
    print(f"\ndecoded the test text back perfectly: {len(test):,} characters")
    counts = torch.tensor([freqs[c] for c in alphabet], dtype=torch.float)
    p = counts / counts.sum()
    entropy = -(p * torch.log2(p)).sum().item()
    print(f"{'entropy of the character distribution':40s} {entropy:.3f} bits/char")
    print(f"{'Huffman code on the test text':40s} {len(bits) / len(test):.3f} bits/char")
    raw = test.encode()
    print(f"{'gzip':40s} {8 * len(gzip.compress(raw, 9)) / len(test):.3f} bits/char")
    print(f"{'bzip2':40s} {8 * len(bz2.compress(raw, 9)) / len(test):.3f} bits/char")
    print(f"{'plain text file (1 byte per char)':40s} {8.0:.3f} bits/char")
