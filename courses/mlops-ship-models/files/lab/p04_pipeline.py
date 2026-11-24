"""Project 4: a training pipeline that reruns only what changed.

Run the demonstration with `python p04_pipeline.py`, or only the pipeline with `python p04_pipeline.py run`.

Steps: validate -> features -> train -> evaluate. Each step declares its inputs, settings and outputs. Before
running a step, the pipeline hashes all of them together with the step's own code; if that key matches the last run
and the outputs exist, the step is skipped. This is what DVC, Make, Airflow's caching and Kubeflow do for you."""
import hashlib
import inspect
import json
import pickle
import time
from pathlib import Path

import pandas as pd

from common import DATA, FEATURES, HERE, TARGET, add_history, between, score
from p01_train import SETTINGS, baseline, make_model
from p02_data import validate

OUT = HERE / "pipeline_out"
STATE = OUT / "state.json"
PARAMS = HERE / "params.json"


def h(*parts):
    m = hashlib.sha256()
    for p in parts:
        m.update(p if isinstance(p, bytes) else json.dumps(p, sort_keys=True, default=str).encode())
    return m.hexdigest()[:12]


def step_validate(raw, out, params):
    df = pd.read_csv(raw)
    problems = validate(df)
    if problems:
        raise SystemExit(f"Stopped at validate: {problems}")
    df.to_pickle(out)


def step_features(clean, out, params):
    df = pd.read_pickle(clean)
    df["dteday"] = pd.to_datetime(df["dteday"])
    df["time"] = df["dteday"] + pd.to_timedelta(df["hr"], unit="h")
    add_history(df).to_pickle(out)


def step_train(features, out, params):
    df = pd.read_pickle(features)
    tr = between(df, params["train_start"], params["train_end"])
    model = make_model(params).fit(tr[FEATURES], tr[TARGET])
    pickle.dump(model, open(out, "wb"))


def step_evaluate(features, model, out, params):
    df = pd.read_pickle(features)
    tr = between(df, params["train_start"], params["train_end"])
    va = between(df, params["train_end"], params["valid_end"])
    m = pickle.load(open(model, "rb"))
    report = {"model": score(va[TARGET], m.predict(va[FEATURES])), "baseline": score(va[TARGET], baseline(tr)(va)),
              "rows": len(va)}
    Path(out).write_text(json.dumps(report, indent=1))


# name: (function, input files, output file, which settings it uses)
STEPS = {
    "validate": (step_validate, [DATA], OUT / "clean.pkl", []),
    "features": (step_features, [OUT / "clean.pkl"], OUT / "features.pkl", []),
    "train": (step_train, [OUT / "features.pkl"], OUT / "model.pkl",
              ["train_start", "train_end", "max_iter", "learning_rate", "max_leaf_nodes", "seed"]),
    "evaluate": (step_evaluate, [OUT / "features.pkl", OUT / "model.pkl"], OUT / "metrics.json",
                 ["train_start", "train_end", "valid_end"]),
}


def run_pipeline(verbose=True):
    OUT.mkdir(exist_ok=True)
    params = {**SETTINGS, **(json.loads(PARAMS.read_text()) if PARAMS.exists() else {})}
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    log = []
    for name, (fn, inputs, output, keys) in STEPS.items():
        used = {k: params[k] for k in keys}
        key = h(inspect.getsource(fn), used, *[Path(i).read_bytes() for i in inputs])
        if state.get(name) == key and output.exists():
            log.append(f"{name}: skipped")
            continue
        t = time.perf_counter()
        fn(*inputs, output, used)
        state[name] = key
        STATE.write_text(json.dumps(state, indent=1))
        log.append(f"{name}: ran ({time.perf_counter() - t:.1f} s)")
    if verbose:
        print("   " + " | ".join(log))
    return json.loads((OUT / "metrics.json").read_text())


if __name__ == "__main__":
    import shutil
    import sys
    if sys.argv[1:] == ["run"]:                  # what CI runs: the pipeline with your params.json, no demo
        m = run_pipeline()
        print(f"   MAE {m['model']['mae']:.1f} (baseline {m['baseline']['mae']:.1f})")
        raise SystemExit
    shutil.rmtree(OUT, ignore_errors=True)       # a clean start for the demonstration
    PARAMS.unlink(missing_ok=True)

    print("1. First run: everything runs")
    m = run_pipeline()
    print(f"   MAE {m['model']['mae']:.1f} (baseline {m['baseline']['mae']:.1f})")
    print("2. Run again, nothing changed")
    run_pipeline()
    print("3. Change a training setting in params.json")
    PARAMS.write_text(json.dumps({"learning_rate": 0.03, "max_leaf_nodes": 63}))
    m = run_pipeline()
    print(f"   MAE {m['model']['mae']:.1f}")
    print("4. Change only the validation window: training is reused")
    PARAMS.write_text(json.dumps({"learning_rate": 0.03, "max_leaf_nodes": 63, "valid_end": "2012-04-01"}))
    m = run_pipeline()
    print(f"   MAE {m['model']['mae']:.1f} on {m['rows']:,} hours")
    print("5. A bad file arrives")
    backup = DATA.read_bytes()
    df = pd.read_csv(DATA)
    df.loc[0, "temp"] = 30.0
    df.to_csv(DATA, index=False)
    try:
        run_pipeline()
    except SystemExit as e:
        print(f"   {e}")
    finally:
        DATA.write_bytes(backup)
    print(f"   data restored; the model from step 4 is still in {OUT.name}/model.pkl, untouched")
