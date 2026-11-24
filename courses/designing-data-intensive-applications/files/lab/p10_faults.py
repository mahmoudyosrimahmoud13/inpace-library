"""Project 10: the trouble with distributed systems: timeouts, clocks, and a paused process.

A. TIMEOUTS. A node usually answers in ~10 ms but sometimes pauses (garbage collection, a busy disk) for seconds.
   You can't tell "dead" from "slow". A short timeout declares healthy nodes dead; a long one takes ages to notice
   a real crash. We measure both for several timeouts.
B. CLOCKS and LAST WRITE WINS. Two nodes' clocks differ by a few milliseconds. A write that really happened LATER
   gets an EARLIER timestamp and is silently thrown away.
C. A PAUSED LEASE HOLDER and FENCING TOKENS. A client holds a lease (a lock with a timeout), pauses for 15 s,
   wakes up still believing it holds the lease, and writes. Storage that checks a fencing token rejects the stale write.

Run:  python p10_faults.py
"""
import random

rnd = random.Random(10)


# ---------------- A ----------------
def response_ms() -> float:
    t = rnd.lognormvariate(2.3, 0.3)                    # ~10 ms
    if rnd.random() < 0.003:
        t += rnd.uniform(500, 8000)                     # a long pause: alive, just slow
    return t


print("A. Failure detection with a timeout (100,000 health checks of live nodes, plus real crashes)")
checks = [response_ms() for _ in range(100_000)]
print(f"   {'timeout':>9} {'live nodes declared dead':>26} {'time to notice a real crash':>29}")
for timeout in (20, 50, 200, 1000, 10_000):
    false_dead = sum(t > timeout for t in checks)
    # a crashed node never answers: we notice after the timeout, on average half a check interval (500 ms) later
    print(f"   {timeout:>7} ms {false_dead:>14,} ({false_dead / len(checks):6.2%}) {timeout + 500:>22,} ms")
print("   There's no right answer, only a trade-off between false alarms and slow detection.")

# ---------------- B ----------------
print("\nB. Last write wins with clocks less than 3 ms apart (the book's Figure 8-3)")
node1_offset, node3_offset = 0.0, -0.0025               # node 3's clock runs 2.5 ms behind
events = [
    ("client A", "x = 1", 42.0040, "node 1"),           # real time in seconds
    ("client B", "x += 1 -> 2", 42.0055, "node 3"),     # really happened 1.5 ms LATER
]
store = {}
for who, what, real, node in events:
    ts = real + (node1_offset if node == "node 1" else node3_offset)
    value = 1 if "= 1" in what and "+=" not in what else 2
    print(f"   {who} writes {what:12} at real time {real:.4f} s, stamped {ts:.4f} s by {node}'s clock")
    if "x" not in store or ts > store["x"][0]:
        store["x"] = (ts, value)
print(f"   stored x = {store['x'][1]}: client B's later write was DROPPED because its timestamp looked older,")
print("   and nobody got an error. Clock skew silently decides which write survives.")

# ---------------- C ----------------
print("\nC. A lease, a 15-second pause, and fencing tokens")


class LockService:
    def __init__(self):
        self.token, self.holder, self.expires = 0, None, 0.0

    def acquire(self, who, now, ttl=10.0):
        if self.holder is None or now >= self.expires:
            self.token += 1                              # every new lease gets a bigger token
            self.holder, self.expires = who, now + ttl
            return self.token
        return None


class Storage:
    def __init__(self, check_tokens):
        self.check, self.highest, self.log = check_tokens, 0, []

    def write(self, who, token, data):
        if self.check and token < self.highest:
            self.log.append(f"REJECTED {who} (token {token} < {self.highest})")
            return
        self.highest = max(self.highest, token)
        self.log.append(f"{who} wrote {data!r} (token {token})")


for check in (False, True):
    lock, disk = LockService(), Storage(check)
    t1 = lock.acquire("client 1", now=0)                # client 1 gets the lease, token 1
    # client 1 pauses for 15 s (garbage collection): its lease expires at t = 10
    t2 = lock.acquire("client 2", now=12)               # client 2 gets the lease, token 2
    disk.write("client 2", t2, "file v2")
    disk.write("client 1", t1, "file v1")               # client 1 wakes at t = 15, still believes it holds the lease
    print(f"   {'with' if check else 'without'} fencing tokens: " + "; ".join(disk.log))
print("   Without tokens, the stale client overwrote the newer data. A node can't trust its own sense of time.")
