"""Project 1 (day 1): k-means from scratch. Group the 1,682 movies by genre and by how people rate them."""
import numpy as np
from sklearn.cluster import KMeans

from movies import GENRES, movies, ratings


def kmeans(X, k, iters=100, seed=0):
    rng = np.random.default_rng(seed)
    C = X[rng.choice(len(X), k, replace=False)]                  # start from k random movies
    for _ in range(iters):
        labels = ((X[:, None, :] - C[None]) ** 2).sum(-1).argmin(1)   # assign each point to its nearest centroid
        newC = np.array([X[labels == j].mean(0) if np.any(labels == j) else C[j] for j in range(k)])
        if np.allclose(newC, C):
            break
        C = newC                                                 # move each centroid to the mean of its points
    cost = ((X - C[labels]) ** 2).sum(-1).mean()
    return labels, C, cost


if __name__ == "__main__":
    m, r = movies(), ratings()
    stats = r.groupby("movie")["rating"].agg(["mean", "count"])
    m = m.join(stats, on="movie").fillna({"mean": 3, "count": 0})
    X = np.column_stack([m[GENRES].to_numpy(float), (m["mean"].to_numpy() - 3) / 1.0, np.log1p(m["count"]) / 3])
    print(f"1. {len(m):,} movies, each as {X.shape[1]} numbers: 19 genre flags, average rating, log of rating count\n")
    print("2. The cost (distortion) for different k, best of 5 random starts each:")
    for k in (2, 4, 6, 8, 10, 12):
        best = min((kmeans(X, k, seed=s) for s in range(5)), key=lambda t: t[2])
        print(f"   k = {k:2}: {best[2]:.3f}")
    labels, C, cost = min((kmeans(X, 8, seed=s) for s in range(5)), key=lambda t: t[2])
    print("\n3. Eight clusters (k = 8), described by their centroid and an example:")
    for j in np.argsort(-np.bincount(labels)):
        top = [GENRES[i] for i in np.argsort(-C[j][:19])[:2] if C[j][i] > 0.3]
        members = m[labels == j].sort_values("count", ascending=False)
        print(f"   {np.sum(labels == j):4} movies  {'/'.join(top) or 'mixed':22} avg rating {C[j][19] + 3:.1f}  "
              f"e.g. {members['title'].iloc[0]}")
    sk = KMeans(8, n_init=5, random_state=0).fit(X)
    print(f"\n4. scikit-learn's KMeans on the same data: cost {sk.inertia_ / len(X):.3f} (yours {cost:.3f})")
