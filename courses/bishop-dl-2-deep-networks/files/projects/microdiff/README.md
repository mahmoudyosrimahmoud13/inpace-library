# microdiff

A small automatic-differentiation engine in pure Python, with both modes of section 8.2: reverse mode (a computation
graph with `backward()`, like PyTorch) and forward mode (dual numbers). It draws its own computation graphs as Mermaid
diagrams, and trains a small neural network.

![moons](outputs/moons.png)

## Results

| check | result |
|---|---|
| book example f = x1 x2 + exp(x1 x2) - sin(x2): reverse mode, forward mode, PyTorch | identical to 6 decimals |
| gradients of a 105-parameter network vs PyTorch (float64) | largest difference 6e-16 |
| two-moons classification, 2-8-8-1 tanh network, 150 steps | 100% training accuracy |

## The computation graph of the example

```mermaid
flowchart LR
    n0["x1<br/>value 2<br/>grad 1.86"]
    n1["x2<br/>value 0.5<br/>grad 6.56"]
    n2["*<br/>value 1<br/>grad 3.72"]
    n0 --> n2
    n1 --> n2
    n3["exp<br/>value 2.72<br/>grad 1"]
    n2 --> n3
    n4["+<br/>value 3.72<br/>grad 1"]
    n2 --> n4
    n3 --> n4
    n5["sin<br/>value 0.479<br/>grad -1"]
    n1 --> n5
    n6["const<br/>value -1<br/>grad 0.479"]
    n7["*<br/>value -0.479<br/>grad 1"]
    n5 --> n7
    n6 --> n7
    n8["+<br/>value 3.24<br/>grad 1"]
    n4 --> n8
    n7 --> n8
```

## Run it

```bash
pip install -r requirements.txt
python demo.py     # the book's example, three ways, and its graph
python train.py    # a neural network made of Value objects (about 30 seconds)
```

## What I learned

- Reverse mode gets all the derivatives of one output in a single backward pass, which is why it trains networks;
  forward mode needs one pass per input.
- Each operation only needs to know its own local derivative; the chain rule does the rest.
- Working one number at a time is very slow in Python. Real frameworks apply the same idea to whole tensors.

Based on section 8.2 of *Deep Learning: Foundations and Concepts* (Bishop & Bishop, 2024).
