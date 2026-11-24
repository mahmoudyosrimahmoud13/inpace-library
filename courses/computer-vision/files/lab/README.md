# Coin inspector

The running project of the inPace course "Computer vision: from pixels to modern models": find, count and measure
the 24 coins in `coins.png` (a sample image from scikit-image, public domain), one step a day.

| File | Day | What it adds |
|---|---|---|
| `p1_pixels.py` | 1 | Pixels, a histogram, blur and edges, your own convolution |
| `p2_measure.py` | 2 | Thresholds, contours and measurements; keypoints, matching and RANSAC |
| `p3_cnn.py` | 3 | A small CNN trained on automatically labelled patches |
| `p4_detect.py` | 4 | Watershed for touching coins; a detector with NMS and IoU |
| `p5_ship.py` | 5 | `inspect()`, robustness tests and speed |

```bash
pip install opencv-python-headless scikit-image numpy torch
python p1_pixels.py
```
