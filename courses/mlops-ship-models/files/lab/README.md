# Bikecast: one model, all the way to production

The project for the inPace course "MLOps: ship and run ML and deep learning models". Bikecast predicts hourly bike
rentals in Washington D.C. from the time, the weather and recent demand.

| File | Day | What it is |
|---|---|---|
| `data/hour.csv` | | UCI Bike Sharing Dataset, hourly, 2011-2012 (Hadi Fanaee-T, CC BY 4.0) |
| `common.py` | 1 | Loading, the `last_week_avg` feature, time windows, scores |
| `p01_train.py` | 1 | A reproducible training script: time split, baseline, leak check |
| `p02_data.py` | 2 | Data validation rules and DVC-style data versions |
| `p03_experiments.py` | 3 | Experiment tracking with MLflow |
| `p04_pipeline.py` | 4 | A pipeline that reruns only what changed (`python p04_pipeline.py run`) |
| `p05_registry.py` | 5 | MLflow Model Registry: versions, aliases, a promotion gate, rollback |
| `serve.py`, `p06_serve.py` | 6 | The FastAPI service and a script that exercises it |
| `Dockerfile`, `requirements-serve.txt` | 6 | The serving image |
| `tests/`, `.github/workflows/ci.yml`, `check_quality.py`, `quality.json`, `p07_ci.py` | 7 | CI and the quality gate |
| `p08_monitor.py` | 8 | Weekly monitoring, drift, and retraining policies |
| `p09_deep_learning.py` | 9 | A PyTorch model: checkpoint, ONNX export, ONNX Runtime |

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Day 9 also needs `pip install torch onnx onnxruntime onnxscript`. Run the projects in order (project 6 serves the
champion that project 5 registers): `python p01_train.py`, and so on. See runs and models with
`mlflow ui --backend-store-uri sqlite:///mlflow.db`.
