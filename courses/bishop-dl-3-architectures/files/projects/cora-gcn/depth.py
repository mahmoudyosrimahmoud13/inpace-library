"""More layers = information from further away. Is deeper better? Watch over-smoothing (section 13.3.4)."""
import torch
import torch.nn.functional as F
from models import DeepGCN
from train import fit, acc, X, y, A_hat, test, topics

print(f"{'layers':>6s} {'validation':>10s} {'test':>6s} {'how alike papers look':>22s}")
for layers in [2, 3, 4, 6, 8]:
    model, v = fit(DeepGCN(X.shape[1], len(topics), layers))
    model.eval()
    with torch.no_grad():
        out, hidden = model(X, A_hat, return_hidden=True)
        h = F.normalize(hidden, dim=1)
        sample = h[torch.randperm(len(h), generator=torch.Generator().manual_seed(0))[:500]]
        alike = (sample @ sample.T).mean().item()               # average cosine similarity between papers
    print(f"{layers:6d} {v:10.3f} {acc(out, test):6.3f} {alike:22.2f}")
