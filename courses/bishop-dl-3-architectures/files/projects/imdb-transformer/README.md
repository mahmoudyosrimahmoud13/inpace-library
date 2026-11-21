# Movie review sentiment: transformer vs bag of words

A transformer encoder written from scratch in PyTorch (multi-head self-attention, residual connections, layer norm,
learned positions, attention pooling) trained to read IMDB movie reviews, compared honestly with a bag-of-words baseline.

## Results (25,000 test reviews)

| model | parameters | test accuracy |
|---|---|---|
| bag of words (average of word embeddings) | 1.28M | **0.852** |
| transformer, 2 layers, 4 heads, d = 64 | 1.39M | 0.830 |

Trained on 22,500 reviews for 3 epochs on a laptop CPU. The simpler model wins: on this task, which words appear
matters far more than their order, and a transformer needs much more data (or pre-training) to pay off.

## Run it

```bash
pip install -r requirements.txt
python train.py      # about 10 minutes on a laptop CPU, under a minute on a GPU
python evaluate.py   # test both, and show which words the attention pooling used
```

## What I learned

- How self-attention works in code: queries, keys and values, scaled dot products, masking the padding.
- A strong baseline is essential: without it, 0.83 would have looked like a success.
- Attention weights hint at what the model uses, but they are not a full explanation.

Based on chapter 12 of *Deep Learning: Foundations and Concepts* (Bishop & Bishop, 2024).
