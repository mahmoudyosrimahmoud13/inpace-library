"""Test the trained network once: overall, per class, and its most common confusions."""
import torch
from data import load, normalize, CLASSES
from model import SmallCNN

saved = torch.load("cnn.pt")
model = SmallCNN(saved["width"]); model.load_state_dict(saved["state"]); model.eval()
X, y = load("test")
with torch.no_grad():
    guess = torch.cat([model(normalize(X[i:i + 1000])).argmax(1) for i in range(0, len(X), 1000)])
print(f"TEST accuracy: {(guess == y).float().mean():.3f} on {len(y):,} photos (random guessing: 0.100)\n")
confusion = torch.zeros(10, 10, dtype=torch.long)
confusion.index_put_((y, guess), torch.ones_like(y), accumulate=True)
acc = confusion.diag().float() / confusion.sum(1)
for k in acc.argsort():
    worst = confusion[k].clone(); worst[k] = 0
    print(f"{CLASSES[k]:9s} {acc[k]:.2f}   most often mistaken for {CLASSES[worst.argmax()]} ({worst.max().item()} times)")
