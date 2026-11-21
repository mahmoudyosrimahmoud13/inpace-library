"""Two MCMC samplers (Bishop, sections 14.2.1 and 14.3)."""
import torch
from model import log_posterior, grad_log_posterior


def metropolis(w0, steps, step_size, seed=0):
    """Random-walk Metropolis: propose a random jump, accept it with probability min(1, p(new)/p(old))."""
    g = torch.Generator().manual_seed(seed)
    w, lp, samples, accepted = w0.clone(), log_posterior(w0), [], 0
    for _ in range(steps):
        proposal = w + step_size * torch.randn(w.shape, generator=g, dtype=w.dtype)
        lp_new = log_posterior(proposal)
        if torch.rand(1, generator=g, dtype=w.dtype).log() < lp_new - lp:
            w, lp, accepted = proposal, lp_new, accepted + 1
        samples.append(w.clone())
    return torch.stack(samples), accepted / steps


def mala(w0, steps, step_size, seed=0):
    """Langevin: move along the gradient of log p, plus noise (section 14.3), then a Metropolis-Hastings
    correction so the samples are exact (the 'Metropolis-adjusted Langevin algorithm')."""
    g = torch.Generator().manual_seed(seed)
    eps = step_size

    def log_q(to, frm, grad_frm):                                   # proposal density q(to | frm)
        return -((to - frm - 0.5 * eps ** 2 * grad_frm) ** 2).sum() / (2 * eps ** 2)

    w, lp, grad = w0.clone(), log_posterior(w0), grad_log_posterior(w0)
    samples, accepted = [], 0
    for _ in range(steps):
        proposal = w + 0.5 * eps ** 2 * grad + eps * torch.randn(w.shape, generator=g, dtype=w.dtype)
        lp_new, grad_new = log_posterior(proposal), grad_log_posterior(proposal)
        log_ratio = lp_new - lp + log_q(w, proposal, grad_new) - log_q(proposal, w, grad)
        if torch.rand(1, generator=g, dtype=w.dtype).log() < log_ratio:
            w, lp, grad, accepted = proposal, lp_new, grad_new, accepted + 1
        samples.append(w.clone())
    return torch.stack(samples), accepted / steps
