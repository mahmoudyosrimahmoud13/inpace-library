"""How many bits does one character of Shakespeare really need? (Bishop, section 2.5)"""
import torch
from data import load_splits

train, test = load_splits()
chars = sorted(set(train) | set(test))
index = {c: i for i, c in enumerate(chars)}
encode = lambda s: torch.tensor([index[c] for c in s])
x_train, x_test = encode(train), encode(test)
V = len(chars)


def entropy_bits(p):
    p = p[p > 0]
    return -(p * torch.log2(p)).sum().item()


# 1. Unigram model: every character drawn independently from p(c)
counts = torch.bincount(x_train, minlength=V).float() + 1            # +1: no character is impossible
p = counts / counts.sum()
print(f"{'uniform over ' + str(V) + ' characters':34s} {torch.log2(torch.tensor(float(V))):.3f} bits/char")
print(f"{'entropy of the unigram model':34s} {entropy_bits(p):.3f} bits/char")

# Cross-entropy: the average number of bits the TRAINING model needs for the TEST text
cross_uni = -torch.log2(p[x_test]).mean().item()
print(f"{'unigram cross-entropy on test':34s} {cross_uni:.3f} bits/char")

# KL divergence between the test text's own distribution and the model: the bits wasted by using the wrong one
q = torch.bincount(x_test, minlength=V).float() / len(x_test)
kl = (q[q > 0] * torch.log2(q[q > 0] / p[q > 0])).sum().item()
print(f"{'KL(test || train model)':34s} {kl:.3f} bits/char   (= cross-entropy - entropy of test text {cross_uni - entropy_bits(q):.3f})")

# 2. Bigram model: p(next char | previous char). Conditional entropy H[next | previous] (section 2.5.6)
pair = torch.zeros(V, V)
pair.index_put_((x_train[:-1], x_train[1:]), torch.ones(len(x_train) - 1), accumulate=True)
pair += 0.1                                                         # a small pseudo-count
cond = pair / pair.sum(1, keepdim=True)
cross_bi = -torch.log2(cond[x_test[:-1], x_test[1:]]).mean().item()
print(f"{'bigram cross-entropy on test':34s} {cross_bi:.3f} bits/char")

# 3. Trigram model: p(next | two previous characters)
tri = torch.zeros(V * V, V)
tri.index_put_((x_train[:-2] * V + x_train[1:-1], x_train[2:]), torch.ones(len(x_train) - 2), accumulate=True)
tri += 0.01
cond3 = tri / tri.sum(1, keepdim=True)
cross_tri = -torch.log2(cond3[x_test[:-2] * V + x_test[1:-1], x_test[2:]]).mean().item()
print(f"{'trigram cross-entropy on test':34s} {cross_tri:.3f} bits/char")
