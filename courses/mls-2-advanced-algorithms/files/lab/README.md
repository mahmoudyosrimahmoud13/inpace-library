# Digit reader

The running project of the inPace course "Machine Learning refresh 2": a network that reads handwritten digits (scikit-learn's copy of the UCI digits), built, trained, diagnosed and compared with trees.

```bash
pip install tensorflow scikit-learn scipy numpy
python p1_forward.py
```

| File | What it adds |
|---|---|
| `digits.py` | The data, split once into training, validation and test |
| `p1_forward.py` | Layers and forward propagation, yours against Keras |
| `p2_backprop.py` | Backpropagation by hand, a gradient check |
| `p3_train_activations.py` | Training, and the hidden activation |
| `p4_softmax_adam.py` | Safe softmax, SGD against Adam |
| `p5_bias_variance.py` | Learning curves and regularization |
| `p6_error_analysis.py` | Error analysis and augmentation |
| `p7_skewed.py` | A rare class: precision, recall and the threshold |
| `p8_trees.py` | Information gain, trees, forests and boosting |
