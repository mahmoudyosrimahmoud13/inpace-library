"""Project 7 (day 9): PCA. Squeeze the 20 numbers collaborative filtering learned for each movie into 2, see how much
survives, and read what the two main directions mean."""
import numpy as np
from sklearn.decomposition import PCA

from movies import movies, ratings, split
from p3_collaborative import fit

if __name__ == "__main__":
    r, m = ratings(), movies()
    train, _ = split(r)
    X = fit(train, 20, 5.0)[0]
    counts = r.groupby("movie").size().reindex(m["movie"]).fillna(0).to_numpy()
    keep = counts >= 150                                       # well-known movies: their vectors are reliable
    Xk, titles = X[keep], m["title"].to_numpy()[keep]
    Xc = Xk - Xk.mean(0)
    U, S, Vt = np.linalg.svd(Xc, full_matrices=False)          # PCA by hand: the SVD of the centred data
    explained = S ** 2 / (S ** 2).sum()
    print(f"1. {keep.sum()} movies with 150+ ratings, 20 learned numbers each")
    print("   share of variance on each principal component: " + ", ".join(f"{e:.0%}" for e in explained[:6]) + " ...")
    print(f"   the first 2 keep {explained[:2].sum():.0%}; it takes {np.searchsorted(np.cumsum(explained), 0.9) + 1} to keep 90%")
    sk = PCA(2).fit(Xk)
    print(f"   scikit-learn's PCA agrees: {np.allclose(np.abs(sk.components_), np.abs(Vt[:2]), atol=1e-6)}\n")
    Z = Xc @ Vt[:2].T
    for i in range(2):
        order = np.argsort(Z[:, i])
        print(f"2. Component {i + 1}, one end:   " + "; ".join(t[:32] for t in titles[order[:4]]))
        print(f"   {'':12} other end: " + "; ".join(t[:32] for t in titles[order[-4:]]))
    print("\n   Read the ends and name the axis yourself: PCA finds directions, people give them meaning.")
