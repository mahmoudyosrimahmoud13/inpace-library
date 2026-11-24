"""Project 6: the same data in four storage formats, and what that choice costs you.

Inkwell's real history is small, so we first make a bigger "five years of sales" table (simulated, 1 million order
lines by default) from the shape of the real data. Then we save it as:

  CSV            row-based text, what most exports give you
  JSON lines     row-based text with the column names repeated on every line
  Parquet        columnar and binary, with three compression codecs: snappy, gzip and zstd

and measure the file size and how long one typical analytics question takes on each.
Finally we write the data as a PARTITIONED lake (one folder per month) and see a query skip the folders it
doesn't need.

Run:  python p06_storage.py              (1,000,000 rows, needs about 300 MB of free disk for a minute)
      python p06_storage.py --rows 200000
"""
import argparse
import shutil

import duckdb

from common import DATA, Timer, log

OUT = DATA / "p06"
QUESTION = "SELECT genre, round(sum(qty * unit_price), 2) AS revenue FROM {src} GROUP BY genre ORDER BY revenue DESC"


def make_history(con, rows: int) -> None:
    con.execute(f"""
        CREATE OR REPLACE TABLE history AS
        SELECT i AS line_id,
               DATE '2021-01-01' + CAST(floor(random() * 1826) AS INTEGER) AS order_date,
               1 + CAST(floor(random() * 5000) AS INTEGER) AS customer_id,
               ['Sci-fi','Classic','Fiction','Fantasy','Tech','History','Self-help'][1 + CAST(floor(random() * 7) AS INTEGER)] AS genre,
               1 + CAST(floor(random() * 10) AS INTEGER) AS book_id,
               1 + CAST(floor(random() * 2) AS INTEGER) AS qty,
               round(8 + random() * 37, 2) AS unit_price,
               ['Cairo','Alexandria','Giza','Mansoura','Aswan','Tanta'][1 + CAST(floor(random() * 6) AS INTEGER)] AS city
        FROM range({rows}) t(i)""")


def size_mb(path) -> float:
    if path.is_dir():
        return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1e6
    return path.stat().st_size / 1e6


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=1_000_000)
    rows = ap.parse_args().rows
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True)
    con = duckdb.connect()
    con.execute("SELECT setseed(0.6)")
    make_history(con, rows)

    files = {
        "CSV": (OUT / "history.csv", "(FORMAT csv, HEADER)", "read_csv_auto('{p}')"),
        "JSON lines": (OUT / "history.jsonl", "(FORMAT json)", "read_json_auto('{p}')"),
        "Parquet snappy": (OUT / "history_snappy.parquet", "(FORMAT parquet, COMPRESSION snappy)", "read_parquet('{p}')"),
        "Parquet gzip": (OUT / "history_gzip.parquet", "(FORMAT parquet, COMPRESSION gzip)", "read_parquet('{p}')"),
        "Parquet zstd": (OUT / "history_zstd.parquet", "(FORMAT parquet, COMPRESSION zstd)", "read_parquet('{p}')"),
    }
    print(f"{rows:,} order lines\n")
    print(f"{'Format':16} {'Size MB':>8} {'Write ms':>9} {'Query ms':>9}")
    for name, (path, opts, reader) in files.items():
        with Timer() as w:
            con.execute(f"COPY history TO '{path.as_posix()}' {opts}")
        src = reader.format(p=path.as_posix())
        con.execute(QUESTION.format(src=src)).fetchall()            # warm-up: the first read fills the OS cache
        with Timer() as q:
            con.execute(QUESTION.format(src=src)).fetchall()
        print(f"{name:16} {size_mb(path):8.1f} {w.ms:9.0f} {q.ms:9.0f}")
        log("p06", "format measured", quiet=True, format=name, mb=round(size_mb(path), 1), query_ms=round(q.ms))

    # A partitioned lake: one folder per year and month, like s3://inkwell-lake/history/year=2024/month=3/...
    lake = OUT / "lake_history"
    con.execute(f"""COPY (SELECT *, year(order_date) AS year, month(order_date) AS month FROM history)
                    TO '{lake.as_posix()}' (FORMAT parquet, PARTITION_BY (year, month))""")
    folders = len(list(lake.glob("year=*/month=*")))
    one_month = f"SELECT sum(qty * unit_price) FROM read_parquet('{lake.as_posix()}/*/*/*.parquet', hive_partitioning = true) WHERE year = 2024 AND month = 3"
    all_data = f"SELECT sum(qty * unit_price) FROM read_parquet('{lake.as_posix()}/*/*/*.parquet', hive_partitioning = true)"
    con.execute(one_month).fetchall()
    with Timer() as part:
        con.execute(one_month).fetchall()
    with Timer() as full:
        con.execute(all_data).fetchall()
    print(f"\nPartitioned lake: {folders} month folders, {size_mb(lake):.1f} MB")
    print(f"  one month (reads 1 folder):  {part.ms:6.0f} ms")
    print(f"  everything ({folders} folders):    {full.ms:6.0f} ms")
    plan = "\n".join(r[1] for r in con.execute("EXPLAIN " + one_month).fetchall())
    print("  The plan's file filter:", "yes" if "year" in plan and "month" in plan else "check the EXPLAIN output")

    for name in ("history.csv", "history.jsonl"):      # big and not needed again: free the disk space
        (OUT / name).unlink()
