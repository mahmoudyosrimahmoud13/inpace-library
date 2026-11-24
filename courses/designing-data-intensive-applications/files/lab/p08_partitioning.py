"""Project 8: partitioning (sharding): how to split data across nodes, and what happens when you add nodes.

A. KEY RANGE versus HASH partitioning of sensor readings keyed by timestamp: range partitioning keeps ranges
   together (fast range scans) but sends every write of "now" to ONE partition: a hot spot.
B. REBALANCING from 4 to 5 nodes: "hash mod N" moves most keys; a FIXED NUMBER OF PARTITIONS (many more partitions
   than nodes; whole partitions move) moves about 1/5 of them.
C. SECONDARY INDEXES: a LOCAL index (each partition indexes its own documents) means a read asks every partition
   (scatter/gather); a GLOBAL index partitioned by term means one partition answers the read, but a write may touch
   several partitions.
D. A HOT KEY (a celebrity): add a random two-digit suffix to spread its writes, and pay for it on reads.

Run:  python p08_partitioning.py
"""
import hashlib
import random
from collections import Counter, defaultdict

rnd = random.Random(8)


def h(key: str) -> int:
    return int.from_bytes(hashlib.md5(key.encode()).digest()[:8], "big")


# ---------------- A ----------------
print("A. 100,000 sensor readings written during the last hour, 4 partitions")
DAY_START = 1_700_000_000
readings = [f"{DAY_START + 23 * 3600 + rnd.randrange(3600)}" for _ in range(100_000)]
bounds = [DAY_START + 6 * 3600 * i for i in range(1, 4)]              # 4 ranges of 6 hours each


def by_range(key: str) -> int:
    t = int(key)
    return sum(t >= b for b in bounds)


range_load = Counter(by_range(k) for k in readings)
hash_load = Counter(h(k) % 4 for k in readings)
print("   key range:", [range_load.get(p, 0) for p in range(4)], "<- one partition takes every write")
print("   hash     :", [hash_load.get(p, 0) for p in range(4)], "<- even, but 'all readings from 23:00 to 23:10'")
print("              now has to ask all 4 partitions")

# ---------------- B ----------------
print("\nB. Adding a 5th node to 4: how many of 100,000 keys must move?")
keys = [f"user:{i}" for i in range(100_000)]
moved_mod = sum(h(k) % 4 != h(k) % 5 for k in keys)

PARTITIONS = 256                                                       # fixed forever, chosen up front
partition_of = {k: h(k) % PARTITIONS for k in keys}
owner4 = {p: p % 4 for p in range(PARTITIONS)}                         # 64 partitions per node
owner5 = dict(owner4)
per_node = Counter(owner5.values())
for p in range(PARTITIONS):                                            # the new node steals partitions until fair
    if per_node[4] >= PARTITIONS // 5:
        break
    donor = owner5[p]
    if per_node[donor] > PARTITIONS // 5:
        owner5[p] = 4
        per_node[donor] -= 1
        per_node[4] += 1
moved_fixed = sum(owner4[partition_of[k]] != owner5[partition_of[k]] for k in keys)
print(f"   hash mod N        : {moved_mod:6,} keys move ({moved_mod / len(keys):.0%})")
print(f"   {PARTITIONS} fixed partitions: {moved_fixed:6,} keys move ({moved_fixed / len(keys):.0%}), "
      f"in {sum(owner4[p] != owner5[p] for p in range(PARTITIONS))} whole partitions")

# ---------------- C ----------------
print("\nC. Secondary index on car colour, 8 partitions, 20,000 cars")
P = 8
colours = ["red", "black", "white", "silver", "blue", "green"]
cars = {i: rnd.choice(colours) for i in range(20_000)}
local = defaultdict(lambda: defaultdict(list))                         # partition -> colour -> car ids
for car, colour in cars.items():
    local[car % P][colour].append(car)
global_index = defaultdict(list)                                       # colour -> car ids, partitioned by colour
for car, colour in cars.items():
    global_index[colour].append(car)
asked_local = sum(1 for p in range(P) if local[p]["red"])
print(f"   local index : 'find red cars' asks {asked_local} of {P} partitions (scatter/gather; the slowest one decides)")
print(f"   global index: 'find red cars' asks 1 partition (the one that holds the term 'red', h % P = {h('red') % P})")
new_car_partition = 20_001 % P
print(f"   but writing one new red car touches partition {new_car_partition} (the car) AND partition "
      f"{h('red') % P} (the index): usually updated asynchronously, so the index can lag")

# ---------------- D ----------------
print("\nD. A celebrity's post gets 50,000 likes in a minute, 16 partitions")
likes_plain = Counter(h("post:celebrity") % 16 for _ in range(50_000))
likes_split = Counter(h(f"post:celebrity#{rnd.randrange(100):02d}") % 16 for _ in range(50_000))
print(f"   one key      : busiest partition takes {max(likes_plain.values()):,} writes")
print(f"   key + suffix : busiest partition takes {max(likes_split.values()):,} writes, "
      f"but counting the likes now reads 100 keys")
