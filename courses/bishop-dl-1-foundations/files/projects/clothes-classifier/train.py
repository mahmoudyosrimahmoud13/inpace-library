"""Fit both classifiers and compare them on the validation set."""
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader, TensorDataset
from data import load_splits
from models import GaussianClassifier, SoftmaxRegression

torch.manual_seed(0)
(xtr, ttr), (xva, tva), _ = load_splits()


def evaluate(logits, t):
    return (logits.argmax(1) == t).float().mean().item(), F.cross_entropy(logits, t).item()


gen = GaussianClassifier().fit(xtr, ttr)
acc, ce = evaluate(gen.logits(xva), tva)
print(f"generative Gaussian classifier: validation accuracy {acc:.3f}, cross-entropy {ce:.3f}")

model = SoftmaxRegression()
opt = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
loader = DataLoader(TensorDataset(xtr, ttr), batch_size=128, shuffle=True)
for epoch in range(1, 16):
    for x, t in loader:
        loss = F.cross_entropy(model(x), t)
        opt.zero_grad(); loss.backward(); opt.step()
    if epoch in (1, 5, 10, 15):
        with torch.no_grad():
            acc, ce = evaluate(model(xva), tva)
        print(f"softmax regression, epoch {epoch:2d}: validation accuracy {acc:.3f}, cross-entropy {ce:.3f}")
torch.save(model.state_dict(), "softmax.pt")
