"""Project 1: the coin inspector starts with pixels. Load the photo, look at its numbers, blur it, find edges.

The photo is scikit-image's `coins`: 24 Greek coins on a dark background (Pompeii collection, public domain).
From today to day 5 you build an inspector that finds, counts and measures them."""
import time

import cv2
import numpy as np

img = cv2.imread("coins.png", cv2.IMREAD_GRAYSCALE)

if __name__ == "__main__":
    print(f"1. The image is an array: shape {img.shape} (rows, columns), type {img.dtype}, "
          f"values {img.min()} to {img.max()}, mean {img.mean():.1f}")
    print(f"   the top-left 4 x 6 pixels:\n{img[:4, :6]}")
    hist = np.bincount(img.ravel(), minlength=256)
    print("\n2. Brightness histogram (8 bins of 32 values):")
    for i in range(8):
        n = hist[i * 32:(i + 1) * 32].sum()
        print(f"   {i * 32:3}-{i * 32 + 31:3} {'#' * int(60 * n / img.size):60} {n / img.size:5.1%}")
    print("   Most pixels are the dark background; the coins are the brighter half. Day 2 splits them.")

    noisy = np.clip(img + np.random.default_rng(0).normal(0, 25, img.shape), 0, 255).astype(np.uint8)
    print("\n3. Edges (Canny), on the clean image, on a noisy copy, and on the noisy copy blurred first:")
    for name, im in [("clean", img), ("noisy", noisy), ("noisy, Gaussian blur 5x5", cv2.GaussianBlur(noisy, (5, 5), 0))]:
        edges = cv2.Canny(im, 100, 200)
        print(f"   {name:26} {np.count_nonzero(edges):6,} edge pixels")
    print("   Noise makes thousands of false edges; a blur removes most of them first.")

    k = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], np.float32)       # Sobel: brightness change left to right
    t = time.perf_counter()
    mine = cv2.filter2D(img.astype(np.float32), -1, k)
    ref = cv2.Sobel(img.astype(np.float32), cv2.CV_32F, 1, 0, ksize=3)
    print(f"\n4. Your own 3x3 convolution equals OpenCV's Sobel filter: {np.allclose(mine, ref)} "
          f"({(time.perf_counter() - t) * 1000:.1f} ms)")
    cv2.imwrite("p1_edges.png", np.hstack([img, cv2.Canny(cv2.GaussianBlur(img, (5, 5), 0), 100, 200)]))
    print("   saved p1_edges.png: the photo and its edges side by side")
