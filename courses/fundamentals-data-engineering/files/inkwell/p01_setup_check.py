"""Project 1: check your computer is ready for the Inkwell Books projects.

Run:  python p01_setup_check.py
It checks your Python version, that DuckDB is installed, and that the data folder can be created.
"""
import sys

from common import DATA, HERE

ok = True
print(f"Python {sys.version.split()[0]}", end="  ")
if sys.version_info < (3, 9):
    print("-> too old. Install Python 3.9 or newer from python.org")
    ok = False
else:
    print("-> OK")

try:
    import duckdb
    print(f"DuckDB {duckdb.__version__}  -> OK")
    con = duckdb.connect()
    print("DuckDB answers 1 + 1 =", con.execute("SELECT 1 + 1").fetchone()[0])
except ImportError:
    print("DuckDB is missing -> run:  pip install duckdb")
    ok = False

DATA.mkdir(exist_ok=True)
probe = DATA / ".write-test"
probe.write_text("ok")
probe.unlink()
print(f"Data folder: {DATA.relative_to(HERE.parent)}  -> OK")

print("\nAll set. Next: project 2." if ok else "\nFix the lines above, then run this again.")
