"""Project 12: batch processing. A log analysis the Unix way, then MapReduce from scratch, then two kinds of join.

Chapter 10's example: a web server log, "what are the 5 most popular pages?".

A. The Unix approach (cat | awk | sort | uniq -c | sort -r | head), in Python, in one pass.
B. MAPREDUCE from scratch, with real parallel processes:
     map    each input file -> (key, value) pairs, PARTITIONED by hash(key) into one sorted file per reducer
     shuffle each reducer collects its partition from every mapper (files on disk, like HDFS)
     reduce each reducer merges its sorted inputs and handles one key at a time
C. JOINS: page views by the viewer's age group, joining activity events with a user database.
     sort-merge (reduce-side) join: both inputs keyed by user id, merged in the reducer
     broadcast hash join (map-side): the small users table is loaded into every mapper's memory

Run:  python p12_mapreduce.py
"""
import heapq
import json
import random
import shutil
from collections import Counter
from itertools import groupby
from multiprocessing import Pool
from pathlib import Path
from zlib import crc32

DATA = Path(__file__).resolve().parent / "lab_data" / "p12"
REDUCERS = 4


def make_inputs(files=8, lines=25_000):
    rnd = random.Random(12)
    pages = [f"/css/typography.css", "/", "/about", "/blog/ddia", "/pricing"] + [f"/blog/post-{i}" for i in range(200)]
    weights = [30, 40, 5, 25, 8] + [1] * 200
    logs = DATA / "logs"
    logs.mkdir(parents=True)
    for f in range(files):
        with open(logs / f"access-{f}.log", "w") as out:
            for _ in range(lines):
                user = rnd.randint(1, 5000)
                page = rnd.choices(pages, weights)[0]
                out.write(f'10.0.{user // 256}.{user % 256} - - [27/Feb/2015:17:55:11 +0000] "GET {page} HTTP/1.1" '
                          f'200 3377 "-" "Mozilla/5.0" user={user}\n')
    with open(DATA / "users.jsonl", "w") as out:
        for u in range(1, 5001):
            out.write(json.dumps({"user": u, "birth_year": rnd.randint(1950, 2008)}) + "\n")
    return sorted(logs.glob("*.log"))


def url_of(line: str) -> str:
    return line.split(" ")[6]                           # awk '{print $7}'


def user_of(line: str) -> int:
    return int(line.rsplit("user=", 1)[1])


# ---------------- B: map and reduce tasks (top-level functions, so worker processes can import them) ----------------
def map_task(args):
    path, job = args
    buckets = [[] for _ in range(REDUCERS)]
    with open(path) as f:
        for line in f:
            if job == "count":
                key, value = url_of(line), 1
            else:                                           # "join": tag each record with where it came from
                key, value = user_of(line), ["view", url_of(line)]
            buckets[crc32(str(key).encode()) % REDUCERS].append((key, value))
    out = []
    for r, items in enumerate(buckets):                     # each mapper writes one SORTED file per reducer
        items.sort(key=lambda kv: str(kv[0]))
        p = DATA / "shuffle" / job / f"map-{Path(path).stem}-r{r}.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w") as f:
            for kv in items:
                f.write(json.dumps(kv) + "\n")
        out.append(p)
    return out


def map_users(path):
    """The other side of the reduce-side join: users keyed by id, partitioned the same way."""
    buckets = [[] for _ in range(REDUCERS)]
    with open(path) as f:
        for line in f:
            u = json.loads(line)
            buckets[crc32(str(u["user"]).encode()) % REDUCERS].append((u["user"], ["user", u["birth_year"]]))
    out = []
    for r, items in enumerate(buckets):
        items.sort(key=lambda kv: str(kv[0]))
        p = DATA / "shuffle" / "join" / f"map-users-r{r}.jsonl"
        with open(p, "w") as f:
            for kv in items:
                f.write(json.dumps(kv) + "\n")
        out.append(p)
    return out


def read_sorted(p):
    with open(p) as f:
        for line in f:
            yield tuple(json.loads(line))


def reduce_task(args):
    r, job = args
    inputs = sorted((DATA / "shuffle" / job).glob(f"*-r{r}.jsonl"))
    merged = heapq.merge(*(read_sorted(p) for p in inputs), key=lambda kv: str(kv[0]))
    result = Counter()
    for key, group in groupby(merged, key=lambda kv: kv[0]):   # one key at a time, all its values together
        values = [v for _, v in group]
        if job == "count":
            result[key] += sum(values)
        else:
            births = [v[1] for v in values if v[0] == "user"]
            if births:
                decade = f"born {births[0] // 10 * 10}s"
                result[decade] += sum(1 for v in values if v[0] == "view")
    return dict(result)


def broadcast_map(args):
    path, users = args                                      # the whole small table, in every mapper's memory
    out = Counter()
    with open(path) as f:
        for line in f:
            out[f"born {users[user_of(line)] // 10 * 10}s"] += 1
    return dict(out)


if __name__ == "__main__":
    shutil.rmtree(DATA, ignore_errors=True)
    files = make_inputs()
    print(f"{len(files)} log files, {sum(1 for p in files for _ in open(p)):,} requests\n")

    print("A. Unix style: read every line, count URLs, sort, take 5")
    counts = Counter(url_of(line) for p in files for line in open(p))
    for url, n in counts.most_common(5):
        print(f"   {n:7,} {url}")

    print(f"\nB. MapReduce with {len(files)} map tasks and {REDUCERS} reduce tasks, in parallel processes")
    with Pool() as pool:
        shuffle_files = pool.map(map_task, [(p, "count") for p in files])
        print(f"   map: {sum(len(s) for s in shuffle_files)} sorted shuffle files written")
        partials = pool.map(reduce_task, [(r, "count") for r in range(REDUCERS)])
    total = Counter()
    for part in partials:
        total.update(part)
    for url, n in total.most_common(5):
        print(f"   {n:7,} {url}")
    print("   same answer as A:", total == counts, "| each URL was handled by exactly one reducer:",
          sum(len(p) for p in partials) == len(total))

    print("\nC. Page views by the viewer's birth decade")
    with Pool() as pool:
        pool.map(map_task, [(p, "join") for p in files])
        map_users(DATA / "users.jsonl")
        joined = Counter()
        for part in pool.map(reduce_task, [(r, "join") for r in range(REDUCERS)]):
            joined.update(part)
        users = {json.loads(l)["user"]: json.loads(l)["birth_year"] for l in open(DATA / "users.jsonl")}
        broadcast = Counter()
        for part in pool.map(broadcast_map, [(p, users) for p in files]):
            broadcast.update(part)
    for decade in sorted(joined):
        print(f"   {decade}: {joined[decade]:7,}")
    print("   sort-merge join == broadcast hash join:", joined == broadcast)
    print("   The broadcast join skipped the whole shuffle, because the users table fits in memory.")
