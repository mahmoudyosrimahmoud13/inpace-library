"""Project 3: track every training run with MLflow, so you can compare them and get any model back later.

See the runs in a browser afterwards:  mlflow ui --backend-store-uri sqlite:///mlflow.db  (then open
http://127.0.0.1:5000)."""
import itertools
import logging
import os
import subprocess
import time
import warnings

warnings.filterwarnings("ignore", category=UserWarning)
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
os.environ.setdefault("MLFLOW_DISABLE_TELEMETRY", "true")
os.environ.setdefault("MLFLOW_ENABLE_ARTIFACTS_PROGRESS_BAR", "false")
import mlflow
from mlflow.models import infer_signature

from common import DATA, FEATURES, TARGET, load, score
from p01_train import SETTINGS, baseline, train
from p02_data import file_hash

logging.getLogger("mlflow").setLevel(logging.ERROR)
mlflow.set_tracking_uri("sqlite:///mlflow.db")
EXPERIMENT = "bikecast"
# MLflow saves scikit-learn models with skops, which refuses types that a tampered file could abuse unless you say
# you trust them. These are models you trained yourself, so this one type is trusted.
TRUSTED = ["sklearn.ensemble._hist_gradient_boosting.predictor.TreePredictor"]


def git_commit():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "not a git repository"


def run(settings, df, features=FEATURES, name=None, log_model=False):
    """One training run: settings in, scores out, everything recorded."""
    with mlflow.start_run(run_name=name):
        mlflow.log_params({**settings, "features": ",".join(features)})
        mlflow.set_tags({"data_version": file_hash(DATA), "git_commit": git_commit()})
        t = time.perf_counter()
        model, tr, va = train(settings, df, features)
        pred = model.predict(va[features])
        s = score(va[TARGET], pred)
        mlflow.log_metrics({f"valid_{k}": v for k, v in s.items()} | {"train_seconds": time.perf_counter() - t})
        if log_model:
            mlflow.sklearn.log_model(model, name="model", signature=infer_signature(va[features].head(), pred[:5]),
                                     input_example=va[features].head(3), skops_trusted_types=TRUSTED)
        return s


if __name__ == "__main__":
    df = load()
    mlflow.set_experiment(EXPERIMENT)
    tr = df[(df["time"] >= SETTINGS["train_start"]) & (df["time"] < SETTINGS["train_end"])]
    va = df[(df["time"] >= SETTINGS["train_end"]) & (df["time"] < SETTINGS["valid_end"])]
    with mlflow.start_run(run_name="baseline"):
        mlflow.log_params({"model": "mean by hour x workingday"})
        mlflow.log_metrics({f"valid_{k}": v for k, v in score(va[TARGET], baseline(tr)(va)).items()})

    t = time.perf_counter()
    grid = list(itertools.product([0.03, 0.05, 0.1], [15, 31, 63]))
    for lr, leaves in grid:
        run({**SETTINGS, "learning_rate": lr, "max_leaf_nodes": leaves}, df, name=f"lr{lr}-leaves{leaves}")
    with_calendar = FEATURES + ["mnth", "season"]
    run(SETTINGS, df, features=with_calendar, name="with month and season")
    print(f"{len(grid) + 2} runs logged in {time.perf_counter() - t:.0f} s\n")

    runs = mlflow.search_runs(experiment_names=[EXPERIMENT], order_by=["metrics.valid_mae ASC"])
    cols = ["tags.mlflow.runName", "metrics.valid_mae", "metrics.valid_rmse", "metrics.valid_bias"]
    table = runs[cols].rename(columns=lambda c: c.split(".")[-1].replace("mlflow.", ""))
    print(table.head(12).to_string(index=False, float_format=lambda x: f"{x:7.1f}"))

    best = runs.iloc[0]
    print(f"\nBest: {best['tags.mlflow.runName']}, data version {best['tags.data_version']}, "
          f"code {best['tags.git_commit']}")
    s = {k: best[f"params.{k}"] for k in ["learning_rate", "max_leaf_nodes", "max_iter"]}
    final = run({**SETTINGS, "learning_rate": float(s["learning_rate"]), "max_leaf_nodes": int(s["max_leaf_nodes"])},
                df, name="best, with model", log_model=True)
    last = mlflow.search_runs(experiment_names=[EXPERIMENT], order_by=["start_time DESC"], max_results=1).iloc[0]
    model = mlflow.sklearn.load_model(f"runs:/{last['run_id']}/model")
    print(f"Logged the model, loaded it back by run id: MAE {score(va[TARGET], model.predict(va[FEATURES]))['mae']:.1f}"
          f" (same as {final['mae']:.1f})")
