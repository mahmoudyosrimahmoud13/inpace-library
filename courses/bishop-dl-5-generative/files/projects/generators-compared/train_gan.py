"""The GAN from the clothes project, trained on MNIST digits instead (same networks, same settings)."""
import torch
import torch.nn.functional as F
from data import load
from gan import generator, discriminator, Z

torch.manual_seed(0)
x, _ = load("train")
x = x * 2 - 1
G, D = generator(), discriminator()
opt_g = torch.optim.Adam(G.parameters(), lr=2e-4, betas=(0.5, 0.999))
opt_d = torch.optim.Adam(D.parameters(), lr=2e-4, betas=(0.5, 0.999))
for epoch in range(1, 16):
    order = torch.randperm(len(x))
    for s in range(0, len(x) - 127, 128):
        real, fake = x[order[s:s + 128]], G(torch.randn(128, Z))
        d_loss = F.binary_cross_entropy_with_logits(D(real), torch.ones(128, 1)) + \
                 F.binary_cross_entropy_with_logits(D(fake.detach()), torch.zeros(128, 1))
        opt_d.zero_grad(); d_loss.backward(); opt_d.step()
        g_loss = F.binary_cross_entropy_with_logits(D(fake), torch.ones(128, 1))
        opt_g.zero_grad(); g_loss.backward(); opt_g.step()
    if epoch in (1, 5, 10, 15):
        print(f"epoch {epoch:2d}: losses D {d_loss.item():.2f}, G {g_loss.item():.2f}")
torch.save(G.state_dict(), "gan_digits.pt")
