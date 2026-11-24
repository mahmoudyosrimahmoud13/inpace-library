"""Project 1 (days 1-2): neurons and a layer, by hand and in TensorFlow. The Digit reader starts by computing a
network's output, before it learns anything."""
import numpy as np
import tensorflow as tf

from digits import X_train, show, y_train

tf.random.set_seed(0)


def dense(a_in, W, b, g):
    """One layer: each unit computes g(w . a + b). W has one column per unit."""
    return g(a_in @ W + b)


def sigmoid(z):
    return 1 / (1 + np.exp(-z))


if __name__ == "__main__":
    print(f"1. {len(X_train)} training digits, 64 pixels each. The first one, a {y_train[0]}:")
    print(show(X_train[0]))
    model = tf.keras.Sequential([tf.keras.Input((64,)), tf.keras.layers.Dense(25, activation="sigmoid"),
                                 tf.keras.layers.Dense(15, activation="sigmoid"),
                                 tf.keras.layers.Dense(1, activation="sigmoid")])
    print(f"\n2. A 64 -> 25 -> 15 -> 1 network: {model.count_params():,} parameters")
    for layer in model.layers:
        W, b = layer.get_weights()
        print(f"   {layer.name:8} W {str(W.shape):9} b {str(b.shape):6}")
    a = X_train[:5]
    for layer in model.layers:                       # forward propagation with your own dense(), Keras's weights
        W, b = layer.get_weights()
        a = dense(a, W, b, sigmoid)
    keras_out = model(X_train[:5]).numpy()
    print(f"\n3. Your forward pass:  {np.round(a.ravel(), 4)}")
    print(f"   Keras's:            {np.round(keras_out.ravel(), 4)}")
    print(f"   identical: {np.allclose(a, keras_out, atol=1e-6)}. Untrained, so every digit gets about the same output.")
