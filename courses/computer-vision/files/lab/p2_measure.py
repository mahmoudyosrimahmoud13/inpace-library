"""Project 2: count and measure the coins with classic vision (threshold, clean up, contours), then find the same
photo again after it's rotated and shrunk (keypoints, matching, RANSAC)."""
import cv2
import numpy as np

TRUE_COUNT = 24


def segment(img, method="adaptive"):
    """A mask: 255 on coins, 0 on the background."""
    blur = cv2.GaussianBlur(img, (5, 5), 0)
    if method == "otsu":                          # one threshold for the whole image
        _, mask = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    else:                                         # a threshold per neighbourhood: copes with uneven light
        mask = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 101, -5)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)          # remove specks
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)   # close gaps inside coins
    return mask


def find_coins(img, method="adaptive", min_area=150):
    mask = segment(img, method)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    coins = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < min_area:
            continue
        bx, by, bw, bh = cv2.boundingRect(c)
        edge = bx == 0 or by == 0 or bx + bw >= img.shape[1] or by + bh >= img.shape[0]
        if edge and area < 600:
            continue                                   # a small piece cut by the photo's edge: not a coin
        (x, y), r = cv2.minEnclosingCircle(c)
        circularity = 4 * np.pi * area / cv2.arcLength(c, True) ** 2      # 1.0 for a perfect circle
        coins.append({"x": x, "y": y, "r": r, "area": area, "circ": circularity, "box": cv2.boundingRect(c)})
    return sorted(coins, key=lambda c: (round(c["y"] / 40), c["x"])), mask


if __name__ == "__main__":
    img = cv2.imread("coins.png", cv2.IMREAD_GRAYSCALE)
    print(f"The photo has {TRUE_COUNT} coins.\n")
    for method in ("otsu", "adaptive"):
        coins, mask = find_coins(img, method)
        print(f"1. {method:8} threshold: {len(coins):2} objects found, {np.count_nonzero(mask) / mask.size:.0%} of "
              f"pixels marked as coin")
    coins, mask = find_coins(img)
    d = [2 * c["r"] for c in coins]
    print(f"\n2. Measurements ({len(coins)} objects): diameter {min(d):.0f} to {max(d):.0f} pixels, "
          f"median {np.median(d):.0f}; circularity {min(c['circ'] for c in coins):.2f} to "
          f"{max(c['circ'] for c in coins):.2f}")
    odd = [i for i, c in enumerate(coins, 1) if c["circ"] < 0.7]
    print(f"   the 3 biggest: {[round(x) for x in sorted(d)[-3:]]} px; the 3 smallest: {[round(x) for x in sorted(d)[:3]]} px")
    print(f"   not round (circularity under 0.7): objects {odd}. Look at p2_coins.png: two touching coins seen "
          f"as one, or a coin cut by the photo's edge. Day 4 splits the touching ones.")
    out = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    for i, c in enumerate(coins, 1):
        cv2.circle(out, (int(c["x"]), int(c["y"])), int(c["r"]), (0, 200, 0), 1)
        cv2.putText(out, str(i), (int(c["x"]) - 6, int(c["y"]) + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 255), 1)
    cv2.imwrite("p2_coins.png", out)
    print("   saved p2_coins.png with every coin circled and numbered")

    h, w = img.shape
    M = cv2.getRotationMatrix2D((w / 2, h / 2), 30, 0.8)        # the same photo, turned 30 degrees, 80% size
    moved = cv2.warpAffine(img, M, (w, h))
    orb = cv2.ORB_create(1000)
    k1, d1 = orb.detectAndCompute(img, None)
    k2, d2 = orb.detectAndCompute(moved, None)
    matches = sorted(cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(d1, d2), key=lambda m: m.distance)
    src = np.float32([k1[m.queryIdx].pt for m in matches])
    dst = np.float32([k2[m.trainIdx].pt for m in matches])
    A, inliers = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=3)
    angle = np.degrees(np.arctan2(A[1, 0], A[0, 0]))
    scale = np.hypot(A[0, 0], A[1, 0])
    print(f"\n3. Find the photo again, turned 30 degrees and shrunk to 80%: {len(k1)} and {len(k2)} keypoints, "
          f"{len(matches)} matches, {int(inliers.sum())} kept by RANSAC")
    print(f"   recovered: rotation {-angle:.1f} degrees, scale {scale:.2f}   (true: 30.0 and 0.80)")
