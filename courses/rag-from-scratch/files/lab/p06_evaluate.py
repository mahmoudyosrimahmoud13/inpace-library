"""Project 6: measure the answers, not only the search. Five checks run on every answer, then a better prompt is
tested against the first one with the same questions."""
import json
import re
import time

from common import load_eval
from p05_answer import SYSTEM, Assistant

SYSTEM_V2 = SYSTEM + """
Answer in this format:
Answer: <two or three sentences, naming the function, with [n] after each fact>
Example: <one line of code>
Sources: <the numbers you used, like [1][3]>"""

OUT_OF_SCOPE = ["How do I train a neural network with the standard library?",
                "What is the capital of France?",
                "How do I draw a window with buttons?"]
REFUSAL = "I don't know from these docs"
NAME = re.compile(r"\b([a-z_][a-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+)\(")


def check(a, item, corpus_ids, sources_text):
    """Five checks a script can do without a human:
    found    - a right document was among the sources (retrieval did its job)
    correct  - the answer names a right function (the last part of a gold id, like 'rmtree')
    cited    - the answer cites at least one source number
    grounded - every module.function( the answer calls appears in the sources it was given
    refused  - for a question the docs can't answer, it said so"""
    text = a["answer"]
    if item is None:
        return {"refused": REFUSAL.lower() in text.lower()}
    modules = {i.split(".")[0] for i in corpus_ids}
    names = {n for n in NAME.findall(text) if n.split(".")[0] in modules}   # module.function(, not my_var.method(
    return {"found": any(g in a["sources"] for g in item["gold"]),
            "correct": any(g.split(".")[-1] in text for g in item["gold"]),
            "cited": bool(a["cited"]),
            "grounded": all(n.split(".")[-1] in sources_text for n in names),
            "invented": sorted(n for n in names if n not in corpus_ids and n.split(".")[-1] not in sources_text)}


def run(bot, system, questions):
    import p05_answer
    p05_answer.SYSTEM = system
    rows = []
    for item in questions:
        a = bot.answer(item["q"])
        src = " ".join(bot.by_id[i]["title"] + " " + bot.by_id[i]["text"] for i in a["sources"])
        rows.append({"q": item["q"], **check(a, item if item["gold"] else None, bot.by_id, src), "answer": a["answer"]})
    return rows


if __name__ == "__main__":
    bot = Assistant()
    qs = load_eval()[::4] + [{"q": q, "gold": None} for q in OUT_OF_SCOPE]
    print(f"{len(qs) - len(OUT_OF_SCOPE)} questions with known answers + {len(OUT_OF_SCOPE)} the docs can't answer\n")
    results = {}
    for name, system in [("prompt v1", SYSTEM), ("prompt v2 (fixed format)", SYSTEM_V2)]:
        t = time.perf_counter()
        rows = run(bot, system, qs)
        results[name] = rows
        known = [r for r in rows if "found" in r]
        oos = [r for r in rows if "refused" in r]
        pct = lambda key: sum(r[key] for r in known) / len(known)
        print(f"{name:26} found {pct('found'):4.0%}  correct {pct('correct'):4.0%}  cited {pct('cited'):4.0%}  "
              f"grounded {pct('grounded'):4.0%}  refused {sum(r['refused'] for r in oos)}/{len(oos)}  "
              f"({time.perf_counter() - t:.0f} s)")
        memory = [r["q"] for r in known if r["correct"] and not r["found"]]
        print(f"   right without the right source (from the model's memory): {len(memory)}  {memory[:2]}")
        for r in known:
            if r["invented"]:
                print(f"   invented names in {r['q']!r}: {r['invented']}")
        for r in oos:
            if not r["refused"]:
                print(f"   didn't refuse {r['q']!r}: {r['answer'][:80]!r}...")
    json.dump(results, open("answers_eval.json", "w"), indent=1)
    print("\nEvery answer is in answers_eval.json. Read the wrong ones: the numbers tell you where, not why.")
