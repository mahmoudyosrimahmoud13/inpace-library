"""Train the spam filter and measure it on the validation set."""
import argparse
import torch
from data import load_splits, Vocabulary
from model import NaiveBayes


def report(name, p_spam, t, threshold=0.5):
    guess = (p_spam > threshold).long()
    tp = ((guess == 1) & (t == 1)).sum().item()
    fp = ((guess == 1) & (t == 0)).sum().item()
    fn = ((guess == 0) & (t == 1)).sum().item()
    acc = (guess == t).float().mean().item()
    undefined = torch.isnan(p_spam).sum().item()
    if undefined:
        print(f"  warning: p(spam) is undefined (nan) for {undefined} of {len(t)} messages")
    print(f"{name}: accuracy {acc:.3f} | spam caught {tp}/{tp + fn} | real messages lost {fp}/{(t == 0).sum().item()}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--alpha", type=float, default=1.0)
    args = ap.parse_args()
    (train_x, train_t), (val_x, val_t), _ = load_splits()
    vocab = Vocabulary(train_x)
    X_train, X_val = vocab.counts(train_x), vocab.counts(val_x)

    baseline = torch.zeros_like(val_t)              # "nothing is spam"
    print(f"baseline (call everything real): accuracy {(baseline == val_t).float().mean():.3f}")
    model = NaiveBayes(alpha=args.alpha).fit(X_train, train_t)
    report(f"naive Bayes, alpha={args.alpha:g}", model.prob_spam(X_val), val_t)
