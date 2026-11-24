"""Project 2: the whole data engineering lifecycle in one small file.

Inkwell Books is a small online bookshop. Its owner asks one question: "How much did we sell each day?"
This script answers it by walking through the five stages of the lifecycle, one function each:

    generate -> ingest -> store -> transform -> serve

and two of the undercurrents: a data quality check (data management) and a run log (DataOps).

Run:  python p02_lifecycle.py
Run it twice: the second run doesn't count anything twice (look at how ingest() names its files).
"""
import csv
import json
import random
from datetime import date, timedelta

import duckdb

from common import DATA, log, now_utc

HOME = DATA / "p02"
LANDING = HOME / "landing"   # where the source system drops its files
RAW = HOME / "raw"           # our copy, never edited
REPORT = HOME / "daily_sales.csv"


def generate(day: date, n: int = 20) -> None:
    """GENERATION. The shop's website writes one JSON line per order. We don't own this system: we just
    receive what it produces. Some lines are bad on purpose, as in real life."""
    LANDING.mkdir(parents=True, exist_ok=True)
    rnd = random.Random(day.toordinal())      # same day -> same orders, so runs are repeatable
    with open(LANDING / f"orders-{day}.jsonl", "w", encoding="utf-8") as f:
        for i in range(n):
            order = {"order_id": f"{day:%Y%m%d}-{i:03d}", "day": str(day),
                     "book": rnd.choice(["Dune", "Emma", "Ulysses", "Beloved"]),
                     "price": round(rnd.uniform(5, 30), 2), "qty": rnd.randint(1, 3)}
            if i == 7:
                order["price"] = None          # a broken record from the source
            f.write(json.dumps(order) + "\n")


def ingest() -> int:
    """INGESTION. Move files from the landing area into our raw zone. The file name is the key, so landing
    the same file twice replaces it instead of adding a copy: the step is idempotent."""
    RAW.mkdir(parents=True, exist_ok=True)
    moved = 0
    for src in sorted(LANDING.glob("orders-*.jsonl")):
        (RAW / src.name).write_bytes(src.read_bytes())
        moved += 1
    return moved


def store() -> duckdb.DuckDBPyConnection:
    """STORAGE. Raw files stay as they are; DuckDB reads them in place, a tiny 'data lake'."""
    return duckdb.connect(str(HOME / "p02.duckdb"))


def check_quality(con) -> int:
    """UNDERCURRENT, data management: count records we can't trust, and keep them out."""
    return con.execute(f"""SELECT count(*) FROM read_json_auto('{RAW.as_posix()}/*.jsonl')
                       WHERE price IS NULL OR qty <= 0""").fetchone()[0]


def transform(con) -> None:
    """TRANSFORMATION. Turn order lines into the number the owner asked for."""
    con.execute(f"""
        CREATE OR REPLACE TABLE daily_sales AS
        SELECT CAST(day AS DATE) AS day, count(*) AS orders, round(sum(price * qty), 2) AS revenue
        FROM read_json_auto('{RAW.as_posix()}/*.jsonl')
        WHERE price IS NOT NULL AND qty > 0
        GROUP BY 1 ORDER BY 1""")


def serve(con) -> None:
    """SERVING. Give the owner something she can open: a CSV for her spreadsheet, and a printout."""
    rows = con.execute("SELECT * FROM daily_sales").fetchall()
    with open(REPORT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["day", "orders", "revenue"])
        w.writerows(rows)
    for day, orders, revenue in rows:
        print(f"  {day}  {orders:3d} orders  {revenue:9.2f}")


if __name__ == "__main__":
    start = date(2026, 3, 1)
    for d in range(3):
        generate(start + timedelta(days=d))
    files = ingest()
    con = store()
    bad = check_quality(con)
    transform(con)
    print(f"Daily sales (report saved to {REPORT.name}):")
    serve(con)
    log("p02", "lifecycle run finished", files=files, bad_records=bad, finished=now_utc())
