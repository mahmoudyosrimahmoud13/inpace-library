"""Capstone: run Inkwell's whole pipeline with a tiny orchestrator, the way Airflow, Dagster or Prefect would.

Each step is a task with the tasks it depends on. The orchestrator:
  * runs the tasks in dependency order (a DAG);
  * retries a failed task, waiting a little longer each time;
  * skips everything downstream of a task that still fails, so no report is built on broken data;
  * writes one line per run to logs/pipeline_runs.jsonl, and exits with an error code a scheduler can see.

Run once:          python run_all.py
Run every night:   Windows Task Scheduler, or on macOS/Linux a cron line such as
                   0 2 * * *  cd /path/to/inkwell && python run_all.py
"""
import json
import subprocess
import sys
import time
from graphlib import TopologicalSorter

from common import HERE, LOGS, now_utc

TASKS = {
    # name:        (command,                                       depends on)
    "generate":    (["p05_source_system.py", "--days", "1"],       []),
    "ingest":      (["p07_ingest.py"],                             ["generate"]),
    "transform":   (["p10_transform.py"],                          ["ingest"]),
    "serve":       (["p11_serve.py"],                              ["transform"]),
    "secure":      (["p12_secure.py"],                             ["transform"]),
}
RETRIES = 2


def run_task(name: str, args: list) -> bool:
    for attempt in range(1, RETRIES + 2):
        started = time.perf_counter()
        result = subprocess.run([sys.executable, *args], cwd=HERE, capture_output=True, text=True)
        took = time.perf_counter() - started
        if result.returncode == 0:
            print(f"  OK    {name:10} {took:5.1f} s" + (f"  (attempt {attempt})" if attempt > 1 else ""))
            return True
        print(f"  FAIL  {name:10} attempt {attempt}: {(result.stderr or result.stdout).strip().splitlines()[-1:]}")
        if attempt <= RETRIES:
            time.sleep(2 ** attempt)              # backoff: 2 s, then 4 s
    return False


if __name__ == "__main__":
    run = {"started": now_utc(), "tasks": {}}
    failed = set()
    print(f"Pipeline run {run['started']}")
    for name in TopologicalSorter({n: deps for n, (_, deps) in TASKS.items()}).static_order():
        args, deps = TASKS[name]
        if any(d in failed for d in deps):
            print(f"  SKIP  {name:10} (an upstream task failed)")
            run["tasks"][name] = "skipped"
            failed.add(name)
            continue
        ok = run_task(name, args)
        run["tasks"][name] = "ok" if ok else "failed"
        if not ok:
            failed.add(name)
    run["finished"] = now_utc()
    run["status"] = "failed" if failed else "ok"
    LOGS.mkdir(parents=True, exist_ok=True)
    with open(LOGS / "pipeline_runs.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(run) + "\n")
    print(f"Run {run['status'].upper()}")
    sys.exit(1 if failed else 0)
