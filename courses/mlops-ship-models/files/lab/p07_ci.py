"""Project 7: continuous integration. Read the steps from .github/workflows/ci.yml and run them here, the way
GitHub Actions will on every push. Then make a bad change and watch the gate stop it."""
import json
import subprocess
import sys
import time
from pathlib import Path

import yaml

HERE = Path(__file__).parent


def run_ci():
    wf = yaml.safe_load((HERE / ".github/workflows/ci.yml").read_text())
    steps = [s for s in wf["jobs"]["test-train-gate"]["steps"] if "run" in s and not s["run"].startswith("pip")]
    for s in steps:
        t = time.perf_counter()
        cmd = s["run"].replace("python ", sys.executable + " ", 1).replace("pytest", f"{sys.executable} -m pytest", 1)
        p = subprocess.run(cmd, shell=True, cwd=HERE, capture_output=True, text=True)
        last = [l for l in (p.stdout + p.stderr).strip().splitlines() if l.strip()]
        gate = s["name"] == "Quality gate"
        print(f"   {'ok  ' if p.returncode == 0 else 'FAIL'} {s['name']:28} {time.perf_counter() - t:5.1f} s   "
              f"{'' if gate else (last[-1].strip() if last else '')}")
        if gate:
            for line in last:
                print(f"{'':10}{line}")
        if p.returncode:
            return False
    return True


if __name__ == "__main__":
    params = HERE / "params.json"
    print("1. The pipeline on the current code and settings:")
    params.unlink(missing_ok=True)
    print(f"   => {'merge allowed' if run_ci() else 'BLOCKED'}\n")

    print("2. Someone 'speeds up training' with max_iter = 15 in params.json:")
    params.write_text(json.dumps({"max_iter": 15}))
    print(f"   => {'merge allowed' if run_ci() else 'BLOCKED'}")
    params.unlink()
