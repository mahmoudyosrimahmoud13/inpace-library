"""Project 4: split touching coins with watershed segmentation, then turn CoinNet into a detector (a score map,
candidate boxes, non-maximum suppression) and grade it against the segmentation with IoU."""
import cv2
import numpy as np
import torch
from skimage.feature import peak_local_max
from skimage.segmentation import watershed

from p2_measure import TRUE_COUNT, find_coins, segment
from p3_cnn import P, CoinNet


def split_touching(img, min_area=150):
    """Watershed: each coin's centre is a peak of the distance-to-background map; 'flood' from each peak until the
    floods meet. Touching coins become separate regions."""
    mask = segment(img)
    dist = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
    peaks = peak_local_max(dist, min_distance=12, threshold_abs=8, labels=mask > 0)
    markers = np.zeros(mask.shape, np.int32)
    for i, (r, c) in enumerate(peaks, 1):
        markers[r, c] = i
    labels = watershed(-dist, markers, mask=mask > 0)
    regions = []
    for i in range(1, labels.max() + 1):
        ys, xs = np.nonzero(labels == i)
        if len(ys) >= min_area:
            regions.append((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    return regions, labels


def iou(a, b):
    """Intersection over union of two boxes (x1, y1, x2, y2): 1 is the same box, 0 no overlap."""
    w = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    h = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = w * h
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)


def nms(boxes, scores, thresh=0.3):
    """Non-maximum suppression: keep the best box, drop boxes that overlap it too much, repeat."""
    keep = []
    for i in np.argsort(scores)[::-1]:
        if all(iou(boxes[i], boxes[j]) < thresh for j in keep):
            keep.append(i)
    return keep


def detect(img, model, step=4):
    """Score every position with CoinNet. Every position confidently inside a coin proposes a box, sized from its
    distance to the nearest low-score area, so each coin gets many overlapping boxes. NMS will pick one."""
    h = P // 2
    pad = cv2.copyMakeBorder(img, h, h, h, h, cv2.BORDER_REFLECT)
    rows, cols = range(0, img.shape[0], step), range(0, img.shape[1], step)
    crops = np.array([pad[r:r + P, c:c + P] for r in rows for c in cols], np.float32)[:, None] / 255
    with torch.no_grad():
        prob = model(torch.from_numpy(crops)).softmax(1)[:, 1].numpy().reshape(len(rows), len(cols))
    heat = cv2.resize(prob, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_LINEAR)
    inside = cv2.distanceTransform((heat > 0.5).astype(np.uint8), cv2.DIST_L2, 5)
    boxes, scores = [], []
    for r in range(0, img.shape[0], step):
        for c in range(0, img.shape[1], step):
            if inside[r, c] < 6:
                continue
            rad = inside[r, c] + 4
            boxes.append((c - rad, r - rad, c + rad, r + rad))
            scores.append(float(inside[r, c] * heat[r, c]))
    return boxes, scores, heat


def grade(pred, truth, thresh=0.5):
    matched, used = 0, set()
    for p in pred:
        best = max(((iou(p, t), j) for j, t in enumerate(truth) if j not in used), default=(0, None))
        if best[0] >= thresh:
            matched += 1
            used.add(best[1])
    return matched, len(pred) - matched, len(truth) - matched


if __name__ == "__main__":
    img = cv2.imread("coins.png", cv2.IMREAD_GRAYSCALE)
    contours, _ = find_coins(img)
    regions, labels = split_touching(img)
    print(f"1. Counting the {TRUE_COUNT} coins: contours (day 2) found {len(contours)}, watershed finds {len(regions)}")
    out = cv2.applyColorMap((labels * 37 % 255).astype(np.uint8), cv2.COLORMAP_JET)
    out[labels == 0] = 0
    cv2.imwrite("p4_watershed.png", np.hstack([cv2.cvtColor(img, cv2.COLOR_GRAY2BGR), out]))
    print("   saved p4_watershed.png: every coin its own colour")

    model = CoinNet()
    model.load_state_dict(torch.load("coinnet.pt", weights_only=True))
    model.eval()
    boxes, scores, heat = detect(img, model)
    print(f"\n2. CoinNet as a detector: {len(boxes)} candidate boxes from the score map")
    def run(t, min_score=0.0):
        idx = [i for i, sc in enumerate(scores) if sc >= min_score]
        keep = [idx[k] for k in nms([boxes[i] for i in idx], [scores[i] for i in idx], t)] if t < 1 else idx
        return keep
    print("   (right = IoU of 0.5 or more with a watershed box)")
    for label, t, ms in [("no NMS", 1.0, 0), ("NMS at IoU 0.5", 0.5, 0), ("NMS at IoU 0.3", 0.3, 0),
                         ("score >= 10, then NMS 0.3", 0.3, 10)]:
        keep = run(t, ms)
        tp, fp, fn = grade([boxes[i] for i in keep], regions)
        print(f"   {label:27} {len(keep):5} boxes: {tp} right, {fp} extra, {fn} missed")
    keep = run(0.3, 10)
    vis = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    for i in keep:
        x1, y1, x2, y2 = map(int, boxes[i])
        cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 200, 255), 1)
    cv2.imwrite("p4_detections.png", np.hstack([vis, cv2.applyColorMap((heat * 255).astype(np.uint8), cv2.COLORMAP_VIRIDIS)]))
    print("   saved p4_detections.png: the boxes after NMS, and the score map")
