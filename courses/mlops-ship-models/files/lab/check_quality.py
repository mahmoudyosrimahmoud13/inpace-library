"""The quality gate: fail the build (exit code 1) if the model the pipeline just trained isn't good enough.
The limits live in quality.json, so changing them is a reviewed change like any other."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
limits = json.loads((HERE / "quality.json").read_text())
m = json.loads((HERE / "pipeline_out" / "metrics.json").read_text())
model, base = m["model"], m["baseline"]
checks = [
    (f"MAE {model['mae']:.1f} <= {limits['max_mae']}", model["mae"] <= limits["max_mae"]),
    (f"MAE is {model['mae'] / base['mae']:.0%} of the baseline's (limit {limits['max_share_of_baseline_mae']:.0%})",
     model["mae"] <= limits["max_share_of_baseline_mae"] * base["mae"]),
    (f"|bias| {abs(model['bias']):.1f} <= {limits['max_abs_bias']}", abs(model["bias"]) <= limits["max_abs_bias"]),
]
for text, ok in checks:
    print(f"{'PASS' if ok else 'FAIL'}  {text}")
sys.exit(0 if all(ok for _, ok in checks) else 1)
