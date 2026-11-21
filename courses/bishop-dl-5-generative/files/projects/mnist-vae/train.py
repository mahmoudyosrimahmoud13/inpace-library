"""Train a VAE on MNIST. Example: python train.py --latent 2"""
import argparse
import torch
from data import load
from vae import VAE

ap = argparse.ArgumentParser()
ap.add_argument("--latent", type=int, default=2)
ap.add_argument("--epochs", type=int, default=10)
args = ap.parse_args()
torch.manual_seed(0)
x, _ = load("train")
x_test, _ = load("test")
model = VAE(args.latent)
opt = torch.optim.Adam(model.parameters(), lr=1e-3)


@torch.no_grad()
def test_scores():
    torch.manual_seed(1)
    elbo, recon, kl = model.elbo(x_test)
    return elbo.mean().item(), recon.mean().item(), kl.mean().item()


for epoch in range(1, args.epochs + 1):
    order = torch.randperm(len(x))
    for s in range(0, len(x), 128):
        loss = -model.elbo(x[order[s:s + 128]])[0].mean()
        opt.zero_grad(); loss.backward(); opt.step()
    if epoch in (1, 2, 5, args.epochs):
        elbo, recon, kl = test_scores()
        print(f"epoch {epoch:2d}: test ELBO {elbo:7.1f} nats per image  (reconstruction {recon:7.1f}, KL {kl:5.1f})")
torch.save(model.state_dict(), f"vae_latent{args.latent}.pt")
