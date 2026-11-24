"""Project 12: security and privacy for Inkwell's data.

1. LEAST PRIVILEGE: analysts get their own database file, analyst.duckdb, with only what they need. No emails,
   no names. Customers appear under a pseudonym: an HMAC of the email with a secret key, so the same person always
   gets the same pseudonym, but nobody without the key can turn it back into an email.
2. SECRETS stay out of code: the key comes from the environment variable INKWELL_PII_KEY.
3. A PII CHECK runs before anything is handed over, and fails the run if a column looks personal.
4. BACKUPS that are tested: export the warehouse, restore it into an empty database, compare every table.

Run:  python p12_secure.py
      (Windows PowerShell:  $env:INKWELL_PII_KEY = "a-long-random-secret";  macOS/Linux:  export INKWELL_PII_KEY=...)
"""
import hashlib
import hmac
import os
import shutil
from datetime import datetime

import duckdb

from common import DATA, WAREHOUSE, log, need

ANALYST_DB = DATA / "analyst.duckdb"
BACKUPS = DATA / "backups"
PII_WORDS = ("email", "name", "phone", "address")


def pseudonym(email: str, key: bytes) -> str:
    return hmac.new(key, email.lower().encode(), hashlib.sha256).hexdigest()[:16]


if __name__ == "__main__":
    need(WAREHOUSE, "p10_transform.py")
    key = os.environ.get("INKWELL_PII_KEY")
    if not key:
        key = "dev-only-key"
        print("WARNING: INKWELL_PII_KEY isn't set, using a development key. Never do this with real data.")
    key = key.encode()

    wh = duckdb.connect(str(WAREHOUSE), read_only=True)
    customers = wh.execute("SELECT customer_key, email FROM dim_customer").fetchall()

    # ---- 1. The analyst's database: copy only safe columns -----------------------------------------------------
    if ANALYST_DB.exists():
        ANALYST_DB.unlink()
    an = duckdb.connect(str(ANALYST_DB))
    an.execute("CREATE TABLE customer_map (customer_key BIGINT, customer_pseudonym VARCHAR)")
    an.executemany("INSERT INTO customer_map VALUES (?, ?)", [(k, pseudonym(e, key)) for k, e in customers])
    an.execute(f"ATTACH '{WAREHOUSE.as_posix()}' AS wh (READ_ONLY)")
    an.execute("""CREATE TABLE sales AS
        SELECT f.order_id, m.customer_pseudonym, c.city, b.genre, b.title, f.date_key, f.status, f.qty, f.amount
        FROM wh.fct_sales f JOIN wh.dim_customer c USING (customer_key) JOIN wh.dim_book b USING (book_key)
        JOIN customer_map m USING (customer_key)""")
    an.execute("CREATE TABLE daily_sales AS SELECT * FROM wh.mart_daily_sales")
    an.execute("DROP TABLE customer_map")       # the map links pseudonyms to keys: analysts don't need it
    an.execute("DETACH wh")

    # ---- 3. PII check on everything we hand over --------------------------------------------------------------
    cols = an.execute("SELECT table_name, column_name FROM information_schema.columns").fetchall()
    leaks = [f"{t}.{c}" for t, c in cols if any(w in c.lower() for w in PII_WORDS) and c != "customer_pseudonym"]
    values = an.execute("SELECT count(*) FROM sales WHERE city LIKE '%@%' OR title LIKE '%@%'").fetchone()[0]
    an.close()
    if leaks or values:
        ANALYST_DB.unlink()
        raise SystemExit(f"PII check FAILED, nothing handed over: {leaks or str(values) + ' values with @'}")
    print(f"analyst.duckdb ready: {len(cols)} columns, no personal data (PII check passed)")

    # ---- 4. Backup, then prove it restores --------------------------------------------------------------------
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]       # to the millisecond: two runs never collide
    target = BACKUPS / stamp
    BACKUPS.mkdir(parents=True, exist_ok=True)
    wh.execute(f"EXPORT DATABASE '{target.as_posix()}' (FORMAT parquet)")
    tables = [r[0] for r in wh.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'main' AND table_type = 'BASE TABLE'").fetchall()]
    restored = duckdb.connect()                 # an empty database in memory
    restored.execute(f"IMPORT DATABASE '{target.as_posix()}'")
    mismatches = [t for t in tables if wh.execute(f"SELECT count(*) FROM {t}").fetchone()
                  != restored.execute(f"SELECT count(*) FROM {t}").fetchone()]
    if mismatches:
        raise SystemExit(f"Backup restore test FAILED for {mismatches}")
    print(f"Backup {stamp}: {len(tables)} tables exported and restored with the same row counts")

    old = sorted(p for p in BACKUPS.iterdir() if p.is_dir())[:-7]   # retention: keep the last 7 backups
    for p in old:
        shutil.rmtree(p)
    log("p12", "secured", analyst_columns=len(cols), backup=stamp, tables=len(tables), deleted_old_backups=len(old))
