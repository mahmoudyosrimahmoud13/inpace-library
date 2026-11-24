"""Project 2: cut documents into chunks, and measure what each way of cutting does to search and to context size."""
import re
import statistics

from common import evaluate, load_docs
from p01_bm25 import BM25


def fixed(text, size=400, overlap=80):
    """Every `size` characters, each chunk repeating the last `overlap` characters of the one before."""
    step = size - overlap
    return [text[i:i + size] for i in range(0, max(len(text) - overlap, 1), step)]


def by_paragraph(text, target=500):
    """Split at blank lines, then glue small paragraphs together up to about `target` characters."""
    out, cur = [], ""
    for para in re.split(r"\n\s*\n", text):
        if cur and len(cur) + len(para) > target:
            out.append(cur)
            cur = ""
        cur = (cur + "\n\n" + para).strip()
    return out + [cur] if cur else out


def make_chunks(docs, splitter, header=True):
    """Each chunk keeps the id of its document. With header=True it also starts with the document's title,
    so a chunk from the middle of a long text still says what it's about."""
    chunks = []
    for d in docs:
        for n, piece in enumerate(splitter(d["text"])):
            chunks.append({"doc": d["id"], "n": n, "title": d["title"],
                           "text": (d["title"] + "\n" + piece) if header else piece})
    return chunks


def chunk_search(chunks):
    bm = BM25([c["text"] for c in chunks])

    def search(q, k):
        seen, out = set(), []
        for i, _ in bm.search(q, k * 4):          # several chunks can come from one document
            if chunks[i]["doc"] not in seen:
                seen.add(chunks[i]["doc"])
                out.append(chunks[i]["doc"])
        return out[:k]
    return bm, search


if __name__ == "__main__":
    docs = load_docs()
    whole = lambda t: [t]
    print(f"{'strategy':34} {'chunks':>7} {'median':>7} {'longest':>8} {'recall@5':>9} {'MRR':>5} {'top-5 context':>14}")
    for name, split, header in [("whole documents", whole, True),
                                ("fixed 400 chars, 80 overlap", fixed, True),
                                ("fixed 400, no title header", fixed, False),
                                ("paragraphs, up to ~500 chars", by_paragraph, True),
                                ("paragraphs, no title header", by_paragraph, False)]:
        chunks = make_chunks(docs, split, header)
        bm, search = chunk_search(chunks)
        r, m = evaluate(search)
        lens = [len(c["text"]) for c in chunks]
        ctx = statistics.mean(sum(len(chunks[i]["text"]) for i, _ in bm.search(q["q"], 5))
                              for q in __import__("common").load_eval())
        print(f"{name:34} {len(chunks):7,} {statistics.median(lens):7.0f} {max(lens):8,} {r:9.0%} {m:5.2f} {ctx:11,.0f} ch")

    d = next(d for d in docs if d["id"] == "subprocess.Popen")
    parts = by_paragraph(d["text"])
    print(f"\nThe {d['id']} document ({len(d['text']):,} chars) as paragraph chunks: {[len(p) for p in parts]}")
    print("   fixed-size chunk 2 starts mid-sentence:", repr(fixed(d["text"])[1][:60]))
    print("   paragraph chunk 2 starts cleanly:      ", repr(parts[1][:60]) if len(parts) > 1 else "(one chunk)")
