"""Project 5: row storage versus column storage, bitmap and run-length encoding, and a data cube.

A shop's fact table: one row per sale, 8 columns, 1,000,000 rows. The analytics question (like the book's example):
"total quantity sold of products 30, 68 and 69". It needs 2 of the 8 columns.

  ROW STORE:    every row is stored whole, so the query reads all 8 columns of every row.
  COLUMN STORE: each column is its own array, so the query reads 2 columns.
  BITMAPS:      for a column with few distinct values, one bit array per value. "product IN (30, 68, 69)" is an OR
                of three bitmaps.
  SORT ORDER + RUN-LENGTH ENCODING: sorted by date, the date column becomes a few long runs: tiny.
  DATA CUBE:    precompute sums by (date, product) once; the question becomes a lookup in a small table.

Run:  python p05_columns.py
"""
import random
import struct
import time
import zlib
from array import array
from collections import Counter, defaultdict

N = 1_000_000
rnd = random.Random(5)
COLS = ["date_key", "product_sk", "store_sk", "promotion_sk", "customer_sk", "quantity", "net_price", "discount"]

print(f"Making {N:,} sales...")
data = {
    "date_key":     array("i", sorted(rnd.randint(140101, 140365) for _ in range(N))),   # sorted by date
    "product_sk":   array("i", (rnd.randint(1, 200) for _ in range(N))),
    "store_sk":     array("i", (rnd.randint(1, 50) for _ in range(N))),
    "promotion_sk": array("i", (rnd.choice([0, 0, 0, 1, 2, 3]) for _ in range(N))),
    "customer_sk":  array("i", (rnd.randint(1, 100_000) for _ in range(N))),
    "quantity":     array("i", (rnd.randint(1, 5) for _ in range(N))),
    "net_price":    array("d", (round(rnd.uniform(1, 100), 2) for _ in range(N))),
    "discount":     array("d", (rnd.choice([0.0, 0.0, 0.1, 0.2]) for _ in range(N))),
}
WANTED = {30, 68, 69}

# ---- Row store: one packed record per row ----
row_fmt = struct.Struct("<iiiiiidd")
row_bytes = bytearray()
for i in range(N):
    row_bytes += row_fmt.pack(*(data[c][i] for c in COLS))
t0 = time.perf_counter()
total_row = 0
for rec in row_fmt.iter_unpack(row_bytes):        # must decode every column of every row
    if rec[1] in WANTED:
        total_row += rec[5]
row_ms = (time.perf_counter() - t0) * 1000

# ---- Column store: read only the 2 columns ----
t0 = time.perf_counter()
total_col = sum(q for p, q in zip(data["product_sk"], data["quantity"]) if p in WANTED)
col_ms = (time.perf_counter() - t0) * 1000
col_bytes = data["product_sk"].itemsize * N + data["quantity"].itemsize * N
assert total_row == total_col
print(f"\nQuantity of products 30, 68, 69: {total_col:,}")
print(f"  row store   : read {len(row_bytes) / 1e6:6.1f} MB  in {row_ms:6.0f} ms")
print(f"  column store: read {col_bytes / 1e6:6.1f} MB  in {col_ms:6.0f} ms")

# ---- Bitmaps for a low-cardinality column ----
bitmaps = defaultdict(lambda: bytearray((N + 7) // 8))
for i, p in enumerate(data["product_sk"]):
    if p in WANTED:                                # only the three we need, to keep the demo fast
        bitmaps[p][i >> 3] |= 1 << (i & 7)
combined = bytearray(a | b | c for a, b, c in zip(bitmaps[30], bitmaps[68], bitmaps[69]))
matches = sum(bin(b).count("1") for b in combined)
print(f"\nBitmap encoding: product IN (30, 68, 69) = bitwise OR of 3 bitmaps of {len(combined) / 1e3:.0f} KB each "
      f"-> {matches:,} matching rows")

# ---- Sort order and run-length encoding ----
def rle(col):
    runs, prev, n = [], col[0], 0
    for v in col:
        if v == prev:
            n += 1
        else:
            runs.append((prev, n))
            prev, n = v, 1
    runs.append((prev, n))
    return runs


date_runs = rle(data["date_key"])
prod_runs = rle(data["product_sk"])
print("\nRun-length encoding (value, how many times in a row):")
print(f"  date_key   (sorted)  : {N:,} values -> {len(date_runs):,} runs   e.g. {date_runs[:2]}")
print(f"  product_sk (unsorted): {N:,} values -> {len(prod_runs):,} runs   (almost no gain)")
for c in ("date_key", "product_sk", "customer_sk"):
    raw = data[c].tobytes()
    print(f"  zlib on {c:12}: {len(raw) / 1e3:6,.0f} KB -> {len(zlib.compress(raw, 6)) / 1e3:6,.0f} KB")

# ---- A data cube: precomputed aggregates ----
t0 = time.perf_counter()
cube = Counter()
for d, p, q in zip(data["date_key"], data["product_sk"], data["quantity"]):
    cube[(d, p)] += q
build_ms = (time.perf_counter() - t0) * 1000
t0 = time.perf_counter()
total_cube = sum(q for (d, p), q in cube.items() if p in WANTED)
cube_ms = (time.perf_counter() - t0) * 1000
assert total_cube == total_col
print(f"\nData cube by (date, product): {len(cube):,} cells instead of {N:,} rows, built once in {build_ms:.0f} ms")
print(f"  the same question from the cube: {cube_ms:.1f} ms. But a question about stores can't be answered from it.")
