"""Project 5: ship the inspector. One function, inspect(), that returns JSON; a robustness check on photos taken
in worse conditions; and its speed. Use it on any photo:  python p5_ship.py my_photo.png"""
import json
import sys
import time

import cv2
import numpy as np

from p2_measure import TRUE_COUNT
from p4_detect import split_touching


def inspect(img, mm_per_px=None):
    """Count and measure coins. Returns plain data a program (or a person) can use."""
    if img.ndim == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    scale = max(img.shape) / 384                       # the pipeline was tuned on a 384-pixel-wide photo
    work = cv2.resize(img, None, fx=1 / scale, fy=1 / scale) if abs(scale - 1) > 0.05 else img
    regions, _ = split_touching(work)
    diam = sorted(round(((x2 - x1) + (y2 - y1)) / 2 * scale, 1) for x1, y1, x2, y2 in regions)
    out = {"count": len(regions), "diameters_px": diam, "median_diameter_px": float(np.median(diam)) if diam else 0}
    if mm_per_px:
        out["median_diameter_mm"] = round(out["median_diameter_px"] * mm_per_px, 1)
    return out


def variants(img):
    """The same coins in worse conditions, as real cameras deliver them."""
    rng = np.random.default_rng(0)
    h, w = img.shape
    yield "as is", img
    yield "darker (-40)", np.clip(img.astype(int) - 40, 0, 255).astype(np.uint8)
    yield "brighter (+40)", np.clip(img.astype(int) + 40, 0, 255).astype(np.uint8)
    yield "uneven light", np.clip(img * np.linspace(0.6, 1.2, w)[None, :], 0, 255).astype(np.uint8)
    yield "sensor noise", np.clip(img + rng.normal(0, 15, img.shape), 0, 255).astype(np.uint8)
    yield "out of focus", cv2.GaussianBlur(img, (9, 9), 0)
    yield "turned 90 degrees", cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    yield "twice the resolution", cv2.resize(img, (w * 2, h * 2))
    yield "JPEG quality 20", cv2.imdecode(cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 20])[1], 0)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(json.dumps(inspect(cv2.imread(sys.argv[1])), indent=1))
        raise SystemExit
    img = cv2.imread("coins.png", cv2.IMREAD_GRAYSCALE)
    print("1. inspect() on the photo:")
    print("   " + json.dumps({k: v for k, v in inspect(img, mm_per_px=0.5).items() if k != "diameters_px"}))
    print(f"\n2. Robustness: the same {TRUE_COUNT} coins in worse conditions")
    ok = 0
    for name, im in variants(img):
        t = time.perf_counter()
        r = inspect(im)
        ms = (time.perf_counter() - t) * 1000
        ok += r["count"] == TRUE_COUNT
        print(f"   {name:22} count {r['count']:2} {'ok ' if r['count'] == TRUE_COUNT else 'OFF'}  "
              f"median diameter {r['median_diameter_px']:5.1f} px   {ms:5.0f} ms")
    print(f"\n   {ok} of 9 conditions give the right count." + (
        " Make it harder (the exercises) until something breaks: that's your next test, found before a user finds it."
        if ok == 9 else " The ones that don't are your next tests, found before a user finds them."))
