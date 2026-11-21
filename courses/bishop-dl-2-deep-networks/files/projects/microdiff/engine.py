"""microdiff: automatic differentiation for single numbers (Bishop, section 8.2), in two modes.

Reverse mode (Value): every operation records its inputs and how to send a gradient back to them.
backward() visits the graph from the output to the inputs, once. Cost: one backward pass per OUTPUT.

Forward mode (Dual): every number carries its derivative along with it, computed at the same time as the value.
Cost: one forward pass per INPUT.
"""
import math


class Value:
    def __init__(self, data, parents=(), op="", name=""):
        self.data, self.grad = float(data), 0.0
        self._parents, self._op, self.name = parents, op, name
        self._backward = lambda: None

    def __add__(self, other):
        other = other if isinstance(other, Value) else Value(other)
        out = Value(self.data + other.data, (self, other), "+")
        def _backward():
            self.grad += out.grad                   # d(a+b)/da = 1
            other.grad += out.grad
        out._backward = _backward
        return out

    def __mul__(self, other):
        other = other if isinstance(other, Value) else Value(other)
        out = Value(self.data * other.data, (self, other), "*")
        def _backward():
            self.grad += other.data * out.grad      # d(ab)/da = b
            other.grad += self.data * out.grad
        out._backward = _backward
        return out

    def __pow__(self, k):
        out = Value(self.data ** k, (self,), f"^{k}")
        def _backward():
            self.grad += k * self.data ** (k - 1) * out.grad
        out._backward = _backward
        return out

    def _unary(self, value, derivative, op):
        out = Value(value, (self,), op)
        def _backward():
            self.grad += derivative * out.grad
        out._backward = _backward
        return out

    def exp(self):
        e = math.exp(self.data)
        return self._unary(e, e, "exp")

    def log(self):
        return self._unary(math.log(self.data), 1 / self.data, "log")

    def sin(self):
        return self._unary(math.sin(self.data), math.cos(self.data), "sin")

    def tanh(self):
        t = math.tanh(self.data)
        return self._unary(t, 1 - t * t, "tanh")

    def relu(self):
        return self._unary(max(0.0, self.data), float(self.data > 0), "relu")

    def __neg__(self): return self * -1
    def __sub__(self, other): return self + (-other)
    def __truediv__(self, other): return self * other ** -1
    __radd__, __rmul__ = __add__, __mul__
    def __rsub__(self, other): return Value(other) - self

    def graph(self):
        """All nodes, ordered so that every node comes after its parents (a topological order)."""
        order, seen = [], set()
        def visit(v):
            if id(v) not in seen:
                seen.add(id(v))
                for p in v._parents:
                    visit(p)
                order.append(v)
        visit(self)
        return order

    def backward(self):
        order = self.graph()
        for v in order:
            v.grad = 0.0
        self.grad = 1.0                             # d(output)/d(output)
        for v in reversed(order):                   # outputs first, inputs last
            v._backward()

    def to_mermaid(self):
        """The computation graph as a Mermaid diagram (GitHub draws these in README files)."""
        lines, number = ["flowchart LR"], {}
        for v in self.graph():
            number[id(v)] = len(number)
            label = (v.name or v._op or "const") + f"<br/>value {v.data:.3g}<br/>grad {v.grad:.3g}"
            lines.append(f'    n{number[id(v)]}["{label}"]')
            for p in v._parents:
                lines.append(f"    n{number[id(p)]} --> n{number[id(v)]}")
        return "\n".join(lines)


class Dual:
    """Forward mode: a number a + b*eps with eps^2 = 0. 'b' is the derivative, carried along."""
    def __init__(self, value, deriv=0.0):
        self.value, self.deriv = value, deriv

    def __add__(self, o):
        o = o if isinstance(o, Dual) else Dual(o)
        return Dual(self.value + o.value, self.deriv + o.deriv)

    def __sub__(self, o):
        return self + o * -1

    def __mul__(self, o):
        o = o if isinstance(o, Dual) else Dual(o)
        return Dual(self.value * o.value, self.deriv * o.value + self.value * o.deriv)

    def exp(self):
        e = math.exp(self.value)
        return Dual(e, e * self.deriv)

    def sin(self):
        return Dual(math.sin(self.value), math.cos(self.value) * self.deriv)

    def tanh(self):
        t = math.tanh(self.value)
        return Dual(t, (1 - t * t) * self.deriv)

    __radd__, __rmul__ = __add__, __mul__
