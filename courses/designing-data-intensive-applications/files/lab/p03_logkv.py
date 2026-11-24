"""Project 3: build a log-structured key-value store with a hash index (the way Bitcask works).

Chapter 3 starts from "the world's simplest database": append every write to a file, and to read, scan the file for
the last value of the key. Writes are fast; reads get slower as the file grows. You'll build that, then fix it:

  * a HASH INDEX in memory: key -> byte offset of its latest value, so a read is one seek;
  * SEGMENTS: when a file reaches a size limit, start a new one;
  * COMPACTION: rewrite old segments keeping only the latest value of each key;
  * TOMBSTONES for deletes;
  * CRASH RECOVERY: rebuild the index by scanning the files, and use a CHECKSUM to skip a half-written last record.

Run:  python p03_logkv.py
"""
import os
import random
import shutil
import struct
import time
import zlib
from pathlib import Path

DATA = Path(__file__).resolve().parent / "lab_data" / "p03"
HEADER = struct.Struct(">IHI")          # crc32, key length, value length (value length 0xFFFFFFFF = tombstone)
TOMBSTONE = 0xFFFFFFFF


class LogKV:
    def __init__(self, folder: Path, segment_bytes: int = 64_000):
        self.folder, self.segment_bytes = folder, segment_bytes
        folder.mkdir(parents=True, exist_ok=True)
        self.index = {}                 # key -> (segment number, offset)
        self.recover()

    # ---- files ----
    def segments(self) -> list:
        return sorted(int(p.stem) for p in self.folder.glob("*.log"))

    def path(self, n: int) -> Path:
        return self.folder / f"{n:06d}.log"

    def active(self) -> int:
        segs = self.segments()
        if not segs or self.path(segs[-1]).stat().st_size >= self.segment_bytes:
            n = (segs[-1] + 1) if segs else 1
            self.path(n).touch()
            return n
        return segs[-1]

    # ---- writes: always append ----
    def _append(self, key: bytes, value) -> None:
        n = self.active()
        vlen = TOMBSTONE if value is None else len(value)
        body = key + (b"" if value is None else value)
        record = HEADER.pack(zlib.crc32(body) ^ vlen, len(key), vlen) + body
        with open(self.path(n), "ab") as f:
            offset = f.tell()
            f.write(record)
        if value is None:
            self.index.pop(key, None)
        else:
            self.index[key] = (n, offset)

    def set(self, key: str, value: str) -> None:
        self._append(key.encode(), value.encode())

    def delete(self, key: str) -> None:
        self._append(key.encode(), None)                      # a tombstone

    # ---- reads: one seek thanks to the index ----
    def get(self, key: str):
        where = self.index.get(key.encode())
        if not where:
            return None
        n, offset = where
        with open(self.path(n), "rb") as f:
            f.seek(offset)
            crc, klen, vlen = HEADER.unpack(f.read(HEADER.size))
            return f.read(klen + vlen)[klen:].decode()

    # ---- recovery: scan every segment, in order ----
    def scan(self, n: int):
        """Yield (offset, key, value or None) for every intact record; stop at the first damaged one."""
        data = self.path(n).read_bytes()
        pos = 0
        while pos + HEADER.size <= len(data):
            crc, klen, vlen = HEADER.unpack_from(data, pos)
            size = HEADER.size + klen + (0 if vlen == TOMBSTONE else vlen)
            body = data[pos + HEADER.size: pos + size]
            if len(body) != size - HEADER.size or zlib.crc32(body) ^ vlen != crc:
                return                                         # a torn write at the end: ignore it
            yield pos, body[:klen], (None if vlen == TOMBSTONE else body[klen:])
            pos += size

    def recover(self) -> None:
        self.index = {}
        for n in self.segments():
            for offset, key, value in self.scan(n):
                if value is None:
                    self.index.pop(key, None)
                else:
                    self.index[key] = (n, offset)

    # ---- compaction: keep only the latest value of each key ----
    def compact(self) -> tuple:
        segs = self.segments()
        old, keep_active = segs[:-1], segs[-1]
        if not old:
            return 0, 0
        before = sum(self.path(n).stat().st_size for n in old)
        live = {}
        for n in old:
            for offset, key, value in self.scan(n):
                live[key] = value                              # later records win
        merged = self.folder / "merged.tmp"
        with open(merged, "wb") as f:
            for key, value in live.items():
                if value is None or self.index.get(key, (None,))[0] not in old:
                    continue                                   # deleted, or a newer value lives in the active segment
                body = key + value
                f.write(HEADER.pack(zlib.crc32(body) ^ len(value), len(key), len(value)) + body)
        for n in old:
            self.path(n).unlink()
        merged.replace(self.path(0))                           # the compacted segment takes number 0
        self.recover()
        return before, self.path(0).stat().st_size


def simplest_get(folder: Path, key: str):
    """The world's simplest database's read: scan everything, keep the last match."""
    found = None
    for p in sorted(folder.glob("*.log")):
        data = p.read_bytes()
        pos = 0
        while pos + HEADER.size <= len(data):
            crc, klen, vlen = HEADER.unpack_from(data, pos)
            body_len = klen + (0 if vlen == TOMBSTONE else vlen)
            k = data[pos + HEADER.size: pos + HEADER.size + klen]
            if k == key.encode():
                found = None if vlen == TOMBSTONE else data[pos + HEADER.size + klen: pos + HEADER.size + body_len].decode()
            pos += HEADER.size + body_len
    return found


if __name__ == "__main__":
    shutil.rmtree(DATA, ignore_errors=True)
    rnd = random.Random(3)
    db = LogKV(DATA)

    # A video site counts plays: few keys, many updates (the book's example workload for Bitcask).
    keys = [f"video:{i}" for i in range(500)]
    for i in range(20_000):
        db.set(rnd.choice(keys), str(rnd.randint(1, 10_000)))
    db.delete("video:7")
    segs = db.segments()
    total = sum(db.path(n).stat().st_size for n in segs)
    print(f"20,000 writes over 500 keys -> {len(segs)} segment files, {total / 1e3:.0f} KB, {len(db.index)} live keys")

    t0 = time.perf_counter()
    for k in keys[:200]:
        simplest_get(DATA, k)
    scan_ms = (time.perf_counter() - t0) * 1000 / 200
    t0 = time.perf_counter()
    for k in keys[:200]:
        db.get(k)
    index_ms = (time.perf_counter() - t0) * 1000 / 200
    print(f"read by scanning the log: {scan_ms:7.3f} ms per key")
    print(f"read with the hash index: {index_ms:7.3f} ms per key  ({scan_ms / index_ms:.0f}x faster)")
    assert all(simplest_get(DATA, k) == db.get(k) for k in keys), "index and scan must agree"
    print("video:7 after delete:", db.get("video:7"))

    snapshot = {k: db.get(k) for k in keys}
    before, after = db.compact()
    assert snapshot == {k: db.get(k) for k in keys}, "compaction must not change any value"
    print(f"compaction: old segments {before / 1e3:.0f} KB -> {after / 1e3:.0f} KB; "
          f"now {len(db.segments())} segment files, every value unchanged")

    # Crash in the middle of a write: append half a record by hand.
    db.set("video:1", "42")
    with open(db.path(db.segments()[-1]), "ab") as f:
        f.write(HEADER.pack(123, 9, 4) + b"video")                # header and part of the key, then "power cut"
    restarted = LogKV(DATA)                                       # a new process: index rebuilt from the files
    print("after a crash mid-write and a restart: video:1 =", restarted.get("video:1"),
          f"| {len(restarted.index)} keys recovered | the torn record was skipped by its checksum")
