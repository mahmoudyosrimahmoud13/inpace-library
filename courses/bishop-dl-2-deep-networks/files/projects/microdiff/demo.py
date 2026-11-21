"""A small function, differentiated three ways: reverse mode, forward mode, and PyTorch."""
import torch
from engine import Value, Dual


def f(x1, x2):
    """The example of section 8.2.1 (equation 8.49): f = x1 x2 + exp(x1 x2) - sin(x2)."""
    v = x1 * x2
    return v + v.exp() - x2.sin()


x1, x2 = Value(2.0, name="x1"), Value(0.5, name="x2")
y = f(x1, x2)
y.backward()
print(f"reverse mode:  f = {y.data:.6f}, df/dx1 = {x1.grad:.6f}, df/dx2 = {x2.grad:.6f}  (one backward pass)")

d1 = f(Dual(2.0, 1.0), Dual(0.5, 0.0)).deriv                 # seed x1: one pass per input
d2 = f(Dual(2.0, 0.0), Dual(0.5, 1.0)).deriv
print(f"forward mode:                    df/dx1 = {d1:.6f}, df/dx2 = {d2:.6f}  (two forward passes)")

t1, t2 = torch.tensor(2.0, requires_grad=True), torch.tensor(0.5, requires_grad=True)
v = t1 * t2
(v + v.exp() - t2.sin()).backward()
print(f"PyTorch:                         df/dx1 = {t1.grad:.6f}, df/dx2 = {t2.grad:.6f}")
print()
print(y.to_mermaid())
