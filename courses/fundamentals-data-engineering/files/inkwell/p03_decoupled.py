"""Project 3: two architecture principles you can run, "build loosely coupled systems" and "plan for failure".

TIGHT: the shop's order code calls the email service directly. If email is down, the order fails too.
LOOSE: the order code drops an event into a queue (here: a folder) and moves on. A separate consumer reads the
queue, retries when the email service fails, and remembers what it already handled, so a crash and a restart
never send the same email twice.

Run:  python p03_decoupled.py
"""
import json
import random
import shutil

from common import DATA

QUEUE = DATA / "p03" / "queue"
DONE = DATA / "p03" / "done.json"
rnd = random.Random(3)


class EmailDown(Exception):
    pass


def send_email(order_id: str) -> None:
    """A flaky downstream service: it fails about 40% of the time."""
    if rnd.random() < 0.4:
        raise EmailDown(order_id)


# ---------- Tight coupling ----------
def place_order_tight(order_id: str) -> bool:
    try:
        send_email(order_id)              # the order waits on email...
        return True
    except EmailDown:
        return False                      # ...and fails when email fails


# ---------- Loose coupling ----------
def place_order_loose(order_id: str) -> bool:
    QUEUE.mkdir(parents=True, exist_ok=True)
    (QUEUE / f"{order_id}.json").write_text(json.dumps({"order_id": order_id}))
    return True                           # the order succeeds whatever email is doing


def consume(max_tries: int = 5) -> dict:
    """Read every event in the queue. Retry each one up to max_tries. Skip what's already done."""
    done = set(json.loads(DONE.read_text())) if DONE.exists() else set()
    stats = {"sent": 0, "skipped_already_done": 0, "retries": 0, "gave_up": 0}
    for path in sorted(QUEUE.glob("*.json")):
        order_id = json.loads(path.read_text())["order_id"]
        if order_id in done:
            stats["skipped_already_done"] += 1
            path.unlink()
            continue
        for attempt in range(1, max_tries + 1):
            try:
                send_email(order_id)
                done.add(order_id)
                DONE.write_text(json.dumps(sorted(done)))   # remember it before deleting the event
                path.unlink()
                stats["sent"] += 1
                break
            except EmailDown:
                stats["retries"] += 1
                # A real consumer would wait longer after each failure (1 s, 2 s, 4 s...): "backoff".
        else:
            stats["gave_up"] += 1        # stays in the queue for the next run, or a dead-letter folder
    return stats


if __name__ == "__main__":
    shutil.rmtree(DATA / "p03", ignore_errors=True)   # start clean, so every run tells the same story
    orders = [f"A{n:03d}" for n in range(20)]
    tight_ok = sum(place_order_tight(o) for o in orders)
    print(f"Tight coupling: {tight_ok} of {len(orders)} orders succeeded (the rest failed because email did)")

    loose_ok = sum(place_order_loose(o) for o in orders)
    print(f"Loose coupling: {loose_ok} of {len(orders)} orders succeeded")
    print("Consumer, first run:", consume())

    # Simulate a crash: the same events arrive again (a producer retried, or a queue redelivered them).
    for o in orders[:5]:
        place_order_loose(o)
    print("Consumer, after duplicates arrived:", consume())
