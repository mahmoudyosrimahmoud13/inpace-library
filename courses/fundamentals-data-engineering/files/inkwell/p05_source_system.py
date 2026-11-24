"""Project 5: build Inkwell's source systems, the place all our data comes from.

1. The shop's application database (OLTP), in SQLite: customers, books, orders and order lines. The app does CRUD:
   it inserts rows, UPDATES them in place (an order goes placed -> shipped -> delivered) and soft-deletes customers.
   Updates destroy history, so the database also keeps a change log (filled by triggers), like a database's own
   log that change data capture (CDC) tools read.
2. The website's click events: insert-only JSON lines, one file per day. Each event carries its EVENT time
   (when it happened, on the visitor's phone). Some events arrive a day late, some twice, and one line is broken.

Every run simulates more days of business, continuing where the last run stopped.

Run:  python p05_source_system.py            (simulates 7 days)
      python p05_source_system.py --days 1   (one more day: use this later to test incremental ingestion)
"""
import argparse
import json
import random
import sqlite3
from datetime import date, datetime, timedelta

from common import EVENTS, SOURCE_DB, log

FIRST_DAY = date(2026, 3, 1)
FIRST = ["Mona", "Omar", "Laila", "Youssef", "Nour", "Karim", "Salma", "Ahmed", "Hana", "Tarek", "Dina", "Ali"]
LAST = ["Hassan", "Farouk", "Mansour", "Saleh", "Nabil", "Kamel", "Gamal", "Fathy"]
CITIES = ["Cairo", "Alexandria", "Giza", "Mansoura", "Aswan", "Tanta"]
BOOKS = [("Dune", "Frank Herbert", "Sci-fi", 14.0), ("Emma", "Jane Austen", "Classic", 9.5),
         ("Beloved", "Toni Morrison", "Fiction", 12.0), ("The Hobbit", "J. R. R. Tolkien", "Fantasy", 11.0),
         ("Clean Code", "Robert C. Martin", "Tech", 32.0), ("Sapiens", "Yuval Noah Harari", "History", 16.5),
         ("Atomic Habits", "James Clear", "Self-help", 15.0), ("The Alchemist", "Paulo Coelho", "Fiction", 10.0),
         ("Designing Data-Intensive Applications", "Martin Kleppmann", "Tech", 45.0),
         ("Season of Migration to the North", "Tayeb Salih", "Classic", 13.0)]

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    customer_id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE, city TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, deleted_at TEXT);
CREATE TABLE IF NOT EXISTS books (
    book_id INTEGER PRIMARY KEY, title TEXT NOT NULL, author TEXT, genre TEXT, price REAL NOT NULL);
CREATE TABLE IF NOT EXISTS orders (
    order_id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL REFERENCES customers, status TEXT NOT NULL,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS order_lines (
    order_id INTEGER NOT NULL REFERENCES orders, book_id INTEGER NOT NULL REFERENCES books,
    qty INTEGER NOT NULL, unit_price REAL NOT NULL, PRIMARY KEY (order_id, book_id));
CREATE TABLE IF NOT EXISTS change_log (
    change_id INTEGER PRIMARY KEY AUTOINCREMENT, table_name TEXT, row_id INTEGER, op TEXT, changed_at TEXT,
    row_json TEXT);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""

# Triggers copy every insert and update into change_log: the database remembers what UPDATE overwrote.
TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS customers_ins AFTER INSERT ON customers BEGIN
  INSERT INTO change_log (table_name,row_id,op,changed_at,row_json) VALUES ('customers', NEW.customer_id, 'insert',
    NEW.updated_at, json_object('customer_id',NEW.customer_id,'name',NEW.name,'email',NEW.email,'city',NEW.city,
    'created_at',NEW.created_at,'updated_at',NEW.updated_at,'deleted_at',NEW.deleted_at)); END;
CREATE TRIGGER IF NOT EXISTS customers_upd AFTER UPDATE ON customers BEGIN
  INSERT INTO change_log (table_name,row_id,op,changed_at,row_json) VALUES ('customers', NEW.customer_id, 'update',
    NEW.updated_at, json_object('customer_id',NEW.customer_id,'name',NEW.name,'email',NEW.email,'city',NEW.city,
    'created_at',NEW.created_at,'updated_at',NEW.updated_at,'deleted_at',NEW.deleted_at)); END;
CREATE TRIGGER IF NOT EXISTS orders_ins AFTER INSERT ON orders BEGIN
  INSERT INTO change_log (table_name,row_id,op,changed_at,row_json) VALUES ('orders', NEW.order_id, 'insert',
    NEW.updated_at, json_object('order_id',NEW.order_id,'customer_id',NEW.customer_id,'status',NEW.status,
    'created_at',NEW.created_at,'updated_at',NEW.updated_at)); END;
CREATE TRIGGER IF NOT EXISTS orders_upd AFTER UPDATE ON orders BEGIN
  INSERT INTO change_log (table_name,row_id,op,changed_at,row_json) VALUES ('orders', NEW.order_id, 'update',
    NEW.updated_at, json_object('order_id',NEW.order_id,'customer_id',NEW.customer_id,'status',NEW.status,
    'created_at',NEW.created_at,'updated_at',NEW.updated_at)); END;
"""

NEXT_STATUS = {"placed": "shipped", "shipped": "delivered"}


def ts(day: date, rnd: random.Random) -> str:
    t = datetime(day.year, day.month, day.day, rnd.randint(8, 22), rnd.randint(0, 59), rnd.randint(0, 59))
    return t.strftime("%Y-%m-%d %H:%M:%S")


def setup(db: sqlite3.Connection) -> None:
    db.executescript(SCHEMA + TRIGGERS)
    if not db.execute("SELECT count(*) FROM books").fetchone()[0]:
        db.executemany("INSERT INTO books (title, author, genre, price) VALUES (?,?,?,?)", BOOKS)


def simulate_day(db: sqlite3.Connection, day: date, late_events: list) -> dict:
    rnd = random.Random(day.toordinal())
    n_new = rnd.randint(3, 6)
    for _ in range(n_new):                                     # new sign-ups (INSERT)
        cid = (db.execute("SELECT coalesce(max(customer_id), 0) FROM customers").fetchone()[0]) + 1
        t = ts(day, rnd)
        db.execute("INSERT INTO customers (name,email,city,created_at,updated_at) VALUES (?,?,?,?,?)",
                   (f"{rnd.choice(FIRST)} {rnd.choice(LAST)}", f"reader{cid}@example.com", rnd.choice(CITIES), t, t))
    active = [r[0] for r in db.execute("SELECT customer_id FROM customers WHERE deleted_at IS NULL AND created_at < ?",
                                          (str(day),))]
    for cid in rnd.sample(active, k=min(2, len(active))):     # people move city (UPDATE)
        city = db.execute("SELECT city FROM customers WHERE customer_id = ?", (cid,)).fetchone()[0]
        db.execute("UPDATE customers SET city=?, updated_at=? WHERE customer_id=?",
                   (rnd.choice([c for c in CITIES if c != city]), ts(day, rnd), cid))
    if day.toordinal() % 4 == 0 and len(active) > 10:          # a customer closes the account (soft DELETE)
        t = ts(day, rnd)
        db.execute("UPDATE customers SET deleted_at=?, updated_at=? WHERE customer_id=?", (t, t, rnd.choice(active)))

    for oid, status in db.execute("SELECT order_id, status FROM orders WHERE status IN ('placed','shipped')").fetchall():
        if rnd.random() < 0.6:                                # orders move forward (UPDATE)
            new = "cancelled" if status == "placed" and rnd.random() < 0.1 else NEXT_STATUS[status]
            db.execute("UPDATE orders SET status=?, updated_at=? WHERE order_id=?", (new, ts(day, rnd), oid))

    books = db.execute("SELECT book_id, price FROM books").fetchall()
    active = [r[0] for r in db.execute("SELECT customer_id FROM customers WHERE deleted_at IS NULL")]
    n_orders = rnd.randint(8, 15)
    events, ev_no = [], 0
    for _ in range(n_orders):                                 # new orders (INSERT)
        cid, t = rnd.choice(active), ts(day, rnd)
        signed_up = db.execute("SELECT created_at FROM customers WHERE customer_id = ?", (cid,)).fetchone()[0]
        t = max(t, signed_up)                                 # nobody orders before they have an account
        cur = db.execute("INSERT INTO orders (customer_id,status,created_at,updated_at) VALUES (?,?,?,?)",
                         (cid, "placed", t, t))
        for book_id, price in rnd.sample(books, k=rnd.randint(1, 3)):
            db.execute("INSERT INTO order_lines VALUES (?,?,?,?)", (cur.lastrowid, book_id, rnd.randint(1, 2), price))
        for kind in ("page_view", "page_view", "add_to_cart", "purchase"):
            ev_no += 1
            events.append({"event_id": f"{day:%Y%m%d}-{ev_no:04d}", "event_type": kind, "customer_id": cid,
                           "event_time": t, "order_id": cur.lastrowid if kind == "purchase" else None})
    for _ in range(rnd.randint(20, 40)):                      # visitors who only look around
        ev_no += 1
        events.append({"event_id": f"{day:%Y%m%d}-{ev_no:04d}", "event_type": "page_view",
                       "customer_id": None, "event_time": ts(day, rnd), "order_id": None})

    # The messy part of event data: some events arrive late, some twice, one line is broken.
    rnd.shuffle(events)
    late_today, keep = events[:3], events[3:]
    keep += late_events                      # yesterday's late events arrive in today's file
    keep += events[3:5]                      # a phone that retried: two duplicates
    EVENTS.mkdir(parents=True, exist_ok=True)
    with open(EVENTS / f"events-{day}.jsonl", "w", encoding="utf-8") as f:
        for e in keep:
            f.write(json.dumps(e) + "\n")
        f.write('{"event_id": "broken", "event_type": \n')   # a truncated line
    late_events[:] = late_today
    return {"new_customers": n_new, "orders": n_orders, "events": len(keep)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    days = ap.parse_args().days
    SOURCE_DB.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(SOURCE_DB)
    setup(db)
    row = db.execute("SELECT value FROM meta WHERE key='last_day'").fetchone()
    start = date.fromisoformat(row[0]) + timedelta(days=1) if row else FIRST_DAY
    late = json.loads((db.execute("SELECT value FROM meta WHERE key='late'").fetchone() or ["[]"])[0])
    for i in range(days):
        day = start + timedelta(days=i)
        stats = simulate_day(db, day, late)
        db.execute("INSERT OR REPLACE INTO meta VALUES ('last_day', ?)", (str(day),))
        db.execute("INSERT OR REPLACE INTO meta VALUES ('late', ?)", (json.dumps(late),))
        db.commit()
        log("p05", f"simulated {day}", **stats)
    for table in ("customers", "books", "orders", "order_lines", "change_log"):
        print(f"  {table:12} {db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]:6} rows")
