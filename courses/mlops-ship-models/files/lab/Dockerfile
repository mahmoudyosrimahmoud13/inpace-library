# Bikecast's prediction service. Build after `python p06_serve.py` has exported the champion to ./model:
#   docker build -t bikecast:2 --build-arg MODEL_VERSION=2 .
#   docker run --rm -p 8000:8000 bikecast:2
FROM python:3.12-slim

WORKDIR /app
COPY requirements-serve.txt .
RUN pip install --no-cache-dir -r requirements-serve.txt

# The code, the history of counts for last_week_avg, and one fixed model: the image never changes after it's built.
COPY common.py serve.py ./
COPY data/hour.csv data/hour.csv
COPY model/ model/

ARG MODEL_VERSION=unknown
ENV MODEL_URI=/app/model MODEL_VERSION=${MODEL_VERSION} PREDICTION_LOG=/tmp/predictions.jsonl \
    MLFLOW_DISABLE_TELEMETRY=true PYTHONUNBUFFERED=1

# Don't run as root inside the container.
RUN useradd --create-home app
USER app

EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
CMD ["uvicorn", "serve:app", "--host", "0.0.0.0", "--port", "8000"]
