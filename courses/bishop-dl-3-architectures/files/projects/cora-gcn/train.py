"""Compare words-only, graph-only and words + graph, with just 140 labelled papers."""
import torch
import torch.nn.functional as F
from data import load, split
from models import MLP, GCN, normalized_adjacency, label_propagation

X, y, A, topics = load()
train, val, test = split(y)
A_hat = normalized_adjacency(A).to_sparse()               # 2,708 x 2,708 but only 0.2% non-zero
acc = lambda logits, idx: (logits[idx].argmax(1) == y[idx]).float().mean().item()


def fit(model, epochs=200):
    torch.manual_seed(0)
    opt = torch.optim.Adam(model.parameters(), lr=0.01, weight_decay=5e-4)
    best_val, best_state = 0.0, None
    for epoch in range(epochs):
        model.train()
        loss = F.cross_entropy(model(X, A_hat)[train], y[train])
        opt.zero_grad(); loss.backward(); opt.step()
        model.eval()
        with torch.no_grad():
            v = acc(model(X, A_hat), val)
        if v > best_val:
            best_val, best_state = v, {k: t.clone() for k, t in model.state_dict().items()}
    model.load_state_dict(best_state)                         # early stopping on validation accuracy
    return model, best_val


if __name__ == "__main__":
    print(f"labelled papers: {len(train)} of {len(y)}\n")
    print(f"{'method':32s} {'validation':>10s} {'test':>6s}")
    with torch.no_grad():
        lp = label_propagation(A_hat, y, train, len(topics))
    print(f"{'label propagation (graph only)':32s} {acc(lp, val):10.3f} {acc(lp, test):6.3f}")
    for name, model in [("MLP (words only)", MLP(X.shape[1], len(topics))),
                        ("GCN (words + graph)", GCN(X.shape[1], len(topics)))]:
        model, v = fit(model)
        model.eval()
        with torch.no_grad():
            t = acc(model(X, A_hat), test)
        print(f"{name:32s} {v:10.3f} {t:6.3f}")
        if name.startswith("GCN"):
            torch.save(model.state_dict(), "gcn.pt")
