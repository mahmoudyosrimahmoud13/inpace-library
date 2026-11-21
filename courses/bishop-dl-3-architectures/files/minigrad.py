"""minigrad: a small automatic-differentiation library in NumPy, built in the Bishop deep learning courses.

A Tensor holds a NumPy array (.data) and, after backward(), the gradient of a scalar loss with respect to it (.grad).
Every operation records how to send gradients back to its inputs (reverse-mode automatic differentiation, Bishop 8.2).

    from minigrad import Tensor
    x = Tensor([[1.0, 2.0]], requires_grad=True)
    y = (x * x).sum()
    y.backward()
    print(x.grad)        # [[2. 4.]]
"""
from __future__ import annotations

import numpy as np


def _unbroadcast(grad, shape):
    """Sum a gradient back down to `shape` (undo NumPy broadcasting)."""
    while grad.ndim > len(shape):
        grad = grad.sum(axis=0)
    for i, n in enumerate(shape):
        if n == 1 and grad.shape[i] != 1:
            grad = grad.sum(axis=i, keepdims=True)
    return grad


class Tensor:
    def __init__(self, data, requires_grad=False, _parents=(), _back=None):
        self.data = np.asarray(data, dtype=np.float64)
        self.requires_grad = requires_grad
        self.grad = None
        self._parents = _parents
        self._back = _back          # function: gradient of the output -> adds into parents' .grad

    # ---- basics -------------------------------------------------------------------------------------------
    shape = property(lambda self: self.data.shape)
    T = property(lambda self: self.transpose())

    def __repr__(self):
        return f"Tensor({np.array2string(self.data, precision=4)})"

    def _make(self, data, parents, back):
        need = any(p.requires_grad for p in parents)
        return Tensor(data, need, parents if need else (), back if need else None)

    @staticmethod
    def lift(x):
        return x if isinstance(x, Tensor) else Tensor(x)

    def _add_grad(self, g):
        if self.requires_grad:
            self.grad = g if self.grad is None else self.grad + g

    # ---- arithmetic ---------------------------------------------------------------------------------------
    def __add__(self, other):
        other = Tensor.lift(other)
        def back(g):
            self._add_grad(_unbroadcast(g, self.shape)); other._add_grad(_unbroadcast(g, other.shape))
        return self._make(self.data + other.data, (self, other), back)

    def __mul__(self, other):
        other = Tensor.lift(other)
        def back(g):
            self._add_grad(_unbroadcast(g * other.data, self.shape))
            other._add_grad(_unbroadcast(g * self.data, other.shape))
        return self._make(self.data * other.data, (self, other), back)

    def __neg__(self):
        return self * -1.0

    def __sub__(self, other):
        return self + (-Tensor.lift(other))

    def __rsub__(self, other):
        return Tensor.lift(other) - self

    def __truediv__(self, other):
        return self * Tensor.lift(other) ** -1.0

    def __rtruediv__(self, other):
        return Tensor.lift(other) * self ** -1.0

    __radd__ = __add__
    __rmul__ = __mul__

    def __pow__(self, k: float):
        def back(g):
            self._add_grad(g * k * self.data ** (k - 1))
        return self._make(self.data ** k, (self,), back)

    def __matmul__(self, other):
        other = Tensor.lift(other)
        def back(g):
            a, b = self.data, other.data
            ga = g @ np.swapaxes(b, -1, -2)
            gb = np.swapaxes(a, -1, -2) @ g
            self._add_grad(_unbroadcast(ga, a.shape)); other._add_grad(_unbroadcast(gb, b.shape))
        return self._make(self.data @ other.data, (self, other), back)

    # ---- elementwise functions ----------------------------------------------------------------------------
    def exp(self):
        out = np.exp(self.data)
        return self._make(out, (self,), lambda g: self._add_grad(g * out))

    def log(self):
        return self._make(np.log(self.data), (self,), lambda g: self._add_grad(g / self.data))

    def tanh(self):
        out = np.tanh(self.data)
        return self._make(out, (self,), lambda g: self._add_grad(g * (1 - out ** 2)))

    def relu(self):
        mask = self.data > 0
        return self._make(self.data * mask, (self,), lambda g: self._add_grad(g * mask))

    def sigmoid(self):
        out = 1 / (1 + np.exp(-self.data))
        return self._make(out, (self,), lambda g: self._add_grad(g * out * (1 - out)))

    # ---- shape and reductions -----------------------------------------------------------------------------
    def sum(self, axis=None, keepdims=False):
        def back(g):
            if axis is not None and not keepdims:
                g = np.expand_dims(g, axis)
            self._add_grad(np.broadcast_to(g, self.shape).copy())
        return self._make(self.data.sum(axis=axis, keepdims=keepdims), (self,), back)

    def mean(self, axis=None, keepdims=False):
        n = self.data.size if axis is None else self.data.shape[axis]
        return self.sum(axis, keepdims) * (1.0 / n)

    def max(self, axis=-1, keepdims=True):
        out = self.data.max(axis=axis, keepdims=True)
        mask = (self.data == out)
        mask = mask / mask.sum(axis=axis, keepdims=True)
        def back(g):
            if not keepdims:
                g = np.expand_dims(g, axis)
            self._add_grad(g * mask)
        return self._make(out if keepdims else out.squeeze(axis), (self,), back)

    def reshape(self, *shape):
        return self._make(self.data.reshape(*shape), (self,), lambda g: self._add_grad(g.reshape(self.shape)))

    def transpose(self, *axes):
        axes = axes or tuple(range(self.data.ndim))[::-1]
        inv = np.argsort(axes)
        return self._make(self.data.transpose(axes), (self,), lambda g: self._add_grad(g.transpose(inv)))

    def __getitem__(self, idx):
        def back(g):
            full = np.zeros_like(self.data)
            np.add.at(full, idx, g)
            self._add_grad(full)
        return self._make(self.data[idx], (self,), back)

    # ---- the backward pass (Bishop 8.2: reverse-mode automatic differentiation) ----------------------------
    def backward(self, grad=None):
        order, seen = [], set()
        def visit(t):
            if id(t) not in seen:
                seen.add(id(t))
                for p in t._parents:
                    visit(p)
                order.append(t)
        visit(self)
        self.grad = np.ones_like(self.data) if grad is None else np.asarray(grad, dtype=np.float64)
        for t in reversed(order):
            if t._back is not None and t.grad is not None:
                t._back(t.grad)


# ---- functions built from the pieces above ----------------------------------------------------------------
def concat(tensors, axis=-1):
    data = np.concatenate([t.data for t in tensors], axis=axis)
    sizes = np.cumsum([t.shape[axis] for t in tensors])[:-1]
    def back(g):
        for t, part in zip(tensors, np.split(g, sizes, axis=axis)):
            t._add_grad(part)
    return tensors[0]._make(data, tuple(tensors), back)


def log_softmax(x: Tensor, axis=-1) -> Tensor:
    shifted = x - Tensor(x.data.max(axis=axis, keepdims=True))     # a constant shift, for numerical safety
    return shifted - shifted.exp().sum(axis=axis, keepdims=True).log()


def softmax(x: Tensor, axis=-1) -> Tensor:
    return log_softmax(x, axis).exp()


def cross_entropy(logits: Tensor, labels) -> Tensor:
    """Mean negative log-probability of the right class (Bishop 5.4.4, 6.4.3). labels: integer array."""
    lp = log_softmax(logits, axis=-1)
    labels = np.asarray(labels)
    return -lp[np.arange(len(labels)), labels].mean()


def mse(pred: Tensor, target) -> Tensor:
    return ((pred - Tensor.lift(target)) ** 2).mean()


# ---- layers --------------------------------------------------------------------------------------------------
class Module:
    def parameters(self):
        out = []
        for v in vars(self).values():
            if isinstance(v, Tensor) and v.requires_grad:
                out.append(v)
            elif isinstance(v, Module):
                out += v.parameters()
            elif isinstance(v, (list, tuple)):
                for item in v:
                    if isinstance(item, Module):
                        out += item.parameters()
        return out

    def __call__(self, *args):
        return self.forward(*args)


class Linear(Module):
    def __init__(self, n_in, n_out, rng, bias=True):
        self.W = Tensor(rng.normal(0, np.sqrt(2.0 / n_in), (n_in, n_out)), requires_grad=True)   # He initialization
        self.b = Tensor(np.zeros(n_out), requires_grad=True) if bias else None

    def forward(self, x):
        y = x @ self.W
        return y + self.b if self.b is not None else y


class MLP(Module):
    def __init__(self, sizes, rng):
        self.layers = [Linear(a, b, rng) for a, b in zip(sizes[:-1], sizes[1:])]

    def forward(self, x):
        for layer in self.layers[:-1]:
            x = layer(x).relu()
        return self.layers[-1](x)


# ---- optimizers (Bishop 7.2, 7.3) ---------------------------------------------------------------------------
class SGD:
    def __init__(self, params, lr=0.1, momentum=0.0, weight_decay=0.0):
        self.params, self.lr, self.mu, self.wd = params, lr, momentum, weight_decay
        self.v = [np.zeros_like(p.data) for p in params]

    def step(self):
        for p, v in zip(self.params, self.v):
            g = p.grad + self.wd * p.data
            v *= self.mu
            v -= self.lr * g
            p.data += v

    def zero_grad(self):
        for p in self.params:
            p.grad = None


class Adam:
    def __init__(self, params, lr=1e-3, betas=(0.9, 0.999), eps=1e-8, weight_decay=0.0):
        self.params, self.lr, (self.b1, self.b2), self.eps, self.wd = params, lr, betas, eps, weight_decay
        self.m = [np.zeros_like(p.data) for p in params]
        self.s = [np.zeros_like(p.data) for p in params]
        self.t = 0

    def step(self):
        self.t += 1
        for p, m, s in zip(self.params, self.m, self.s):
            g = p.grad
            m *= self.b1; m += (1 - self.b1) * g
            s *= self.b2; s += (1 - self.b2) * g * g
            mhat = m / (1 - self.b1 ** self.t)
            shat = s / (1 - self.b2 ** self.t)
            p.data -= self.lr * (mhat / (np.sqrt(shat) + self.eps) + self.wd * p.data)   # decoupled weight decay

    def zero_grad(self):
        for p in self.params:
            p.grad = None


# ---- added in part 3: convolution (Bishop 10.2) ------------------------------------------------------------------
def conv2d(x: Tensor, W: Tensor, b: Tensor = None, padding=0) -> Tensor:
    """x: (N, C, H, W) images, W: (F, C, k, k) filters, b: (F,). Stride 1. Returns (N, F, H', W')."""
    xp = np.pad(x.data, ((0, 0), (0, 0), (padding, padding), (padding, padding)))
    F, C, k, _ = W.shape
    patches = np.lib.stride_tricks.sliding_window_view(xp, (k, k), axis=(2, 3))   # (N, C, H', W', k, k)
    N, _, Ho, Wo = patches.shape[:4]
    cols = patches.transpose(0, 2, 3, 1, 4, 5).reshape(N * Ho * Wo, C * k * k)      # one row per output position
    out = cols @ W.data.reshape(F, -1).T                                            # (N*H'*W', F)
    if b is not None:
        out = out + b.data
    out = out.reshape(N, Ho, Wo, F).transpose(0, 3, 1, 2)

    def back(g):                                                                    # g: (N, F, H', W')
        g2 = g.transpose(0, 2, 3, 1).reshape(-1, F)
        W._add_grad((g2.T @ cols).reshape(W.shape))
        if b is not None:
            b._add_grad(g2.sum(0))
        if x.requires_grad:
            dcols = (g2 @ W.data.reshape(F, -1)).reshape(N, Ho, Wo, C, k, k)
            dxp = np.zeros_like(xp)
            for i in range(k):                                                     # send each patch's gradient back
                for j in range(k):                                                 # to the pixels it was cut from
                    dxp[:, :, i:i + Ho, j:j + Wo] += dcols[:, :, :, :, i, j].transpose(0, 3, 1, 2)
            x._add_grad(dxp[:, :, padding:padding + x.shape[2], padding:padding + x.shape[3]])
    parents = (x, W) if b is None else (x, W, b)
    return x._make(out, parents, back)


class Conv2d(Module):
    def __init__(self, c_in, c_out, k, rng, padding=0):
        self.W = Tensor(rng.normal(0, np.sqrt(2.0 / (c_in * k * k)), (c_out, c_in, k, k)), requires_grad=True)
        self.b = Tensor(np.zeros(c_out), requires_grad=True)
        self.padding = padding

    def forward(self, x):
        return conv2d(x, self.W, self.b, self.padding)


def max_pool2(x: Tensor) -> Tensor:
    """2 × 2 max pooling with stride 2 on (N, C, H, W), H and W even."""
    N, C, H, W = x.shape
    return x.reshape(N, C, H // 2, 2, W // 2, 2).max(axis=5, keepdims=False).max(axis=3, keepdims=False)
