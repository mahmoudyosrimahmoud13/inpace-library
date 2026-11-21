# Paper topic classifier with a graph convolutional network

Predicts the research topic of 2,708 machine-learning papers (the Cora citation graph) from their words and their
citations, with a graph convolutional network written in plain PyTorch. Only 140 papers (20 per topic) have labels.

## Results (1,000 test papers)

| method | uses | test accuracy |
|---|---|---|
| MLP | words only | 0.534 |
| label propagation | citations only | 0.704 |
| GCN, 2 layers | words + citations | **0.796** |

Over-smoothing with depth (section 13.3.4):

| GCN layers | test accuracy | average similarity between papers |
|---|---|---|
| 2 | 0.788 | 0.65 |
| 4 | 0.777 | 0.52 |
| 6 | 0.711 | 0.52 |
| 8 | 0.196 | 1.00 (all papers look the same) |

## Run it

```bash
pip install -r requirements.txt
python train.py    # three methods compared
python depth.py    # deeper GCNs and over-smoothing
```

## What I learned

- 81% of citations link papers on the same topic; a GCN turns that structure into accuracy.
- Words and links carry different information: together they beat either one alone by 9 to 26 points.
- More message-passing layers are not better: by 8 layers, every paper's representation has blurred into the same vector.

Based on chapter 13 of *Deep Learning: Foundations and Concepts* (Bishop & Bishop, 2024).
