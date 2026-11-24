"""Shared pieces of the Ask-Python project: the corpus, a tokenizer, the evaluation set and the scorer."""
import json
import re
from pathlib import Path

HERE = Path(__file__).parent
STOP = set("""a an the and or of to in on for with by at from as is are be it its this that these those i me my you
your we how do does can what which who when where why get make into not no so if then than there their them any
all each every one some way like use using want need""".split())


def load_docs():
    """The corpus: one document per module, class, function or method, with its docstring."""
    return json.loads((HERE / "pydocs.json").read_text(encoding="utf-8"))["docs"]


def load_eval():
    """45 questions, written the way people ask, each with the document(s) that answer it."""
    return json.loads((HERE / "evalset.json").read_text(encoding="utf-8"))


def tokenize(text):
    """Lowercase words; split snake_case and dotted names; drop very common words."""
    text = re.sub(r"[._]", " ", text.lower())
    return [w for w in re.findall(r"[a-z0-9]+", text) if w not in STOP and len(w) > 1]


def evaluate(retrieve, k=5, show_misses=0):
    """recall@k: how often a right document is in the top k. MRR: 1/rank of the first right one, averaged."""
    hits, rr, misses = 0, 0.0, []
    for item in load_eval():
        got = retrieve(item["q"], k)
        rank = next((i + 1 for i, d in enumerate(got) if d in item["gold"]), None)
        if rank:
            hits += 1
            rr += 1 / rank
        else:
            misses.append((item["q"], got[:3]))
    n = len(load_eval())
    for q, got in misses[:show_misses]:
        print(f"     missed: {q!r} -> {got}")
    return hits / n, rr / n
