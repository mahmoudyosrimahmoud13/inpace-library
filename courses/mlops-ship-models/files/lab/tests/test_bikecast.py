"""Tests that run in CI on every push. They train a small model, save it like MLflow would, and test the service
and the model's quality against the baseline."""
import os
import sys
import warnings
from pathlib import Path

import pytest

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MLFLOW_DISABLE_TELEMETRY", "true")
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")

from common import FEATURES, TARGET, between, load, score  # noqa: E402
from p01_train import SETTINGS, baseline, train  # noqa: E402
from p02_data import validate  # noqa: E402


@pytest.fixture(scope="session")
def data():
    return load()


@pytest.fixture(scope="session")
def client(tmp_path_factory, data):
    import mlflow
    from p03_experiments import TRUSTED
    model, _, _ = train(SETTINGS, data)
    path = tmp_path_factory.mktemp("m") / "model"
    mlflow.sklearn.save_model(model, path, skops_trusted_types=TRUSTED)
    os.environ.update(MODEL_URI=str(path), MODEL_VERSION="test",
                      PREDICTION_LOG=str(tmp_path_factory.mktemp("log") / "p.jsonl"))
    import serve
    from fastapi.testclient import TestClient
    return TestClient(serve.app)


HOUR = {"time": "2012-05-01T08:00", "weathersit": 1, "temp": 0.52, "atemp": 0.5, "hum": 0.6, "windspeed": 0.2}


def test_the_data_passes_its_checks(data):
    assert validate(data.drop(columns=["time", "last_week_avg"])) == []


def test_training_is_reproducible(data):
    a, _, va = train(SETTINGS, data)
    b, _, _ = train(SETTINGS, data)
    assert (a.predict(va[FEATURES]) == b.predict(va[FEATURES])).all()


def test_the_model_beats_the_baseline(data):
    model, tr, va = train(SETTINGS, data)
    assert score(va[TARGET], model.predict(va[FEATURES]))["mae"] < 0.9 * score(va[TARGET], baseline(tr)(va))["mae"]


def test_serving_features_match_training_features(client, data):
    """Training/serving skew: the service must compute exactly what training saw."""
    import serve
    from serve import Hour
    row = data.set_index("time").loc["2012-05-01 08:00"]
    got = serve.features([Hour(**{**HOUR, "holiday": int(row["holiday"]), "weathersit": int(row["weathersit"]),
                                  "temp": row["temp"], "atemp": row["atemp"], "hum": row["hum"],
                                  "windspeed": row["windspeed"]})]).iloc[0]
    for f in FEATURES:
        assert got[f] == pytest.approx(row[f]), f


def test_health_and_predict(client):
    assert client.get("/health").json() == {"status": "ok", "model_version": "test"}
    r = client.post("/predict", json=[HOUR, {**HOUR, "time": "2012-05-01T03:00"}])
    night, morning = r.json()["predictions"][1], r.json()["predictions"][0]
    assert r.status_code == 200 and 0 <= night < morning


@pytest.mark.parametrize("bad", [{"temp": 21.5}, {"weathersit": 0}, {"time": "not a date"}, {"hum": None}])
def test_bad_input_is_refused(client, bad):
    assert client.post("/predict", json=[{**HOUR, **bad}]).status_code == 422


def test_batch_limits(client):
    assert client.post("/predict", json=[]).status_code == 422
    assert client.post("/predict", json=[HOUR] * 501).status_code == 422
