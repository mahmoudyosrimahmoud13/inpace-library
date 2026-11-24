"""Project 2 (day 3): gradient descent from scratch on the same line, and what the learning rate does."""
import numpy as np

from p1_one_feature import cost, x, y


def descend(alpha, steps=2000, w=0.0, b=0.0):
    history = []
    for i in range(steps):
        err = w * x + b - y
        dw, db = np.mean(err * x), np.mean(err)      # the partial derivatives of the cost
        w, b = w - alpha * dw, b - alpha * db
        if abs(w) > 1e9:
            history.append((i + 1, w, b, cost(w, b)))
            break                                    # diverged: stop here
        if i in (0, 9, 99, 999, steps - 1):
            history.append((i + 1, w, b, cost(w, b)))
    return w, b, history


if __name__ == "__main__":
    W, B = np.polyfit(x, y, 1)
    print(f"Target (exact solution): w = {W:.2f}, b = {B:.2f}, cost {cost(W, B):,.0f}\n")
    for alpha in (0.001, 0.01, 0.1, 0.13):
        w, b, hist = descend(alpha)
        print(f"learning rate {alpha}:")
        for k, (step, w_, b_, c) in enumerate(hist):
            f = (lambda v: f"{v:9.2f}") if abs(w_) < 1e6 else (lambda v: f"{v:9.2e}")
            note = "  (diverged, stopped)" if c > 1e12 and k == len(hist) - 1 else ""
            print(f"   step {step:5}: w = {f(w_)}, b = {f(b_)}, cost " + (f"{c:14,.0f}" if c < 1e12 else f"{c:.2e}") + note)
    print("\nToo small: slow. Bigger: there in about a thousand steps. Too big: every step overshoots and it blows up.")
