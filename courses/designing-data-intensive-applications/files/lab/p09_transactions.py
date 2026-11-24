"""Project 9: build a tiny multi-version (MVCC) store and watch isolation levels succeed and fail.

The store keeps every committed version of every key, tagged with the transaction that wrote it. Three isolation
levels, each a few lines:

  READ COMMITTED     each read sees the latest committed value AT THAT MOMENT.
  SNAPSHOT ISOLATION each transaction reads from a snapshot taken when it began; at commit, if another transaction
                     committed a write to the same key meanwhile, abort ("first committer wins").
  SERIALIZABLE (SSI) snapshot isolation, plus: abort if anything this transaction READ was changed by a transaction
                     that committed meanwhile (the premise of its decision is out of date).

Then the book's anomalies, with the two transactions interleaved step by step:
  1. read skew (Alice's bank accounts), 2. lost update (a counter), 3. write skew (doctors on call).

Run:  python p09_transactions.py
"""


class Abort(Exception):
    pass


class MVCC:
    def __init__(self, initial: dict):
        self.versions = {k: [(0, v)] for k, v in initial.items()}   # key -> [(commit timestamp, value)]
        self.clock = 0

    def begin(self, level: str) -> "Tx":
        return Tx(self, level)


class Tx:
    def __init__(self, db: MVCC, level: str):
        self.db, self.level, self.start = db, level, db.clock
        self.writes, self.reads = {}, set()

    def read(self, key):
        self.reads.add(key)
        if key in self.writes:
            return self.writes[key]
        history = self.db.versions[key]
        if self.level == "read committed":
            return history[-1][1]                                  # newest committed, whenever it was committed
        return [v for ts, v in history if ts <= self.start][-1]   # newest as of my snapshot

    def write(self, key, value):
        self.writes[key] = value

    def commit(self):
        db = self.db
        if self.level != "read committed":
            changed = {k for k, hist in db.versions.items() if hist[-1][0] > self.start}
            if changed & set(self.writes):
                raise Abort(f"write-write conflict on {sorted(changed & set(self.writes))}")
            if self.level == "serializable" and changed & self.reads:
                raise Abort(f"something I read changed: {sorted(changed & self.reads)}")
        db.clock += 1
        for k, v in self.writes.items():
            db.versions[k].append((db.clock, v))


def run(level, steps, db):
    """steps: list of (tx name, function(tx)). Transactions begin at their first step."""
    txs, aborted = {}, []
    for name, fn in steps:
        if name in aborted:
            continue
        tx = txs.setdefault(name, db.begin(level))
        try:
            fn(tx)
        except Abort as e:
            aborted.append(name)
            print(f"      {name} ABORTED: {e}")
    return aborted


def read_skew(level):
    db = MVCC({"acct1": 500, "acct2": 500})
    seen = {}
    steps = [
        ("Alice", lambda t: seen.__setitem__("1", t.read("acct1"))),
        ("transfer", lambda t: (t.write("acct1", t.read("acct1") + 100), t.write("acct2", t.read("acct2") - 100))),
        ("transfer", lambda t: t.commit()),
        ("Alice", lambda t: seen.__setitem__("2", t.read("acct2"))),
        ("Alice", lambda t: t.commit()),
    ]
    run(level, steps, db)
    print(f"   {level:18}: Alice sees {seen['1']} + {seen['2']} = {seen['1'] + seen['2']}"
          f"{'   <- 100 vanished!' if seen['1'] + seen['2'] != 1000 else ''}")


def lost_update(level):
    db = MVCC({"counter": 0})
    attempts = 0
    steps = [
        ("A", lambda t: t.write("counter", t.read("counter") + 1)),
        ("B", lambda t: t.write("counter", t.read("counter") + 1)),
        ("A", lambda t: t.commit()),
        ("B", lambda t: t.commit()),
    ]
    aborted = run(level, steps, db)
    for name in aborted:                                             # the application retries an aborted transaction
        attempts += 1
        retry = db.begin(level)
        retry.write("counter", retry.read("counter") + 1)
        retry.commit()
    value = db.versions["counter"][-1][1]
    print(f"   {level:18}: two increments -> counter = {value}"
          f"{'   <- one increment LOST' if value != 2 else ''}{f' (after {attempts} retry)' if attempts else ''}")


def write_skew(level):
    db = MVCC({"alice_on_call": True, "bob_on_call": True})

    def go_home(me):
        def step(t):
            on_call = sum(t.read(k) for k in ("alice_on_call", "bob_on_call"))
            if on_call >= 2:                                         # "someone else is still on call, I can leave"
                t.write(f"{me}_on_call", False)
        return step

    steps = [("Alice", go_home("alice")), ("Bob", go_home("bob")), ("Alice", lambda t: t.commit()),
             ("Bob", lambda t: t.commit())]
    run(level, steps, db)
    left = sum(db.versions[k][-1][1] for k in ("alice_on_call", "bob_on_call"))
    print(f"   {level:18}: doctors still on call = {left}{'   <- nobody! write skew' if left == 0 else ''}")


if __name__ == "__main__":
    print("1. Read skew: Alice reads her two accounts while 100 moves between them")
    for level in ("read committed", "snapshot isolation"):
        read_skew(level)
    print("\n2. Lost update: two transactions increment the same counter at the same time")
    for level in ("read committed", "snapshot isolation"):
        lost_update(level)
    print("\n3. Write skew: Alice and Bob both feel unwell and check 'is someone else on call?'")
    for level in ("snapshot isolation", "serializable"):
        write_skew(level)
