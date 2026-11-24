"""Project 3 (days 3-4): collaborative filtering from scratch. Learn a vector for every movie and every person from
the ratings alone, predict ratings nobody gave, and recommend movies to a new person."""
import numpy as np

from movies import movies, ratings, split

N_USERS, N_MOVIES = 943, 1682


def fit(train, k=20, lam=5.0, lr=0.01, steps=300, seed=0):
    """Minimize the regularized cost: sum over known ratings of (w_j . x_i + b_j - y)^2 / 2, plus lam/2 times the
    squared size of every X and W. Ratings are mean-normalized per movie first. The steps use Adam (as the course's
    TensorFlow version does): popular movies have hundreds of ratings, so their plain gradients are huge and one
    learning rate can't suit every movie."""
    rng = np.random.default_rng(seed)
    Y = np.zeros((N_MOVIES, N_USERS))
    R = np.zeros_like(Y)
    Y[train["movie"] - 1, train["user"] - 1] = train["rating"]
    R[train["movie"] - 1, train["user"] - 1] = 1
    mu = (Y.sum(1) / np.maximum(R.sum(1), 1))[:, None]        # each movie's mean rating
    Yn = (Y - mu) * R
    X, W, b = rng.normal(0, 0.1, (N_MOVIES, k)), rng.normal(0, 0.1, (N_USERS, k)), np.zeros(N_USERS)
    params = [X, W, b]
    m1 = [np.zeros_like(p) for p in params]
    m2 = [np.zeros_like(p) for p in params]
    for t in range(1, steps + 1):
        E = (X @ W.T + b - Yn) * R                               # errors on known ratings only
        grads = [E @ W + lam * X, E.T @ X + lam * W, E.sum(0)]
        for p, g, a, v in zip(params, grads, m1, m2):            # Adam: a step size per number
            a *= 0.9
            a += 0.1 * g
            v *= 0.999
            v += 0.001 * g * g
            p -= lr * (a / (1 - 0.9 ** t)) / (np.sqrt(v / (1 - 0.999 ** t)) + 1e-8)
    return X, W, b, mu


def predict(model, df):
    X, W, b, mu = model
    p = (X[df["movie"] - 1] * W[df["user"] - 1]).sum(1) + b[df["user"] - 1] + mu[df["movie"] - 1, 0]
    return np.clip(p, 1, 5)


def rmse(a, b):
    return float(np.sqrt(np.mean((np.asarray(a) - np.asarray(b)) ** 2)))


if __name__ == "__main__":
    r, m = ratings(), movies()
    train, test = split(r)
    print(f"1. {len(train):,} ratings to learn from, {len(test):,} held out. The matrix is "
          f"{len(r) / N_USERS / N_MOVIES:.1%} filled.\n")
    print("2. Predicting the held-out ratings (RMSE, in stars):")
    print(f"   everyone's average ({train['rating'].mean():.2f})      {rmse(test['rating'], train['rating'].mean()):.3f}")
    mm = train.groupby("movie")["rating"].mean()
    print(f"   each movie's average                {rmse(test['rating'], test['movie'].map(mm).fillna(train['rating'].mean())):.3f}")
    for k, lam in [(20, 0.0), (20, 5.0), (50, 5.0)]:
        model = fit(train, k, lam)
        print(f"   collaborative filtering k={k}, lambda={lam:<4} {rmse(test['rating'], predict(model, test)):.3f}")

    model = fit(train, 20, 5.0)
    X = model[0]
    star = m.index[m["title"].str.startswith("Star Wars")][0]
    sims = X @ X[star] / (np.linalg.norm(X, axis=1) * np.linalg.norm(X[star]) + 1e-9)
    counts = r.groupby("movie").size().reindex(range(1, N_MOVIES + 1)).fillna(0).to_numpy()
    near = [i for i in np.argsort(-sims) if i != star and counts[i] >= 100][:5]
    print(f"\n3. Movies whose learned vectors are closest to Star Wars (1977), among movies with 100+ ratings:")
    print("   " + "; ".join(m["title"].iloc[i] for i in near))
    print("   Nobody told the model about genres or sequels: it found them in who rated what.")
