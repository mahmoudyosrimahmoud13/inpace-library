"""Project 4: combine searches. Keyword search finds exact names, embeddings find meaning; together they beat both.
Then a second view of every document (its one-line summary) and reciprocal rank fusion (RRF) to merge the lists."""
import numpy as np

from common import evaluate, load_docs
from p02_chunking import by_paragraph, chunk_search, make_chunks
from p03_embeddings import VectorIndex, normalize, pretrained


def rrf(*ranked_lists, k=60):
    """Reciprocal rank fusion: each list gives 1 / (60 + rank) to each item. No scores to calibrate, only ranks,
    so lists from very different searches can be merged fairly."""
    score = {}
    for lst in ranked_lists:
        for rank, item in enumerate(lst, 1):
            score[item] = score.get(item, 0) + 1 / (k + rank)
    return sorted(score, key=lambda x: -score[x])


class SummaryIndex:
    """One vector per document from its title and first line: docstrings start with a one-line summary
    ("Recursively delete a directory tree."), the most useful sentence to match a question against."""

    def __init__(self, model, docs):
        self.model, self.ids = model, [d["id"] for d in docs]
        lines = [d["title"].split("(")[0] + ": " + d["text"].strip().split("\n")[0] for d in docs]
        self.vecs = normalize(model.encode(lines))

    def doc_search(self, q, k=5):
        sims = self.vecs @ normalize(self.model.encode([q]))[0]
        return [self.ids[i] for i in np.argsort(-sims)[:k]]


if __name__ == "__main__":
    docs = load_docs()
    chunks = make_chunks(docs, by_paragraph)
    model = pretrained()
    _, bm25 = chunk_search(chunks)
    emb = VectorIndex(model, chunks)
    summ = SummaryIndex(model, docs)

    runs = {
        "BM25 on chunks": bm25,
        "embeddings on chunks": emb.doc_search,
        "embeddings on one-line summaries": summ.doc_search,
        "hybrid: BM25 + chunk embeddings": lambda q, k: rrf(bm25(q, 20), emb.doc_search(q, 20))[:k],
        "hybrid: all three": lambda q, k: rrf(bm25(q, 20), emb.doc_search(q, 20), summ.doc_search(q, 20))[:k],
    }
    print(f"{'retriever':36} {'recall@5':>9} {'recall@10':>10} {'MRR':>5}")
    for name, fn in runs.items():
        r5, m = evaluate(fn, k=5)
        r10, _ = evaluate(fn, k=10)
        print(f"{name:36} {r5:9.0%} {r10:10.0%} {m:5.2f}")

    best = runs["hybrid: all three"]
    print()
    for q in ["Delete a folder together with everything inside it", "Create a directory and any missing parent folders",
              "Pick k different random items from a list"]:
        print(f"{q!r}\n   -> {best(q, 3)}")
    print()
    evaluate(best, show_misses=5)
