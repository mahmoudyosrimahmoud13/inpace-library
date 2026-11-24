"""Shared paths and small helpers for the Inkwell Books projects.

Every project script imports this file. All data lives in one folder, inkwell_data/, next to the scripts,
so you can delete that folder at any time and start again from project 5.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # Windows consoles: never crash on a symbol
except (AttributeError, ValueError):
    pass

HERE = Path(__file__).resolve().parent
DATA = HERE / "inkwell_data"
SOURCE_DB = DATA / "source" / "shop.db"          # the shop's application database (OLTP), project 5
EVENTS = DATA / "source" / "events"               # the website's click events, one JSON line each, project 5
LAKE = DATA / "lake"                              # raw files, landed by ingestion, projects 6 and 7
WAREHOUSE = DATA / "warehouse.duckdb"             # the analytics database, projects 8 to 12
SERVE = DATA / "serve"                            # what we hand to people and tools, project 11
STATE = DATA / "state"                            # bookmarks ("watermarks") that ingestion remembers, project 7
LOGS = DATA / "logs"


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(step: str, message: str, quiet: bool = False, **numbers) -> None:
    """Print a line and keep it in logs/runs.jsonl, so every run leaves a trace you can look at later."""
    LOGS.mkdir(parents=True, exist_ok=True)
    row = {"at": now_utc(), "step": step, "message": message, **numbers}
    with open(LOGS / "runs.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    if quiet:
        return
    extra = "  ".join(f"{k}={v}" for k, v in numbers.items())
    print(f"[{step}] {message}" + (f"  {extra}" if extra else ""))


def need(path: Path, made_by: str) -> None:
    """Stop with a clear message when an earlier project hasn't been run yet."""
    if not path.exists():
        raise SystemExit(f"Missing {path.relative_to(HERE)}. Run {made_by} first.")


class Timer:
    def __enter__(self):
        self.start = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.ms = (time.perf_counter() - self.start) * 1000
