"""Project 13: stream processing. A partitioned log like Kafka, consumer offsets, change data capture, and why
dual writes break.

A. A LOG-BASED MESSAGE BROKER: a topic is a set of partitions; each partition is an append-only file. Messages with
   the same key go to the same partition (so they stay in order). A consumer remembers its OFFSET per partition. If
   it crashes after processing but before saving the offset, it reprocesses: AT-LEAST-ONCE delivery.
B. DUAL WRITES versus CDC: an app writes to the database AND to a search index. Two concurrent requests can apply in
   different orders to the two systems: they disagree FOREVER. With change data capture, the index follows the
   database's own ordered log, so it always converges.
C. A STREAM-TABLE JOIN and a TUMBLING WINDOW: enrich click events with the user's current country (a table kept up
   to date from a changelog stream), counting clicks per country per minute.

Run:  python p13_streams.py
"""
import json
import random
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from zlib import crc32

DATA = Path(__file__).resolve().parent / "lab_data" / "p13"
rnd = random.Random(13)


class Topic:
    def __init__(self, name, partitions=3):
        self.dir = DATA / name
        self.dir.mkdir(parents=True, exist_ok=True)
        self.n = partitions

    def produce(self, key, value):
        p = crc32(str(key).encode()) % self.n
        with open(self.dir / f"p{p}.log", "a") as f:
            f.write(json.dumps({"key": key, "value": value}) + "\n")

    def read(self, partition, offset):
        """All messages from `offset` on. A message's offset is its line number."""
        path = self.dir / f"p{partition}.log"
        if not path.exists():
            return []
        lines = path.read_text().splitlines()
        return [(i, json.loads(l)) for i, l in enumerate(lines) if i >= offset]


class Consumer:
    def __init__(self, topic, group):
        self.topic, self.file = topic, DATA / f"offsets-{group}.json"

    def offsets(self):
        return json.loads(self.file.read_text()) if self.file.exists() else {}

    def run(self, handle, crash_after=None):
        offs, done = self.offsets(), 0
        for p in range(self.topic.n):
            for i, msg in self.topic.read(p, offs.get(str(p), 0)):
                handle(msg)
                done += 1
                if crash_after is not None and done == crash_after:
                    return "crashed"                        # processed, but the offset was never saved
                offs[str(p)] = i + 1
        self.file.write_text(json.dumps(offs))              # commit offsets
        return "ok"


def part_a():
    print("A. A topic with 3 partitions; a consumer counts page views and crashes once")
    views = Topic("page-views")
    for i in range(3000):
        user = rnd.randint(1, 200)
        views.produce(user, {"user": user, "page": rnd.choice(["/", "/books", "/cart"]), "seq": i})
    sizes = [sum(1 for _ in open(views.dir / f"p{p}.log")) for p in range(3)]
    print(f"   messages per partition: {sizes} (each user's events land in one partition, in order)")

    counted, seen_ids = Counter(), Counter()
    consumer = Consumer(views, "counter")
    print("   first run :", consumer.run(lambda m: counted.update([m["value"]["page"]]), crash_after=1200))
    print("   restart   :", consumer.run(lambda m: counted.update([m["value"]["page"]])))
    print(f"   naive count = {sum(counted.values()):,} for 3,000 events: the 1,200 processed before the crash were"
          f" counted twice")
    # Idempotent processing: remember which message ids were already applied. (A real system stores these ids in the
    # same transaction as the result, so the two can never disagree.)
    consumer2 = Consumer(views, "idempotent")

    def apply_once(m):
        if seen_ids[m["value"]["seq"]] == 0:
            counted2.update([m["value"]["page"]])
        seen_ids[m["value"]["seq"]] += 1

    counted2 = Counter()
    consumer2.run(apply_once, crash_after=1200)
    consumer2.run(apply_once)
    print(f"   idempotent count = {sum(counted2.values()):,}: duplicates delivered, but applied once")


def part_b():
    print("\nB. Keeping a search index in sync with a database")
    disagree = 0
    for trial in range(1000):
        db, index = {}, {}
        # Two requests set the same item at about the same time; each write's arrival order is random per system.
        writes = [("item:1", "price=10"), ("item:1", "price=12")]
        db_order = writes[:] if rnd.random() < 0.5 else writes[::-1]
        index_order = writes[:] if rnd.random() < 0.5 else writes[::-1]
        for k, v in db_order:
            db[k] = v
        for k, v in index_order:
            index[k] = v
        disagree += db != index
    print(f"   dual writes: database and index disagree in {disagree} of 1000 races, and nothing ever fixes it")

    disagree = 0
    for trial in range(1000):
        db, index, changelog = {}, {}, []
        writes = [("item:1", "price=10"), ("item:1", "price=12")]
        for k, v in (writes if rnd.random() < 0.5 else writes[::-1]):
            db[k] = v
            changelog.append((k, v))                        # the database's own log, in the order IT applied them
        for k, v in changelog:                              # the index consumes the log, in that same order
            index[k] = v
        disagree += db != index
    print(f"   change data capture: they disagree in {disagree} of 1000 races")


def part_c():
    print("\nC. Clicks per country per minute: a stream-table join and a tumbling window")
    profile_changes = [(0, 7, "Egypt"), (0, 8, "Egypt"), (0, 9, "Kenya"), (95, 7, "Morocco")]   # (second, user, country)
    clicks = sorted((rnd.randint(0, 179), rnd.choice([7, 8, 9])) for _ in range(60))             # (second, user)
    table, windows = {}, defaultdict(Counter)
    changes = iter(profile_changes)
    nxt = next(changes, None)
    for second, user in clicks:
        while nxt and nxt[0] <= second:                     # apply every profile change up to this event's time
            table[nxt[1]] = nxt[2]
            nxt = next(changes, None)
        windows[second // 60][table[user]] += 1             # join with the table AS IT WAS at this moment
    for minute in sorted(windows):
        print(f"   minute {minute}: {dict(sorted(windows[minute].items()))}")
    print("   user 7 moved to Morocco at second 95: earlier clicks stay with Egypt, later ones go to Morocco.")


if __name__ == "__main__":
    shutil.rmtree(DATA, ignore_errors=True)
    part_a()
    part_b()
    part_c()
