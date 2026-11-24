"""Project 6: serve the champion behind an HTTP API, check what comes in, and package it for Docker."""
import os
import shutil
import statistics
import time
import warnings

warnings.filterwarnings("ignore")
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
os.environ.setdefault("MLFLOW_DISABLE_TELEMETRY", "true")
os.environ.setdefault("MLFLOW_ENABLE_ARTIFACTS_PROGRESS_BAR", "false")
os.environ["PREDICTION_LOG"] = "p06_predictions.jsonl"
import mlflow
from fastapi.testclient import TestClient

from common import TARGET, between, load

if __name__ == "__main__":
    import serve
    client = TestClient(serve.app)
    print("1.", client.get("/health").json())

    hour = {"time": "2012-05-01T08:00", "weathersit": 1, "temp": 0.52, "atemp": 0.5, "hum": 0.6, "windspeed": 0.2}
    r = client.post("/predict", json=[hour])
    actual = load().set_index("time").loc["2012-05-01 08:00", TARGET]
    print(f"2. 8 am on 1 May 2012: predicted {r.json()['predictions'][0]} bikes, actually {actual}")

    bad = {**hour, "temp": 21.5, "weathersit": 7}
    r = client.post("/predict", json=[bad])
    print(f"3. Bad input -> {r.status_code}: " + "; ".join(f"{e['loc'][-1]}: {e['msg']}" for e in r.json()["detail"]))
    r = client.post("/predict", json=[{**hour, "time": "2011-01-02T08:00"}])
    print(f"   Too early for history -> {r.status_code}: {r.json()['detail']}")

    df = between(load(), "2012-05-01", "2012-05-08")
    week = [{"time": t.isoformat(), "holiday": int(h), "weathersit": int(w), "temp": a, "atemp": b, "hum": c,
             "windspeed": d} for t, h, w, a, b, c, d in
            df[["time", "holiday", "weathersit", "temp", "atemp", "hum", "windspeed"]].itertuples(index=False)]
    t = time.perf_counter()
    r = client.post("/predict", json=week)
    preds = r.json()["predictions"]
    mae = statistics.mean(abs(p - a) for p, a in zip(preds, df[TARGET]))
    print(f"4. A batch of {len(week)} hours (the first week of May) in {(time.perf_counter() - t) * 1000:.0f} ms, "
          f"MAE {mae:.1f}")

    lat = []
    for _ in range(50):
        t = time.perf_counter()
        client.post("/predict", json=[hour])
        lat.append((time.perf_counter() - t) * 1000)
    lat.sort()
    print(f"5. 50 single requests: median {lat[25]:.1f} ms, p95 {lat[47]:.1f} ms")
    n = sum(1 for _ in open("p06_predictions.jsonl"))
    print(f"6. Every prediction is logged for monitoring: {n} lines in p06_predictions.jsonl")
    os.remove("p06_predictions.jsonl")

    shutil.rmtree("model", ignore_errors=True)
    mlflow.artifacts.download_artifacts(f"models:/bikecast@champion", dst_path="model")
    print(f"7. Champion exported to ./model for the Docker image: {sorted(os.listdir('model'))}")
