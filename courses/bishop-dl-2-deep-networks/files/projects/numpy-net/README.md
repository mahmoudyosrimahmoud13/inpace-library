# numpy-net

A small neural network library in plain NumPy, with backpropagation written by hand: linear layers, ReLU and tanh,
softmax cross-entropy, and SGD with momentum. Gradients are verified against finite differences and PyTorch autograd,
and a network trained with it reaches 97.2% on MNIST.

## Results

| check | result |
|---|---|
| gradients vs finite differences (float64) | worst relative error 7e-6 |
| gradients vs PyTorch autograd | largest difference 2e-8 |
| same check with a planted bug in tanh's derivative | error ~1 (caught) |
| MNIST test accuracy, 784-128-64-10, 5 epochs | **97.19%** |
| same network and settings in PyTorch | 97.29% |

## Run it

```bash
pip install -r requirements.txt
python check_gradients.py          # verify every gradient
python check_gradients.py --bug    # watch the check catch a mistake
python train.py                    # train on MNIST (about 10 seconds)
python torch_version.py            # the same in PyTorch
```

## What I learned

- Backpropagation is two rules: a weight's gradient is (input) x (delta), and deltas flow back through the same weights
  multiplied by the activation's derivative.
- Hand-written gradients must be tested: a one-character bug still trains, just worse, and only a gradient check shows it.
- A framework like PyTorch does exactly this, automatically, for any network.

Based on section 8.1 of *Deep Learning: Foundations and Concepts* (Bishop & Bishop, 2024).
