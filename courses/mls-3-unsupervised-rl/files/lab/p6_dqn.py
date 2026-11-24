"""Project 6 (day 8): deep Q-learning on a continuous rover. The position is any number from 0 to 6, so no table can
hold Q: a small neural network learns Q(x, action), with a replay buffer, a target network and epsilon-greedy
exploration, the ingredients of DQN."""
import os

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
from collections import deque

import numpy as np
import tensorflow as tf

GAMMA = 0.5
rng = np.random.default_rng(0)
tf.random.set_seed(0)


def step(x, a):
    """Move about 1 unit left (a=0) or right (a=1), with noise. Ends at x <= 0.5 (reward 100) or x >= 5.5 (40)."""
    x2 = x + (1 if a else -1) * rng.normal(1.0, 0.3)
    if x2 <= 0.5:
        return x2, 100.0, True
    if x2 >= 5.5:
        return x2, 40.0, True
    return x2, 0.0, False


def net():
    m = tf.keras.Sequential([tf.keras.Input((1,)), tf.keras.layers.Dense(32, "relu"),
                             tf.keras.layers.Dense(32, "relu"), tf.keras.layers.Dense(2)])
    m.compile(tf.keras.optimizers.Adam(1e-3), "mse")
    return m


if __name__ == "__main__":
    q, target = net(), net()
    target.set_weights(q.get_weights())
    buffer = deque(maxlen=5000)                 # replay buffer: learn from a mix of old and new experience
    eps, updates = 1.0, 0
    for episode in range(400):
        x, done = rng.uniform(1, 5), False
        while not done:
            a = int(rng.integers(2)) if rng.random() < eps else int(q(np.array([[x / 6]]))[0].numpy().argmax())
            x2, r, done = step(x, a)
            buffer.append((x / 6, a, r / 100, x2 / 6, done))     # inputs and rewards scaled to about 0..1
            x = x2
            if len(buffer) >= 256:
                idx = rng.choice(len(buffer), 64, replace=False)
                s, act, rew, s2, d = map(np.array, zip(*[buffer[i] for i in idx]))
                y = q.predict(s[:, None], verbose=0)
                nxt = target.predict(s2[:, None], verbose=0).max(1)      # the target network: a fixed goal
                y[np.arange(64), act] = rew + GAMMA * nxt * (1 - d)
                q.train_on_batch(s[:, None], y)
                updates += 1
                if updates % 100 == 0:
                    target.set_weights(q.get_weights())
        eps = max(0.05, eps * 0.99)
        if (episode + 1) % 100 == 0:
            xs = np.arange(1.0, 5.01, 0.5)
            pol = "".join("<" if v[0] > v[1] else ">" for v in q(xs[:, None] / 6).numpy())
            print(f"episode {episode + 1:3}  epsilon {eps:.2f}  policy at x = 1, 1.5, ... 5: {pol}")
    xs = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    Q = q(xs[:, None] / 6).numpy() * 100
    print("\nLearned Q at x = 1, 2, 3, 4, 5 (in reward units). Here the reward comes on arriving, so from x = 1 going")
    print("left is worth about 100, from x = 2 about 50, and so on, halving with each step (gamma 0.5):")
    print(f"   Q(x, left)  {np.round(Q[:, 0], 1)}\n   Q(x, right) {np.round(Q[:, 1], 1)}")
