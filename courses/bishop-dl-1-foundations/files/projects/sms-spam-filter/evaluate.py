"""Choose the decision threshold on the validation set, then measure the final filter ONCE on the test set.

Losing a real message is much worse than letting a spam through, so we demand that at most
1 in 500 real messages is sent to the spam folder, and catch as much spam as possible under that rule.
"""
import torch
from data import load_splits, Vocabulary
from model import NaiveBayes
from train import report

(train_x, train_t), (val_x, val_t), (test_x, test_t) = load_splits()
vocab = Vocabulary(train_x)
model = NaiveBayes(alpha=1.0).fit(vocab.counts(train_x), train_t)

p_val = model.prob_spam(vocab.counts(val_x))
max_lost = (val_t == 0).sum().item() // 500
for threshold in [0.5, 0.9, 0.99, 0.999, 0.9999]:
    lost = ((p_val > threshold) & (val_t == 0)).sum().item()
    caught = ((p_val > threshold) & (val_t == 1)).float().sum() / (val_t == 1).sum()
    print(f"threshold {threshold:<7g}: real messages lost {lost}, spam caught {caught:.1%}")
    if lost <= max_lost:
        break
print(f"\nchosen threshold: {threshold} (at most {max_lost} lost real messages on validation)\n")

report("TEST, threshold 0.5    ", model.prob_spam(vocab.counts(test_x)), test_t)
report(f"TEST, threshold {threshold:<7g}", model.prob_spam(vocab.counts(test_x)), test_t, threshold)
