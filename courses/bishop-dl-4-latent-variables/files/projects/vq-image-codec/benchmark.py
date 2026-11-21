"""Compress a photo with K = 2 to 256 colours, check the round trip, and compare file sizes with PNG and JPEG."""
import io
from pathlib import Path
import numpy as np
from PIL import Image
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.datasets import load_sample_image
from codec import compress, decompress, psnr

img = load_sample_image("china.jpg")                 # a 640 x 427 photo that ships with scikit-learn
H, W, _ = img.shape
raw = H * W * 3
Path("outputs").mkdir(exist_ok=True)


def saved_size(fmt, **kw):
    buf = io.BytesIO(); Image.fromarray(img).save(buf, fmt, **kw); return len(buf.getvalue())


print(f"photo: {W} x {H} pixels, raw size {raw:,} bytes (24 bits per pixel)\n")
print(f"{'format':14s} {'bytes':>9s} {'bits/pixel':>10s} {'PSNR (dB)':>9s}")
print(f"{'PNG (lossless)':14s} {saved_size('PNG'):9,d} {8 * saved_size('PNG') / (H * W):10.2f} {'perfect':>9s}")
jpg = saved_size("JPEG", quality=75)
buf = io.BytesIO(); Image.fromarray(img).save(buf, "JPEG", quality=75)
print(f"{'JPEG q75':14s} {jpg:9,d} {8 * jpg / (H * W):10.2f} {psnr(img, np.array(Image.open(buf))):9.1f}")
shown = {}
for K in [2, 4, 8, 16, 32, 64, 256]:
    data = compress(img, K)
    back = decompress(data)
    Path(f"outputs/china_K{K}.vq").write_bytes(data)
    print(f"{'VQ, K = ' + str(K):14s} {len(data):9,d} {8 * len(data) / (H * W):10.2f} {psnr(img, back):9.1f}")
    if K in (4, 16, 64):
        shown[K] = back
for K in [16, 32, 64]:
    data = compress(img, K, entropy=True)
    back = decompress(data)
    print(f"{'VQ+zlib, K=' + str(K):14s} {len(data):9,d} {8 * len(data) / (H * W):10.2f} {psnr(img, back):9.1f}")

fig, axes = plt.subplots(1, 4, figsize=(14, 2.9))
axes[0].imshow(img); axes[0].set_title("original (24 bits/pixel)")
for ax, (K, im) in zip(axes[1:], shown.items()):
    ax.imshow(im); ax.set_title(f"K = {K} colours ({np.log2(K):.0f} bits/pixel)")
for ax in axes: ax.axis("off")
fig.tight_layout(); fig.savefig("outputs/compare.png", dpi=100)
print("\nsaved outputs/compare.png")
