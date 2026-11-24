"""Bikecast's prediction service. Run it with:  uvicorn serve:app --port 8000

It loads the model from MODEL_URI (by default the registry's champion), computes the same features as training
with the same code, checks every request, and logs every prediction for monitoring."""
import json
import os
import time
import warnings
from datetime import datetime
from pathlib import Path

warnings.filterwarnings("ignore", category=UserWarning)
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
os.environ.setdefault("MLFLOW_DISABLE_TELEMETRY", "true")
import mlflow
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from common import DATA, FEATURES, TARGET, load

MODEL_URI = os.environ.get("MODEL_URI", "models:/bikecast@champion")
HISTORY = os.environ.get("HISTORY_CSV", str(DATA))       # observed counts, for last_week_avg
LOG = Path(os.environ.get("PREDICTION_LOG", "predictions.jsonl"))

mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "sqlite:///mlflow.db"))
model = mlflow.sklearn.load_model(MODEL_URI)
counts = load(HISTORY).set_index("time")[TARGET]
VERSION = str(os.environ.get("MODEL_VERSION") or (
    mlflow.MlflowClient().get_model_version_by_alias("bikecast", "champion").version
    if MODEL_URI.startswith("models:/") else Path(MODEL_URI).name))
app = FastAPI(title="Bikecast", version="1.0")


class Hour(BaseModel):
    """One hour to predict. Weather values are normalized like the training data (0 to 1)."""
    time: datetime
    holiday: int = Field(0, ge=0, le=1)
    weathersit: int = Field(ge=1, le=4, description="1 clear, 2 mist, 3 light rain or snow, 4 heavy rain")
    temp: float = Field(ge=0, le=1)
    atemp: float = Field(ge=0, le=1)
    hum: float = Field(ge=0, le=1)
    windspeed: float = Field(ge=0, le=1)


def features(hours: list[Hour]) -> pd.DataFrame:
    """The same features as training. weekday uses the data's convention (0 = Sunday)."""
    rows = []
    for h in hours:
        t = pd.Timestamp(h.time).floor("h")
        past = counts[(counts.index >= t - pd.Timedelta(days=7)) & (counts.index < t)]
        if len(past) < 100:
            raise HTTPException(422, f"Not enough history before {t} to compute last_week_avg")
        weekday = (t.dayofweek + 1) % 7
        rows.append({"hr": t.hour, "weekday": weekday, "workingday": int(weekday not in (0, 6) and not h.holiday),
                     "holiday": h.holiday, "weathersit": h.weathersit, "temp": h.temp, "atemp": h.atemp,
                     "hum": h.hum, "windspeed": h.windspeed, "last_week_avg": float(past.mean())})
    return pd.DataFrame(rows)[FEATURES]


@app.get("/health")
def health():
    return {"status": "ok", "model_version": VERSION}


@app.post("/predict")
def predict(hours: list[Hour]):
    if not 1 <= len(hours) <= 500:
        raise HTTPException(422, "Send between 1 and 500 hours")
    t = time.perf_counter()
    X = features(hours)
    preds = [max(0, round(float(p))) for p in model.predict(X)]
    with LOG.open("a") as f:
        for h, x, p in zip(hours, X.to_dict("records"), preds):
            f.write(json.dumps({"time": h.time.isoformat(), "model_version": VERSION, "prediction": p, **x}) + "\n")
    return {"model_version": VERSION, "predictions": preds, "ms": round((time.perf_counter() - t) * 1000, 1)}
