"""Project 4: build an LSM-tree: a memtable, sorted SSTable files, a sparse index, Bloom filters and compaction.

The hash index from project 3 needs every key in memory and can't do range queries. An LSM-tree fixes both:

  write -> WAL (append, for crash safety) -> MEMTABLE (in memory, kept sorted on flush)
        -> when the memtable is big: FLUSH it to an SSTable (a file sorted by key) and start a new one
  read  -> memtable, then SSTables newest to oldest; a BLOOM FILTER says "definitely not here" without reading the file,
           and a SPARSE INDEX (every 16th key) narrows the search to one small block
  COMPACTION merges SSTables (a merge sort: they're already sorted) and drops overwritten values and tombstones.

We also measure WRITE AMPLIFICATION: how many bytes hit the disk for each byte the application wrote.

Run:  python p04_lsm.py
"""
import bisect
import hashlib
import heapq
import json
import random
import shutil
from pathlib import Path

DATA = Path(__file__).resolve().parent / "lab_data" / "p04"
TOMB = "__tombstone__"


class Bloom:
    """k hash functions set k bits per key. All k bits set = 'maybe here'; any bit clear = 'definitely not'."""

    def __init__(self, bits: int = 65536, k: int = 4):
        self.bits, self.k, self.array = bits, k, bytearray(bits // 8)

    def _positions(self, key: str):
        h = hashlib.sha256(key.encode()).digest()
        return [int.from_bytes(h[i * 4:(i + 1) * 4], "big") % self.bits for i in range(self.k)]

    def add(self, key: str) -> None:
        for p in self._positions(key):
            self.array[p // 8] |= 1 << (p % 8)

    def might_contain(self, key: str) -> bool:
        return all(self.array[p // 8] & (1 << (p % 8)) for p in self._positions(key))


class SSTable:
    """One sorted file of JSON lines. In memory we keep only a sparse index and a Bloom filter."""
    EVERY = 16

    def __init__(self, path: Path):
        self.path, self.sparse_keys, self.sparse_offsets, self.bloom = path, [], [], Bloom()
        with open(path, "rb") as f:
            n = 0
            while True:
                offset = f.tell()
                line = f.readline()
                if not line:
                    break
                key = json.loads(line)[0]
                self.bloom.add(key)
                if n % self.EVERY == 0:
                    self.sparse_keys.append(key)
                    self.sparse_offsets.append(offset)
                n += 1

    @staticmethod
    def write(path: Path, items) -> int:
        """items must be sorted by key. Returns bytes written."""
        with open(path, "w", encoding="utf-8") as f:
            for key, value in items:
                f.write(json.dumps([key, value]) + "\n")
        return path.stat().st_size

    def get(self, key: str, stats: dict):
        if not self.bloom.might_contain(key):
            stats["bloom_skips"] += 1
            return None
        i = bisect.bisect_right(self.sparse_keys, key) - 1     # the block that could hold the key
        if i < 0:
            return None
        stats["file_reads"] += 1
        with open(self.path, encoding="utf-8") as f:
            f.seek(self.sparse_offsets[i])
            for _ in range(self.EVERY):
                line = f.readline()
                if not line:
                    return None
                k, v = json.loads(line)
                if k == key:
                    return v
                if k > key:
                    return None
        return None

    def items(self):
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                yield tuple(json.loads(line))


class LSM:
    def __init__(self, folder: Path, memtable_limit: int = 2000):
        self.folder, self.limit = folder, memtable_limit
        folder.mkdir(parents=True, exist_ok=True)
        self.memtable, self.tables, self.next_id = {}, [], 1
        self.stats = {"bloom_skips": 0, "file_reads": 0, "user_bytes": 0, "disk_bytes": 0}
        self.wal = open(folder / "wal.log", "a", encoding="utf-8")

    def set(self, key: str, value: str) -> None:
        line = json.dumps([key, value]) + "\n"
        self.wal.write(line)                         # 1. durable first
        self.stats["user_bytes"] += len(line)
        self.stats["disk_bytes"] += len(line)
        self.memtable[key] = value                   # 2. then in memory
        if len(self.memtable) >= self.limit:
            self.flush()

    def delete(self, key: str) -> None:
        self.set(key, TOMB)

    def flush(self) -> None:
        path = self.folder / f"sst-{self.next_id:04d}.jsonl"
        self.next_id += 1
        self.stats["disk_bytes"] += SSTable.write(path, sorted(self.memtable.items()))
        self.tables.append(SSTable(path))
        self.memtable = {}
        self.wal.close()
        self.wal = open(self.folder / "wal.log", "w", encoding="utf-8")   # flushed data no longer needs the WAL

    def get(self, key: str):
        if key in self.memtable:
            v = self.memtable[key]
        else:
            v = None
            for table in reversed(self.tables):      # newest first
                v = table.get(key, self.stats)
                if v is not None:
                    break
        return None if v == TOMB else v

    def range(self, lo: str, hi: str) -> list:
        """Keys in [lo, hi): possible because every SSTable is sorted. Newest value wins."""
        merged = {}
        for table in self.tables:                    # oldest to newest, so newer overwrite older
            for k, v in table.items():
                if lo <= k < hi:
                    merged[k] = v
        merged.update({k: v for k, v in self.memtable.items() if lo <= k < hi})
        return sorted((k, v) for k, v in merged.items() if v != TOMB)

    def compact(self) -> None:
        """Merge all SSTables into one (size-tiered style, all at once for simplicity)."""
        def tagged(table, age):                      # a function, so each stream keeps its own age
            for k, v in table.items():
                yield k, -age, v
        streams = [tagged(t, i) for i, t in enumerate(self.tables)]
        out, last = [], None
        for k, neg_age, v in heapq.merge(*streams):  # sorted by key, then newest table first
            if k == last:
                continue                             # an older value of a key we already kept
            last = k
            if v != TOMB:
                out.append((k, v))
        path = self.folder / f"sst-{self.next_id:04d}.jsonl"
        self.next_id += 1
        self.stats["disk_bytes"] += SSTable.write(path, out)
        for t in self.tables:
            t.path.unlink()
        self.tables = [SSTable(path)]


if __name__ == "__main__":
    shutil.rmtree(DATA, ignore_errors=True)
    rnd = random.Random(4)
    db = LSM(DATA)
    users = [f"user:{i:05d}" for i in range(5000)]
    truth = {}
    for _ in range(30_000):
        k = rnd.choice(users)
        v = f"last_seen={rnd.randint(1, 10**6)}"
        db.set(k, v)
        truth[k] = v
    for k in users[:50]:
        db.delete(k)
        truth.pop(k, None)
    print(f"30,000 writes, 50 deletes -> {len(db.tables)} SSTables on disk + {len(db.memtable)} keys in the memtable")

    db.stats.update(bloom_skips=0, file_reads=0)
    assert all(db.get(k) == truth.get(k) for k in users), "every read must match"
    print(f"5,000 reads: {db.stats['file_reads']:,} SSTable block reads, {db.stats['bloom_skips']:,} files skipped by "
          f"Bloom filters (a skip = no disk read)")
    missing = [f"ghost:{i}" for i in range(1000)]
    db.stats.update(bloom_skips=0, file_reads=0)
    for k in missing:
        db.get(k)
    print(f"1,000 reads of keys that don't exist: {db.stats['file_reads']} block reads "
          f"(Bloom false positives), {db.stats['bloom_skips']:,} skips")

    print("range query user:01000 .. user:01005 ->", db.range("user:01000", "user:01005"))

    amp_before = db.stats["disk_bytes"] / db.stats["user_bytes"]
    files_before = len(db.tables)
    db.compact()
    assert all(db.get(k) == truth.get(k) for k in users), "compaction must not change answers"
    amp_after = db.stats["disk_bytes"] / db.stats["user_bytes"]
    print(f"compaction: {files_before} SSTables -> 1, every answer unchanged")
    print(f"write amplification: {amp_before:.2f} bytes on disk per byte written before compaction, "
          f"{amp_after:.2f} after it")
