"""Project 4 (day 5): content-based filtering, and recommending at scale (retrieve, then rank). Compare three
recommenders by how often a movie someone loved (5 stars, held out) is in their top 10."""
import numpy as np

from movies import GENRES, movies, ratings, split
from p3_collaborative import N_MOVIES, fit

if __name__ == "__main__":
    r, m = ratings(), movies()
    train, test = split(r)
    loved = test[test["rating"] == 5]
    G = m[GENRES].to_numpy(float)
    G = G / np.maximum(np.linalg.norm(G, axis=1, keepdims=True), 1e-9)            # one vector per movie, length 1
    seen = train.groupby("user")["movie"].apply(lambda s: set(s - 1))
    pop = np.bincount(train["movie"] - 1, minlength=N_MOVIES).astype(float)
    mean = train.groupby("movie")["rating"].mean().reindex(range(1, N_MOVIES + 1)).fillna(0).to_numpy()
    X, W, b, mu = fit(train, 20, 5.0)

    def top10(scores, user):
        scores = scores.copy()
        scores[list(seen.get(user, set()))] = -np.inf                             # never recommend what they've rated
        return set(np.argpartition(-scores, 10)[:10])

    def content_scores(user):
        mine = train[train["user"] == user]
        w = (mine["rating"] - mine["rating"].mean()).to_numpy()                   # liked more than usual: +, less: -
        profile = w @ G[mine["movie"] - 1]
        quality = np.log1p(pop) / np.log1p(pop.max())
        return G @ profile + 2 * quality                                           # similar genres, then popular-ish

    hits = {"most popular": 0, "content-based (genres)": 0, "collaborative filtering": 0}
    users = loved["user"].unique()
    for u in users:
        want = set(loved[loved["user"] == u]["movie"] - 1)
        hits["most popular"] += len(want & top10(pop, u)) > 0
        hits["content-based (genres)"] += len(want & top10(content_scores(u), u)) > 0
        cf = X @ W[u - 1] + b[u - 1] + mu[:, 0] + 0.002 * pop                     # predicted rating, a nudge to popular
        hits["collaborative filtering"] += len(want & top10(cf, u)) > 0
    print(f"1. {len(users)} people have a held-out 5-star rating. How often is one of them in the top 10?")
    for name, h in hits.items():
        print(f"   {name:26} {h / len(users):6.1%}")

    print("\n2. Retrieval, then ranking: for one person, keep the 100 movies whose genres fit best (cheap), then")
    print("   rank only those 100 with the collaborative model (expensive at scale).")
    u = users[0]
    cand = np.argsort(-content_scores(u))[:100]
    cand = [c for c in cand if c not in seen.get(u, set())]
    ranked = sorted(cand, key=lambda c: -(X[c] @ W[u - 1] + b[u - 1] + mu[c, 0]))
    titles = list(dict.fromkeys(m["title"].iloc[c] for c in ranked))[:5]          # a few movies appear twice in the data
    print(f"   person {u}: " + "; ".join(titles))
    print(f"   scored {len(cand)} movies instead of {N_MOVIES:,}: with millions of items, that's the difference that matters")
