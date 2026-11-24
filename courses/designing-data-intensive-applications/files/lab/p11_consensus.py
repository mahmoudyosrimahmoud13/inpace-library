"""Project 11: consistency and consensus, simulated: linearizability, Lamport clocks, two-phase commit, and electing
a leader by majority vote.

A. LINEARIZABILITY (the book's World Cup example): Alice reads the final score from the leader, tells Bob, Bob
   reloads and reads from a lagging follower: the game "isn't over" for him. A linearizable system makes every read
   see the latest completed write.
B. LAMPORT TIMESTAMPS: a counter per node, (counter, node id) pairs give a total order consistent with causality.
   But on its own it can't answer "was this username taken first?" at the moment you ask: you'd need to know you've
   seen every other node's operations. That's what total order broadcast (consensus) provides.
C. TWO-PHASE COMMIT: if the coordinator crashes after participants voted "yes", they are stuck "in doubt",
   holding their locks, until it comes back.
D. LEADER ELECTION by majority vote, Raft style: terms, one vote per node per term, randomized election timeouts,
   and a network partition where the minority side can never elect a leader.

Run:  python p11_consensus.py
"""
import random

rnd = random.Random(11)

# ---------------- A ----------------
print("A. Linearizability: the final score")
leader, follower = {"score": "1-1, playing"}, {"score": "1-1, playing"}
leader["score"] = "2-1, FINAL"                                  # the write completes on the leader
alice = leader["score"]                                         # Alice's request goes to the leader
bob = follower["score"]                                         # Bob, told by Alice, reloads: a follower, not caught up
print(f"   Alice reads {alice!r}, tells Bob; Bob reads {bob!r} AFTER that")
print("   Not linearizable: once anyone has seen the new value, every later read must see it too.")
follower["score"] = leader["score"]                             # replication catches up later

# ---------------- B ----------------
print("\nB. Lamport timestamps on three nodes")


class Node:
    def __init__(self, nid):
        self.id, self.counter = nid, 0

    def local(self, what):
        self.counter += 1
        return (self.counter, self.id, what)

    def send(self, what):
        return self.local(what)

    def receive(self, stamp, what):
        self.counter = max(self.counter, stamp[0])              # jump ahead of anything we've heard of
        return self.local(what)


n1, n2, n3 = Node(1), Node(2), Node(3)
ops = []
ops.append(n1.local("A: create username 'mona'"))
msg = n1.send("A tells B about it")
ops.append(msg)
ops.append(n3.local("C: create username 'mona'"))             # concurrent: nobody told C
ops.append(n2.receive(msg, "B: reads A's message, then edits"))
ops.append(n3.local("C: another edit"))
for stamp in sorted(ops):
    print(f"   ({stamp[0]}, node {stamp[1]})  {stamp[2]}")
print("   The order is total and respects 'A told B'. A's 'mona' sorts before C's, so A wins, but node C couldn't")
print("   know that when its user clicked 'create': it hadn't heard from A yet. Deciding NOW needs consensus.")

# ---------------- C ----------------
print("\nC. Two-phase commit with a coordinator crash")
participants = {"orders db": "idle", "payments db": "idle", "stock db": "idle"}
for p in participants:
    participants[p] = "prepared (voted yes, holding locks)"     # phase 1: everyone promises to commit if asked
coordinator_decision = "commit"
coordinator_alive = False                                       # it crashes before sending phase 2
for p in participants:
    if coordinator_alive:
        participants[p] = "committed"
print("   after the crash:", participants)
print("   They can't commit (maybe someone voted no) or abort (maybe the coordinator already told someone to")
print("   commit). They wait, with rows locked, until the coordinator recovers and reads its log.")


# ---------------- D ----------------
def election(pool, all_nodes, reachable, max_rounds=10):
    """Each round: the nodes in `pool` whose randomized timeout fires first become candidates for a new term and ask
    every node for its vote. A node grants one vote per term, to the first request that reaches it. A candidate with
    votes from a MAJORITY OF ALL NODES (not just the ones it can reach) becomes leader."""
    voted = {}
    for term in range(1, max_rounds + 1):
        timeouts = {n: rnd.uniform(150, 300) for n in pool}
        first = sorted(timeouts, key=timeouts.get)
        # two nodes may time out at almost the same moment: a split vote
        candidates = first[:2] if len(first) > 1 and timeouts[first[1]] - timeouts[first[0]] < 15 else first[:1]
        votes = {c: 0 for c in candidates}
        for voter in all_nodes:
            # each request reaches each voter after a small network delay; the first to arrive gets the vote
            arrivals = sorted(candidates, key=lambda c: 0 if c == voter else timeouts[c] + rnd.uniform(0, 20))
            for c in arrivals:
                if reachable(c, voter) and (voter, term) not in voted:
                    voted[(voter, term)] = c
                    votes[c] += 1
                    break
        detail = ", ".join(f"node {c}: {v} votes" for c, v in votes.items())
        winner = [c for c, v in votes.items() if v > len(all_nodes) // 2]
        if winner:
            return f"term {term}: {detail} -> node {winner[0]} is LEADER"
        print(f"      term {term}: {detail} -> no majority, new term with new random timeouts")
    return f"no leader after {max_rounds} terms"


nodes = [1, 2, 3, 4, 5]
print("\nD. Leader election, 5 nodes (a majority is 3)")
print("   all connected:", election(nodes, nodes, lambda a, b: True))
side_a, side_b = {1, 2}, {3, 4, 5}
same_side = lambda a, b: (a in side_a) == (b in side_a)        # a network partition: {1, 2} | {3, 4, 5}
print("   partition, minority side {1, 2}:")
print("  ", election(sorted(side_a), nodes, same_side, max_rounds=3))
print("   partition, majority side {3, 4, 5}:")
print("  ", election(sorted(side_b), nodes, same_side))
print("   At most one side can hold a majority, so there can never be two leaders in the same term.")
