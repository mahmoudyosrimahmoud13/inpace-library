# SMS spam filter

A Naive Bayes spam filter written from scratch in PyTorch: Bayes' theorem, word counts and nothing else.
Trained and tested on the SMS Spam Collection (5,574 real text messages, 13% spam).

## Results (test set, 1,116 messages, used once)

| filter | accuracy | spam caught | real messages lost |
|---|---|---|---|
| call everything real | 0.859 | 0 / 157 | 0 / 959 |
| Naive Bayes, threshold 0.5 | 0.984 | 147 / 157 | 8 / 959 |
| Naive Bayes, threshold 0.9 (chosen on validation) | 0.988 | 146 / 157 | 2 / 959 |

Raising the threshold cut lost real messages from 8 to 2 at the cost of 1 spam.

Most spam-like words: claim, 150p, tone, prize, won, www, guaranteed, awarded.

## Run it

```bash
pip install -r requirements.txt
python train.py               # validation results
python train.py --alpha 0     # see why plain maximum likelihood fails
python evaluate.py            # choose the threshold, then test once
python explain.py "Your text here"
```

## What I learned

- A classifier can be built directly from Bayes' theorem: prior times likelihood, normalized.
- Maximum likelihood gives probability zero to any word never seen in a class, and one such word then decides everything.
  Adding a pseudo-count (alpha = 1) fixes it.
- Accuracy alone hides what matters: the threshold should reflect that losing a real message costs more than missing a spam.

Based on chapter 2 of *Deep Learning: Foundations and Concepts* (Bishop & Bishop, 2024).
