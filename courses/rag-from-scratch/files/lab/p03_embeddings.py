"""Project 3: turn text into vectors two ways, and search by meaning instead of by shared words.

A. LSA, built from scratch: word counts (TF-IDF), squeezed to 256 numbers per chunk with an SVD. It only knows the
   words of this corpus.
B. A small pretrained embedding model (model2vec potion-base-8M, 30 MB, CPU only): it learned from far more text that
   "folder" and "directory" mean the same thing.
"""
import math
import time
from collections import Counter

import numpy as np

from common import evaluate, load_docs, tokenize
from p02_chunking import by_paragraph, chunk_search, make_chunks

MODEL = "minishlab/potion-base-8M"


class LSA:
    def __init__(self, texts, dim=256):
        tfs = [Counter(tokenize(t)) for t in texts]
        df = Counter(w for tf in tfs for w in tf)
        self.vocab = {w: i for i, w in enumerate(sorted(w for w, c in df.items() if c >= 2))}
        self.idf = np.array([math.log(len(texts) / df[w]) for w in self.vocab])
        X = self._tfidf(tfs)
        # SVD: X ≈ U S Vt. The rows of Vt are 256 "topics": words that tend to appear together.
        _, _, vt = np.linalg.svd(X, full_matrices=False)
        self.topics = vt[:dim].T                      # (words, 256)

    def _tfidf(self, tfs):
        X = np.zeros((len(tfs), len(self.vocab)), dtype=np.float32)
        for r, tf in enumerate(tfs):
            for w, c in tf.items():
                if w in self.vocab:
                    X[r, self.vocab[w]] = 1 + math.log(c)
        return X * self.idf

    def encode(self, texts):
        return self._tfidf([Counter(tokenize(t)) for t in texts]) @ self.topics


def normalize(v):
    return v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)


class VectorIndex:
    """The simplest vector database: every vector in one matrix, and a search compares the question with all of
    them (cosine similarity = dot product of unit vectors)."""

    def __init__(self, model, chunks):
        self.model, self.chunks = model, chunks
        self.vecs = normalize(model.encode([c["text"] for c in chunks])).astype(np.float32)

    def search(self, q, k=5):
        sims = self.vecs @ normalize(self.model.encode([q]))[0]
        top = np.argpartition(-sims, k)[:k]
        return [(int(i), float(sims[i])) for i in top[np.argsort(-sims[top])]]

    def doc_search(self, q, k=5):
        seen, out = set(), []
        for i, _ in self.search(q, k * 4):
            d = self.chunks[i]["doc"]
            if d not in seen:
                seen.add(d)
                out.append(d)
        return out[:k]

    def save(self, path):
        np.save(path, self.vecs)


def pretrained():
    from model2vec import StaticModel
    return StaticModel.from_pretrained(MODEL)


if __name__ == "__main__":
    chunks = make_chunks(load_docs(), by_paragraph)
    _, bm25 = chunk_search(chunks)
    r, m = evaluate(bm25)
    print(f"BM25 (project 2)             recall@5 = {r:.0%}   MRR = {m:.2f}")

    t = time.perf_counter()
    lsa = VectorIndex(LSA([c["text"] for c in chunks]), chunks)
    print(f"A. LSA built in {time.perf_counter() - t:.1f} s: {len(lsa.model.vocab):,} words -> 256 numbers per chunk")
    r, m = evaluate(lsa.doc_search)
    print(f"   LSA                       recall@5 = {r:.0%}   MRR = {m:.2f}")

    t = time.perf_counter()
    emb = VectorIndex(pretrained(), chunks)
    print(f"B. {MODEL}: {len(chunks):,} chunks embedded in {time.perf_counter() - t:.1f} s, "
          f"{emb.vecs.shape[1]} numbers each, {emb.vecs.nbytes / 1e6:.1f} MB")
    r, m = evaluate(emb.doc_search, show_misses=3)
    print(f"   pretrained embeddings     recall@5 = {r:.0%}   MRR = {m:.2f}")

    t = time.perf_counter()
    for _ in range(100):
        emb.search("delete a folder")
    print(f"   one search over {len(chunks):,} vectors: {(time.perf_counter() - t) * 10:.2f} ms\n")

    q = "Delete a folder together with everything inside it"
    print(f"{q!r}")
    print("   BM25      :", bm25(q, 3))
    print("   LSA       :", lsa.doc_search(q, 3))
    print("   embeddings:", emb.doc_search(q, 3))
    a, b, c = normalize(emb.model.encode(["folder", "directory", "banana"]))
    print(f"\n   cosine(folder, directory) = {a @ b:.2f}   cosine(folder, banana) = {a @ c:.2f}")
    emb.save("chunk_vectors.npy")
    print("   saved chunk_vectors.npy")
