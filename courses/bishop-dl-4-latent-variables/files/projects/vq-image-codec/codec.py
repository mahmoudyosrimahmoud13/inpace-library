"""A real image codec based on vector quantization (section 15.1.1): store a palette of K colours, and for each
pixel only the index of its colour, packed into log2(K) bits."""
import math
import struct
import zlib
import numpy as np
import torch
from kmeans import kmeans


def compress(img, K, seed=0, sample=20000, entropy=False):
    """img: (H, W, 3) uint8 array -> bytes. K-means runs on a random sample of pixels, for speed.
    entropy=True also squeezes the index stream with zlib: neighbouring pixels often share a colour."""
    H, W, _ = img.shape
    pixels = torch.tensor(img.reshape(-1, 3), dtype=torch.float32)
    g = torch.Generator().manual_seed(seed)
    centres, _, _ = kmeans(pixels[torch.randperm(len(pixels), generator=g)[:sample]], K, seed=seed)
    palette = centres.round().clamp(0, 255).to(torch.uint8)
    labels = torch.cdist(pixels, palette.float()).argmin(1).numpy()
    bits = max(1, math.ceil(math.log2(K)))
    bit_array = ((labels[:, None] >> np.arange(bits)[::-1]) & 1).astype(np.uint8)  # each index as `bits` bits
    body = np.packbits(bit_array.flatten()).tobytes()
    if entropy:
        body = zlib.compress(body, 9)
    header = struct.pack("<HHHBB", H, W, K, bits, int(entropy))
    return header + palette.numpy().tobytes() + body


def decompress(data):
    H, W, K, bits, entropy = struct.unpack("<HHHBB", data[:8])
    palette = np.frombuffer(data[8:8 + 3 * K], dtype=np.uint8).reshape(K, 3)
    body = data[8 + 3 * K:]
    if entropy:
        body = zlib.decompress(body)
    bit_array = np.unpackbits(np.frombuffer(body, dtype=np.uint8))[:H * W * bits].reshape(-1, bits)
    labels = (bit_array * (1 << np.arange(bits)[::-1])).sum(1)
    return palette[labels].reshape(H, W, 3)


def psnr(a, b):
    """Peak signal-to-noise ratio in decibels: higher is closer to the original (30+ dB looks good)."""
    mse = np.mean((a.astype(float) - b.astype(float)) ** 2)
    return 10 * math.log10(255 ** 2 / mse)
