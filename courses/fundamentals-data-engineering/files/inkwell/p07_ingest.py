"""Project 7: ingestion. Move data from the source systems into the lake's raw zone, safely and only once.

Four ways of ingesting, one per source, each a pattern from the chapter:

  books        FULL SNAPSHOT     small table, copy all of it every run
  orders       BATCH CDC         only rows with updated_at after the last watermark (the book's "batch-oriented CDC")
  order_lines  FOLLOWS ORDERS    lines of the orders that arrived in this batch
  customers    CONTINUOUS CDC    read the database's change_log after the last change_id: every insert AND update,
                                 so we keep history that UPDATE overwrote
  events       NEW FILES ONLY    each event file once; broken lines go to a dead-letter file, not into the lake

Rules that make it safe to run again and again:
  * a watermark moves forward only AFTER the data is written (a crash in between re-reads, it never skips);
  * a batch's folder name comes from its window, so re-running the same window replaces it instead of duplicating;
  * raw data is never edited: duplicates and late events are kept here and handled in transformation (project 10).

Run:  python p07_ingest.py
      python p05_source_system.py --days 1 && python p07_ingest.py     (a second batch: only the new changes)
"""
import json
import sqlite3

import duckdb

from common import EVENTS, LAKE, SOURCE_DB, STATE, log, need, now_utc

RAW = LAKE / "raw"
DEAD = LAKE / "dead_letter"
WATERMARKS = STATE / "watermarks.json"

SQL_TYPES = {"INTEGER": "BIGINT", "REAL": "DOUBLE", "TEXT": "VARCHAR"}


def load_state() -> dict:
    return json.loads(WATERMARKS.read_text()) if WATERMARKS.exists() else {}


def save_state(state: dict) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    tmp = WATERMARKS.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(WATERMARKS)            # replace() is atomic: the file is either the old one or the new one


def to_parquet(src: sqlite3.Connection, duck, query: str, params: tuple, out_dir, batch: str) -> int:
    """Run a query on the source, save the rows as one Parquet file with two ingestion columns."""
    cur = src.execute(query, params)
    rows = cur.fetchall()
    if not rows:
        return 0
    cols = [d[0] for d in cur.description]
    types = []
    for i, c in enumerate(cols):                       # SQLite types -> DuckDB types, from the first non-null value
        sample = next((r[i] for r in rows if r[i] is not None), "")
        types.append("BIGINT" if isinstance(sample, int) else "DOUBLE" if isinstance(sample, float) else "VARCHAR")
    duck.execute("CREATE OR REPLACE TEMP TABLE batch (" + ", ".join(f'"{c}" {t}' for c, t in zip(cols, types)) + ")")
    duck.executemany(f"INSERT INTO batch VALUES ({', '.join('?' * len(cols))})", rows)
    out_dir.mkdir(parents=True, exist_ok=True)
    duck.execute(f"""COPY (SELECT *, '{batch}' AS _batch_id, TIMESTAMP '{now_utc().replace('T', ' ').rstrip('Z')}' AS _ingested_at
                          FROM batch) TO '{(out_dir / 'part-0.parquet').as_posix()}' (FORMAT parquet)""")
    return len(rows)


def ingest_tables(src, duck, state: dict) -> None:
    # books: full snapshot, one folder per day we took it
    snap = "snapshot=" + now_utc()[:10]
    n = to_parquet(src, duck, "SELECT * FROM books", (), RAW / "books" / snap, snap)
    log("p07", "books snapshot", rows=n)

    # orders: incremental on updated_at (the high watermark)
    lo = state.get("orders_updated_at", "1970-01-01 00:00:00")
    hi = src.execute("SELECT max(updated_at) FROM orders").fetchone()[0]
    if hi and hi > lo:
        batch = f"updated_{lo}_to_{hi}".replace(" ", "T").replace(":", "")
        n = to_parquet(src, duck, "SELECT * FROM orders WHERE updated_at > ? AND updated_at <= ?", (lo, hi),
                       RAW / "orders" / f"batch={batch}", batch)
        m = to_parquet(src, duck, """SELECT l.* FROM order_lines l JOIN orders o USING (order_id)
                                     WHERE o.created_at > ? AND o.created_at <= ?""", (lo, hi),
                       RAW / "order_lines" / f"batch={batch}", batch)
        state["orders_updated_at"] = hi            # move the watermark only after both files are written
        save_state(state)
        log("p07", "orders batch CDC", rows=n, lines=m, watermark=hi)
    else:
        log("p07", "orders: nothing new")

    # customers: log-based CDC from change_log
    last = state.get("customers_change_id", 0)
    top = src.execute("SELECT max(change_id) FROM change_log WHERE table_name = 'customers'").fetchone()[0] or 0
    if top > last:
        batch = f"changes_{last + 1}_to_{top}"
        q = """SELECT change_id, op, changed_at,
                      json_extract(row_json,'$.customer_id') AS customer_id, json_extract(row_json,'$.name') AS name,
                      json_extract(row_json,'$.email') AS email, json_extract(row_json,'$.city') AS city,
                      json_extract(row_json,'$.created_at') AS created_at,
                      json_extract(row_json,'$.deleted_at') AS deleted_at
               FROM change_log WHERE table_name = 'customers' AND change_id > ? AND change_id <= ? ORDER BY change_id"""
        n = to_parquet(src, duck, q, (last, top), RAW / "customer_changes" / f"batch={batch}", batch)
        state["customers_change_id"] = top
        save_state(state)
        log("p07", "customers CDC", changes=n, last_change_id=top)
    else:
        log("p07", "customers: no new changes")


def ingest_events(duck, state: dict) -> None:
    done = set(state.get("event_files", []))
    for path in sorted(EVENTS.glob("events-*.jsonl")):
        if path.name in done:
            continue
        good, bad = [], []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
                good.append((e["event_id"], e["event_type"], e.get("customer_id"), e["event_time"], e.get("order_id")))
            except (json.JSONDecodeError, KeyError):
                bad.append(line)
        if bad:                                       # dead-letter: keep what we couldn't read, to look at later
            DEAD.mkdir(parents=True, exist_ok=True)
            (DEAD / path.name).write_text("\n".join(bad) + "\n", encoding="utf-8")
        duck.execute("""CREATE OR REPLACE TEMP TABLE ev (event_id VARCHAR, event_type VARCHAR, customer_id BIGINT,
                        event_time TIMESTAMP, order_id BIGINT)""")
        duck.executemany("INSERT INTO ev VALUES (?,?,?,?,?)", good)
        out = RAW / "events" / f"file={path.stem}"
        out.mkdir(parents=True, exist_ok=True)
        duck.execute(f"""COPY (SELECT *, '{path.name}' AS _source_file, current_timestamp AS _ingested_at FROM ev)
                         TO '{(out / 'part-0.parquet').as_posix()}' (FORMAT parquet)""")
        done.add(path.name)
        state["event_files"] = sorted(done)
        save_state(state)
        log("p07", f"events {path.name}", rows=len(good), dead_letter=len(bad))


if __name__ == "__main__":
    need(SOURCE_DB, "p05_source_system.py")
    src = sqlite3.connect(SOURCE_DB)
    duck = duckdb.connect()
    state = load_state()
    ingest_tables(src, duck, state)
    ingest_events(duck, state)
    print(f"Watermarks saved in {WATERMARKS.name}: run this again and only new changes come in.")
