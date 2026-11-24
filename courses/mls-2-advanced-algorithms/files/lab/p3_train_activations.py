"""Project 3 (day 4): train the network with TensorFlow, and see what the hidden activation changes. Task: all ten
digits; the output layer is softmax (tomorrow's lesson), so today's question is only the hidden layers."""
import numpy as np
import tensorflow as tf

from digits import X_train, X_val, y_train, y_val


def model(hidden):
    return tf.keras.Sequential([tf.keras.Input((64,)), tf.keras.layers.Dense(25, activation=hidden),
                                tf.keras.layers.Dense(15, activation=hidden), tf.keras.layers.Dense(10)])


if __name__ == "__main__":
    print("Same network, same data, 30 epochs with Adam; only the hidden activation changes.\n")
    for act in ["linear", "sigmoid", "relu"]:
        tf.random.set_seed(0)
        m = model(act)
        m.compile(tf.keras.optimizers.Adam(1e-3), tf.keras.losses.SparseCategoricalCrossentropy(from_logits=True),
                  metrics=["accuracy"])
        h = m.fit(X_train, y_train, epochs=30, batch_size=32, verbose=0, validation_data=(X_val, y_val))
        acc = h.history["val_accuracy"]
        print(f"   {act:8} validation accuracy after 5 epochs {acc[4]:.1%}, after 30 {acc[-1]:.1%}")
    print("\n   Linear hidden layers collapse into one linear layer: the network is just logistic regression, which is")
    print("   already strong on these clean 8x8 digits. Sigmoid learns slowly here; ReLU matches the linear model and,")
    print("   unlike it, keeps improving as the network and the data grow.")
