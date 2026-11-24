"""Project 8: how a query runs, and how to make it cheaper.

Part A uses project 6's partitioned history (run p06_storage.py first). Part B uses the events from project 7.

A1  EXPLAIN: read the plan the optimizer chose, before running anything.
A2  Column pruning: SELECT * reads every column; naming the columns you need reads less.
A3  Partition pruning: a filter on the partition columns skips whole folders.
A4  A join that multiplies rows (a key that isn't unique) and how to spot it.
B   A "streaming" style question on bounded data: purchases per 6-hour TUMBLING WINDOW by EVENT time,
    and how many events arrived late (in a later day's file than the day they happened).

Run:  python p08_queries.py
"""
import duckdb

from common import DATA, LAKE, Timer, need

LAKE_HISTORY = DATA / "p06" / "lake_history"
SRC = f"read_parquet('{LAKE_HISTORY.as_posix()}/*/*/*.parquet', hive_partitioning = true)"


def timed(con, sql: str, runs: int = 3) -> float:
    con.execute(sql).fetchall()                      # warm-up
    best = float("inf")
    for _ in range(runs):
        with Timer() as t:
            con.execute(sql).fetchall()
        best = min(best, t.ms)
    return best


if __name__ == "__main__":
    need(LAKE_HISTORY, "p06_storage.py")
    con = duckdb.connect()

    print("A1. The plan for 'revenue per city in March 2024':")
    q = f"SELECT city, sum(qty * unit_price) FROM {SRC} WHERE year = 2024 AND month = 3 GROUP BY city"
    for _, plan in con.execute("EXPLAIN " + q).fetchall():
        print("   " + plan.replace("\n", "\n   ")[:1500])

    print("\nA2. Column pruning")
    star = timed(con, f"SELECT * FROM {SRC}")
    two = timed(con, f"SELECT order_date, unit_price FROM {SRC}")
    print(f"   SELECT * (all 10 columns): {star:7.1f} ms")
    print(f"   SELECT 2 columns:          {two:7.1f} ms   -> columnar files let us skip the other 8")

    print("\nA3. Partition pruning")
    every = timed(con, f"SELECT sum(unit_price) FROM {SRC} WHERE order_date BETWEEN '2024-03-01' AND '2024-03-31'")
    pruned = timed(con, f"SELECT sum(unit_price) FROM {SRC} WHERE year = 2024 AND month = 3")
    print(f"   filter on order_date:      {every:7.1f} ms   (DuckDB may still open every folder)")
    print(f"   filter on year and month:  {pruned:7.1f} ms   (only the 2024/3 folder)")

    print("\nA4. A join that multiplies rows")
    con.execute(f"CREATE TABLE lines AS SELECT * FROM {SRC} WHERE year = 2024")
    con.execute("CREATE TABLE cities AS SELECT * FROM (VALUES ('Cairo','North'),('Cairo','Delta'),('Giza','North')) t(city, region)")
    n_lines = con.execute("SELECT count(*) FROM lines").fetchone()[0]
    n_join = con.execute("SELECT count(*) FROM lines LEFT JOIN cities USING (city)").fetchone()[0]
    print(f"   lines in 2024: {n_lines:,}   after LEFT JOIN cities: {n_join:,}   (+{n_join - n_lines:,} rows from nowhere)")
    print("   'Cairo' appears twice in cities, so every Cairo line was counted twice. Always check the row count"
          "\n   before and after a join, and make sure the key is unique on one side.")

    events = LAKE / "raw" / "events"
    need(events, "p07_ingest.py")
    ev = f"read_parquet('{events.as_posix()}/*/*.parquet')"
    print("\nB. Purchases per 6-hour tumbling window (by event time), first 8 windows:")
    rows = con.execute(f"""
        SELECT time_bucket(INTERVAL 6 HOUR, event_time) AS window_start, count(DISTINCT event_id) AS purchases
        FROM {ev} WHERE event_type = 'purchase' GROUP BY 1 ORDER BY 1 LIMIT 8""").fetchall()
    for start, n in rows:
        print(f"   {start}  {n:3d}")
    late = con.execute(f"""
        SELECT count(*) FROM {ev}
        WHERE CAST(event_time AS DATE) < CAST(replace(replace(_source_file, 'events-', ''), '.jsonl', '') AS DATE)""").fetchone()[0]
    dupes = con.execute(f"SELECT count(*) - count(DISTINCT event_id) FROM {ev}").fetchone()[0]
    print(f"   late events (arrived in a later day's file): {late}")
    print(f"   duplicate deliveries (same event_id twice):  {dupes}")
    print("   A real stream processor waits for late data with a WATERMARK, then closes the window.")
