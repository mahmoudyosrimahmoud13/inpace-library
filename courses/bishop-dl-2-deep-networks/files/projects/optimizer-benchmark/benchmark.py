"""Compare optimizers, schedules, initialization and normalization on the same network and budget (5 epochs)."""
import json
from pathlib import Path
from experiment import run

EXPERIMENTS = {
    "SGD, lr 0.01": {"opt": "sgd", "lr": 0.01},
    "SGD + momentum 0.9, lr 0.01": {"opt": "momentum", "lr": 0.01},
    "RMSProp, lr 0.001": {"opt": "rmsprop", "lr": 1e-3},
    "Adam, lr 0.001": {"opt": "adam", "lr": 1e-3},
    "Adam, lr 0.001, cosine schedule": {"opt": "adam", "lr": 1e-3, "schedule": "cosine"},
    "Adam, lr 0.01 (too big)": {"opt": "adam", "lr": 1e-2},
    "Adam, weights init std 1.0 (bad)": {"opt": "adam", "lr": 1e-3, "init_std": 1.0},
    "Adam, init std 1.0 + batch norm": {"opt": "adam", "lr": 1e-3, "init_std": 1.0, "batch_norm": True},
}
results = {}
print(f"{'experiment':36s} {'final train loss':>16s} {'val accuracy':>13s}")
for name, cfg in EXPERIMENTS.items():
    r = run(cfg)
    results[name] = r
    print(f"{name:36s} {r['final_loss']:16.3f} {r['val_acc']:13.3f}")

Path("outputs").mkdir(exist_ok=True)
Path("outputs/results.json").write_text(json.dumps(results))
print("saved outputs/results.json")
