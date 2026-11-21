"""A variational autoencoder (Bishop, section 19.2)."""
import torch
import torch.nn.functional as F
from torch import nn


class VAE(nn.Module):
    def __init__(self, latent=2, hidden=400):
        super().__init__()
        self.latent = latent
        self.encoder = nn.Sequential(nn.Linear(784, hidden), nn.ReLU(), nn.Linear(hidden, 2 * latent))
        self.decoder = nn.Sequential(nn.Linear(latent, hidden), nn.ReLU(), nn.Linear(hidden, 784))

    def encode(self, x):
        """The encoder gives, for each image, a Gaussian q(z | x): a mean and a log-variance per latent dimension
        (amortized inference, section 19.2.1)."""
        mu, log_var = self.encoder(x).chunk(2, 1)
        return mu, log_var

    def decode(self, z):
        """The decoder gives, for each latent point, the probability of each pixel being 'on' (as logits)."""
        return self.decoder(z)

    def elbo(self, x):
        """Evidence lower bound per image (equation 19.14): reconstruction log-likelihood minus KL(q(z|x) || p(z))."""
        mu, log_var = self.encode(x)
        z = mu + torch.exp(0.5 * log_var) * torch.randn_like(mu)          # reparameterization trick (19.18)
        recon = -F.binary_cross_entropy_with_logits(self.decode(z), x, reduction="none").sum(1)
        kl = 0.5 * (mu ** 2 + log_var.exp() - 1 - log_var).sum(1)         # closed form for two Gaussians
        return recon - kl, recon, kl
