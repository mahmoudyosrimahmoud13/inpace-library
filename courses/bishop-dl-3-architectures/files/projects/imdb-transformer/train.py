"""Train the bag-of-words baseline and the transformer, and compare them on the validation reviews."""
import torch
import torch.nn.functional as F
from data import load_splits
from model import SentimentTransformer, BagOfWords

vocab, (xtr, ytr), (xva, yva), _ = load_splits()


def accuracy(model, x, y):
    model.eval()
    with torch.no_grad():
        return torch.cat([model(x[i:i + 500]).argmax(1) for i in range(0, len(x), 500)]).eq(y).float().mean().item()


def fit(model, epochs, lr):
    torch.manual_seed(0)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    steps = epochs * (len(xtr) // 64)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=lr, total_steps=steps)
    for epoch in range(1, epochs + 1):
        model.train()
        order = torch.randperm(len(xtr))
        for s in range(0, len(xtr) - 63, 64):
            idx = order[s:s + 64]
            loss = F.cross_entropy(model(xtr[idx]), ytr[idx])
            opt.zero_grad(); loss.backward(); opt.step(); sched.step()
        print(f"  epoch {epoch}: validation accuracy {accuracy(model, xva, yva):.3f}")
    return model


print("bag of words (order ignored):")
torch.manual_seed(0)
bow = fit(BagOfWords(len(vocab.itos)), epochs=3, lr=3e-3)
print("transformer (2 layers, 4 heads, d = 64):")
torch.manual_seed(0)
tf = fit(SentimentTransformer(len(vocab.itos)), epochs=3, lr=1e-3)
print(f"parameters: bag of words {sum(p.numel() for p in bow.parameters()):,}, "
      f"transformer {sum(p.numel() for p in tf.parameters()):,}")
torch.save({"bow": bow.state_dict(), "tf": tf.state_dict()}, "models.pt")
