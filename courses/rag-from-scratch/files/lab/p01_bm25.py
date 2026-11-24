"""Project 1: the corpus, an evaluation set, and a search engine you write yourself (BM25)."""
import math
import time
from collections import Counter, defaultdict

from common import evaluate, load_docs, tokenize


class BM25:
    """Okapi BM25: rare words count more (idf), repeats count less and less (k1), long documents are
    penalised a little (b)."""

    def __init__(self, texts, k1=1.5, b=0.75):
        self.k1, self.b = k1, b
        self.tfs = [Counter(tokenize(t)) for t in texts]
        self.lens = [sum(tf.values()) for tf in self.tfs]
        self.avg = sum(self.lens) / len(self.lens)
        self.postings = defaultdict(list)          # word -> [(doc number, count)]: the inverted index
        for i, tf in enumerate(self.tfs):
            for w, c in tf.items():
                self.postings[w].append((i, c))
        n = len(texts)
        self.idf = {w: math.log(1 + (n - len(p) + 0.5) / (len(p) + 0.5)) for w, p in self.postings.items()}

    def search(self, query, k=5):
        scores = defaultdict(float)
        for w in set(tokenize(query)):
            for i, c in self.postings.get(w, []):
                norm = c + self.k1 * (1 - self.b + self.b * self.lens[i] / self.avg)
                scores[i] += self.idf[w] * c * (self.k1 + 1) / norm
        return sorted(scores.items(), key=lambda x: -x[1])[:k]


if __name__ == "__main__":
    docs = load_docs()
    print(f"Corpus: {len(docs):,} documents, {sum(len(d['text']) for d in docs):,} characters")
    print("   e.g.", docs[300]["title"], "->", docs[300]["text"][:70].replace("\n", " "), "...\n")

    def grep(q, k):  # the baseline: documents containing the most query words
        words = set(tokenize(q))
        scored = sorted(docs, key=lambda d: -len(words & set(tokenize(d["title"] + " " + d["text"]))))
        return [d["id"] for d in scored[:k]]
    r, m = evaluate(grep)
    print(f"1. Word overlap      recall@5 = {r:.0%}   MRR = {m:.2f}")

    t = time.perf_counter()
    bm = BM25([d["title"] + "\n" + d["text"] for d in docs])
    print(f"   BM25 index built in {(time.perf_counter() - t) * 1000:.0f} ms: {len(bm.postings):,} distinct words")
    search = lambda q, k: [docs[i]["id"] for i, _ in bm.search(q, k)]
    r, m = evaluate(search, show_misses=4)
    print(f"2. BM25              recall@5 = {r:.0%}   MRR = {m:.2f}")

    t = time.perf_counter()
    for _ in range(100):
        bm.search("remove a folder and everything inside it")
    print(f"   one search takes {(time.perf_counter() - t) * 10:.2f} ms\n")

    q = "Delete a folder together with everything inside it"
    print(f"3. {q!r}")
    for i, s in bm.search(q, 3):
        print(f"   {s:5.1f}  {docs[i]['id']}")
