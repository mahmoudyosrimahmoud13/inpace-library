"""Project 7: replication, simulated. Leaders and followers, the anomalies replication lag causes, failover, and
leaderless quorums.

Everything runs on a simulated clock (milliseconds), so results are exact and repeatable. A "network" delivers each
replication message after a random delay.

A. Single leader, two followers, ASYNCHRONOUS replication.
   - read-after-write: a user writes, then reads from a follower that hasn't caught up: their own write is gone.
   - monotonic reads: a user reads twice from different followers and sees time go backwards.
   - fixes: read your own recent writes from the leader; always send a user to the same follower.
B. Failover: the leader dies; a follower is promoted; writes it never received are LOST.
C. Leaderless (Dynamo style): n = 3 replicas, write to w, read from r. With w + r > n, every read overlaps the
   latest write. Read repair fixes stale replicas as a side effect of reading.

Run:  python p07_replication.py
"""
import random

rnd = random.Random(7)


class Replica:
    def __init__(self, name):
        self.name, self.data, self.applied, self.pending = name, {}, 0, {}   # applied = position in the leader's log

    def apply(self, pos, key, value):
        self.pending[pos] = (key, value)
        while self.applied + 1 in self.pending:                   # apply the log strictly in order
            k, v = self.pending.pop(self.applied + 1)
            self.data[k] = v
            self.applied += 1


class LeaderFollower:
    def __init__(self, mean_lag_ms=30):
        self.leader = Replica("leader")
        self.followers = [Replica("follower-1"), Replica("follower-2")]
        self.log, self.in_flight, self.mean_lag = [], [], mean_lag_ms

    def write(self, now, key, value):
        self.log.append((key, value))
        pos = len(self.log)
        self.leader.apply(pos, key, value)
        for f in self.followers:                                  # async: don't wait for the followers
            # usually fast, sometimes very slow (a busy follower, a network hiccup)
            self.in_flight.append((now + 2 + rnd.expovariate(1 / self.mean_lag), f, pos, key, value))
        return pos

    def tick(self, now):
        due = sorted([m for m in self.in_flight if m[0] <= now], key=lambda m: m[2])
        self.in_flight = [m for m in self.in_flight if m[0] > now]
        for _, f, pos, key, value in due:
            f.apply(pos, key, value)


def part_a():
    print("A. Asynchronous leader-follower replication, 1,000 users each write then read 100 ms later")
    db = LeaderFollower()
    now = 0.0
    lost_own_write = backwards = 0
    fixed_own = fixed_backwards = 0
    for u in range(1000):
        key = f"profile:{u}"
        now += 10
        db.write(now, key, f"v{u}")
        db.tick(now + 100)
        # naive: any follower
        f = rnd.choice(db.followers)
        if f.data.get(key) != f"v{u}":
            lost_own_write += 1
        # fix: read from the leader if the user wrote in the last minute
        if db.leader.data.get(key) != f"v{u}":
            fixed_own += 1
        # monotonic reads: the same user reads a hot counter twice, 20 ms apart
        db.write(now, "counter", u)
        db.tick(now + 150)
        a, sticky = rnd.choice(db.followers), db.followers[u % 2]   # user u's own follower, always the same
        r1, s1 = a.data.get("counter", -1), sticky.data.get("counter", -1)
        db.tick(now + 170)
        b = rnd.choice(db.followers)
        r2, s2 = b.data.get("counter", -1), sticky.data.get("counter", -1)
        if r2 < r1:
            backwards += 1                                        # the second read saw an OLDER value
        if s2 < s1:
            fixed_backwards += 1
    print(f"   read-after-write violated:  {lost_own_write:4d} of 1000 reads (any follower)   "
          f"-> {fixed_own} when users read their own recent writes from the leader")
    print(f"   monotonic reads violated:   {backwards:4d} of 1000 read pairs (random followers) "
          f"-> {fixed_backwards} when each user sticks to one follower")


def part_b():
    print("\nB. Failover with asynchronous replication")
    db = LeaderFollower(mean_lag_ms=30)
    now = 0.0
    for i in range(1, 501):
        now += 2
        db.write(now, f"order:{i}", "paid")
        db.tick(now)
    # The leader crashes at this moment. The most up-to-date follower is promoted.
    new_leader = max(db.followers, key=lambda f: f.applied)
    lost = len(db.log) - new_leader.applied
    print(f"   the old leader had {len(db.log)} writes; the best follower had {new_leader.applied}")
    print(f"   promoting it LOSES {lost} acknowledged writes (users were told 'paid'). Synchronous or")
    print("   semi-synchronous replication, or a consensus protocol, is what prevents this.")


def part_c():
    print("\nC. Leaderless replication with quorums, n = 3")
    for w, r in [(1, 1), (2, 2), (3, 1)]:
        stale = 0
        replicas = [dict() for _ in range(3)]                     # key -> (version, value)
        for i in range(2000):
            key = f"k{i % 50}"
            version = i
            # a write reaches only w replicas before we acknowledge (the rest are slow or down)
            for idx in rnd.sample(range(3), w):
                replicas[idx][key] = (version, f"value-{i}")
            # a read asks r replicas and takes the highest version
            got = max((replicas[idx].get(key, (-1, None)) for idx in rnd.sample(range(3), r)), key=lambda x: x[0])
            if got[0] != version:
                stale += 1
        print(f"   w={w}, r={r}  (w + r {'>' if w + r > 3 else '<='} n): stale reads {stale:4d} of 2000")

    print("   Read repair: a read that sees an old version on a replica writes the new one back")
    replicas = [{"cart": (1, "1 book")}, {"cart": (2, "2 books")}, {"cart": (1, "1 book")}]
    answers = [rep["cart"] for rep in replicas[:2]]               # r = 2 reads replicas 0 and 1
    newest = max(answers)
    for rep in replicas[:2]:
        if rep["cart"] < newest:
            rep["cart"] = newest                                  # repaired
    print(f"   read returned {newest[1]!r}; replica 0 repaired; replica 2 still stale until anti-entropy: "
          f"{[rep['cart'][1] for rep in replicas]}")


if __name__ == "__main__":
    part_a()
    part_b()
    part_c()
