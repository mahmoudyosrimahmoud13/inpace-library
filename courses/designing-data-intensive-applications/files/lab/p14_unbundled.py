"""Project 14 (capstone): an "unbundled database". One event log is the source of truth; everything else is a view
derived from it, and can be rebuilt or added at any time by replaying the log.

Payments app "Nilepay":
  * clients send money transfers, each with a unique REQUEST ID (made by the client, kept across its retries);
  * an ingest step appends each request to the event log ONCE, however often the client retries (end-to-end
    duplicate suppression, the book's end-to-end argument);
  * three derived views consume the log: account BALANCES, a SEARCH index over transfer notes, and DAILY totals;
  * a new view is added later (fraud alerts) by replaying the log from the beginning: no migration;
  * an AUDIT recomputes every balance from the log and compares ("trust, but verify"), and catches a corrupted view.

Run:  python p14_unbundled.py
"""
import json
import random
import shutil
import uuid
from collections import Counter, defaultdict
from pathlib import Path

DATA = Path(__file__).resolve().parent / "lab_data" / "p14"
rnd = random.Random(14)


class EventLog:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.seen = set()                                   # request ids already in the log

    def append_once(self, event: dict) -> bool:
        if event["request_id"] in self.seen:
            return False                                    # a retry of something already recorded: drop it
        with open(self.path, "a") as f:
            f.write(json.dumps(event) + "\n")
        self.seen.add(event["request_id"])
        return True

    def replay(self, from_offset=0):
        with open(self.path) as f:
            for i, line in enumerate(f):
                if i >= from_offset:
                    yield i, json.loads(line)


class View:
    """A derived view: it applies events in log order and remembers how far it got."""
    def __init__(self):
        self.offset = 0

    def catch_up(self, log: EventLog):
        for i, e in log.replay(self.offset):
            self.apply(e)
            self.offset = i + 1


class Balances(View):
    def __init__(self):
        super().__init__()
        self.balance = defaultdict(int)

    def apply(self, e):
        self.balance[e["from"]] -= e["amount"]
        self.balance[e["to"]] += e["amount"]


class Search(View):
    def __init__(self):
        super().__init__()
        self.index = defaultdict(set)                       # word -> request ids (an inverted index)

    def apply(self, e):
        for word in e["note"].lower().split():
            self.index[word].add(e["request_id"])


class Daily(View):
    def __init__(self):
        super().__init__()
        self.totals = Counter()

    def apply(self, e):
        self.totals[e["day"]] += e["amount"]


class FraudAlerts(View):                                    # added on "day 2", built from the whole history
    def __init__(self):
        super().__init__()
        self.sent = defaultdict(int)
        self.alerts = []

    def apply(self, e):
        self.sent[e["from"]] += e["amount"]
        if e["amount"] >= 900 and self.sent[e["from"]] > 3000:
            self.alerts.append(f"{e['from']} sent {e['amount']} on day {e['day']} (total {self.sent[e['from']]})")


def client_requests(n=2000):
    accounts = [f"acct-{i:03d}" for i in range(50)]
    notes = ["rent", "dinner split", "books", "school fees", "gift", "taxi", "groceries", "loan repayment"]
    for _ in range(n):
        a, b = rnd.sample(accounts, 2)
        req = {"request_id": str(uuid.UUID(int=rnd.getrandbits(128))), "from": a, "to": b,
               "amount": rnd.choice([10, 25, 50, 100, 250, 500, 950]), "note": rnd.choice(notes), "day": rnd.randint(1, 7)}
        yield req
        while rnd.random() < 0.15:                          # the network timed out: the client retries, same id
            yield dict(req)


if __name__ == "__main__":
    shutil.rmtree(DATA, ignore_errors=True)
    log = EventLog(DATA / "transfers.log")
    received = recorded = 0
    for req in client_requests():
        received += 1
        recorded += log.append_once(req)
    print(f"1. {received:,} requests received (including client retries), {recorded:,} transfers recorded once each")

    balances, search, daily = Balances(), Search(), Daily()
    for view in (balances, search, daily):
        view.catch_up(log)
    print(f"2. Views built from the log: {len(balances.balance)} balances (they sum to "
          f"{sum(balances.balance.values())}: money is neither created nor lost), "
          f"{len(search.index)} search words, daily totals {dict(sorted(daily.totals.items()))}")
    print(f"   search 'school' -> {len(search.index['school'])} transfers")

    fraud = FraudAlerts()                                   # a brand-new view: replay everything
    fraud.catch_up(log)
    print(f"3. New fraud view built by replaying {fraud.offset:,} events: {len(fraud.alerts)} alerts, "
          f"e.g. {fraud.alerts[0] if fraud.alerts else '-'}")

    more = 0
    for req in client_requests(300):                        # more traffic arrives; views just keep consuming
        more += log.append_once(req)
    for view in (balances, search, daily, fraud):
        view.catch_up(log)
    print(f"4. {more} more transfers: every view caught up from its own offset ({balances.offset:,} events)")

    balances.balance["acct-007"] += 500                     # a bug (or a bit flip) corrupts one derived value
    audit = Balances()
    audit.catch_up(log)
    wrong = {a: (balances.balance[a], audit.balance[a]) for a in audit.balance if balances.balance[a] != audit.balance[a]}
    print(f"5. Audit: recomputed every balance from the log; mismatches: {wrong}")
    balances = audit                                        # the fix: throw the view away and rebuild it
    print("   fixed by rebuilding the view from the log. The log is the truth; views are disposable.")
