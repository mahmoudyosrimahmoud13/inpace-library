"""Project 1: describe load and measure performance, the way Chapter 1 does.

Part A: Chirp, a tiny Twitter. Two ways to build the home timeline (the book's example):
  1. fan-out on READ:  store each post once; when someone opens the app, gather the posts of everyone they follow.
  2. fan-out on WRITE: when someone posts, copy the post into every follower's timeline ("cache").
We count the work each approach does for the same day of traffic. The LOAD PARAMETERS that decide the winner are
the read/write ratio and the distribution of followers (a few celebrities have millions).

Part B: response times as a distribution. Mean versus median versus p95/p99/p999, and TAIL LATENCY AMPLIFICATION:
when one page needs several backend calls, the slowest call decides the page's time.

Run:  python p01_load_and_latency.py
Only Python's standard library is needed for every project in this course.
"""
import random
import statistics

rnd = random.Random(1)

# ---------------- Part A: fan-out ----------------
USERS = 10_000
# Followers follow a heavy-tailed distribution: most users have few, a handful have very many.
followers = {u: int(rnd.paretovariate(1.2) * 3) for u in range(USERS)}
following = {u: rnd.randint(20, 200) for u in range(USERS)}      # how many accounts each user follows

POSTS_PER_DAY = 20_000
TIMELINE_READS_PER_DAY = 600_000                                  # reads are far more common than writes

posters = [rnd.randrange(USERS) for _ in range(POSTS_PER_DAY)]
readers = [rnd.randrange(USERS) for _ in range(TIMELINE_READS_PER_DAY)]

# Fan-out on read: a post is 1 write; a timeline read looks at every followed account.
read_cost = sum(following[r] for r in readers)
write_cost_a = POSTS_PER_DAY
# Fan-out on write: a post is written into every follower's timeline; a read is 1 lookup.
write_cost_b = sum(followers[p] for p in posters)
read_cost_b = TIMELINE_READS_PER_DAY

celebrity = max(followers, key=followers.get)
print("A. Chirp's home timeline, one day of traffic")
print(f"   users {USERS:,}, posts {POSTS_PER_DAY:,}, timeline reads {TIMELINE_READS_PER_DAY:,}")
print(f"   biggest account has {followers[celebrity]:,} followers; median user has "
      f"{int(statistics.median(followers.values()))}")
print(f"   fan-out on read : {write_cost_a:>12,} writes + {read_cost:>12,} lookups = {write_cost_a + read_cost:>12,}")
print(f"   fan-out on write: {write_cost_b:>12,} writes + {read_cost_b:>12,} lookups = {write_cost_b + read_cost_b:>12,}")

print(f"   one post by the biggest account alone = {followers[celebrity]:,} timeline writes")

# The hybrid Twitter moved to: fan out on write, except for accounts with huge follower counts, whose posts are
# fetched at read time instead.
CELEB_LIMIT = 1_000
celebs = {u for u, n in followers.items() if n >= CELEB_LIMIT}
write_cost_c = sum(followers[p] for p in posters if p not in celebs)
# A reader follows each celebrity with probability (its followers / all users): that's the extra work per read.
celeb_follows_per_read = sum(followers[c] for c in celebs) / USERS
read_cost_c = int(TIMELINE_READS_PER_DAY * (1 + celeb_follows_per_read))
print(f"   hybrid ({len(celebs)} accounts over {CELEB_LIMIT:,} followers read on demand): "
      f"{write_cost_c:>9,} writes + {read_cost_c:>12,} lookups = {write_cost_c + read_cost_c:>12,}")
worst = max(n for u, n in followers.items() if u not in celebs)
print(f"   ...a bit more total work, but no single post now causes more than {worst:,} writes")

# ---------------- Part B: response time percentiles ----------------
def one_call() -> float:
    """Most calls are fast; a few hit garbage collection, a lost packet or a cold cache."""
    t = rnd.lognormvariate(3.0, 0.35)            # around 20 ms
    if rnd.random() < 0.02:
        t += rnd.uniform(200, 1200)              # the rare slow path
    return t


def pct(values: list, p: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, int(len(s) * p / 100))]


calls = [one_call() for _ in range(100_000)]
print("\nB. 100,000 backend calls (milliseconds)")
print(f"   mean {statistics.mean(calls):7.1f}   median (p50) {pct(calls, 50):7.1f}")
print(f"   p95  {pct(calls, 95):7.1f}   p99 {pct(calls, 99):7.1f}   p999 {pct(calls, 99.9):7.1f}")
print("   The mean hides the slow requests; the high percentiles show what your unhappiest users wait.")

print("\n   Tail latency amplification: a page that needs N backend calls in parallel waits for the slowest")
for n in (1, 5, 20, 50):
    pages = [max(one_call() for _ in range(n)) for _ in range(20_000)]
    slow = sum(1 for p in pages if p > 200) / len(pages)
    print(f"   {n:3d} calls per page: median page {pct(pages, 50):7.1f} ms, p99 {pct(pages, 99):7.1f} ms, "
          f"pages slower than 200 ms: {slow:6.1%}")
