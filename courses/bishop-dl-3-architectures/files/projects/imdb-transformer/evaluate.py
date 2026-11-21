"""Test both models once, then look at which words the transformer's attention pooling relied on."""
import torch
from data import load_splits
from model import SentimentTransformer, BagOfWords

vocab, _, _, (xte, yte) = load_splits()
saved = torch.load("models.pt")
bow, tf = BagOfWords(len(vocab.itos)), SentimentTransformer(len(vocab.itos))
bow.load_state_dict(saved["bow"]); tf.load_state_dict(saved["tf"])
bow.eval(); tf.eval()

with torch.no_grad():
    for name, m in [("bag of words", bow), ("transformer", tf)]:
        guess = torch.cat([m(xte[i:i + 500]).argmax(1) for i in range(0, len(xte), 500)])
        print(f"TEST accuracy, {name}: {(guess == yte).float().mean():.3f} on {len(yte):,} reviews")

    # Short test reviews are easiest to read: two negative and two positive ones,
    # with the 4 words that got the largest attention-pooling weight in [brackets]
    lengths = (xte > 0).sum(1)
    short = lambda label: torch.nonzero((lengths < 45) & (yte == label)).flatten()[:2].tolist()
    for i in short(0) + short(1):
        logits, w = tf(xte[i:i + 1], return_weights=True)
        n = lengths[i].item()
        top = w[0, :n].topk(4).indices.sort().values
        p = logits.softmax(-1)[0, 1].item()
        print(f"\n{'positive' if yte[i] else 'negative'} review, model says p(positive) = {p:.2f}")
        print("  " + " ".join(f"[{vocab.itos[t]}]" if k in top else vocab.itos[t] for k, t in enumerate(xte[i, :n].tolist())))
