"""Project 5: a model registry with a quality gate. Models get version numbers; an alias ("champion") points to
the one in production; a new model replaces it only if it wins on the same recent data. Rollback is moving the alias
back."""
import os
import warnings

warnings.filterwarnings("ignore", category=UserWarning)
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
os.environ.setdefault("MLFLOW_DISABLE_TELEMETRY", "true")
os.environ.setdefault("MLFLOW_ENABLE_ARTIFACTS_PROGRESS_BAR", "false")
import logging

import mlflow
from mlflow import MlflowClient
from mlflow.models import infer_signature

from common import FEATURES, TARGET, between, load, score
from p01_train import SETTINGS, make_model
from p03_experiments import TRUSTED

logging.getLogger("mlflow").setLevel(logging.ERROR)
mlflow.set_tracking_uri("sqlite:///mlflow.db")
mlflow.set_experiment("bikecast-registry")
NAME = "bikecast"
client = MlflowClient()


def train_and_register(settings, df, note, features=FEATURES):
    """Train, log and register a new version. It gets no alias: being registered isn't being in production."""
    tr = between(df, settings["train_start"], settings["train_end"])
    model = make_model(settings).fit(tr[features], tr[TARGET])
    with mlflow.start_run(run_name=note):
        mlflow.log_params(settings)
        info = mlflow.sklearn.log_model(model, name="model", registered_model_name=NAME,
                                        signature=infer_signature(tr[features].head(), model.predict(tr[features].head())),
                                        skops_trusted_types=TRUSTED)
    v = info.registered_model_version
    client.update_model_version(NAME, v, description=note)
    return v


def gate(candidate, df, window, min_gain=0.02):
    """The challenger must beat the champion by at least 2% MAE on the same recent hours, and be no more biased."""
    test = between(df, *window)
    champ = mlflow.sklearn.load_model(f"models:/{NAME}@champion")
    chall = mlflow.sklearn.load_model(f"models:/{NAME}/{candidate}")
    a, b = score(test[TARGET], champ.predict(test[FEATURES])), score(test[TARGET], chall.predict(test[FEATURES]))
    ok = b["mae"] <= a["mae"] * (1 - min_gain) and abs(b["bias"]) <= abs(a["bias"])
    return ok, a, b


def promote(version):
    old = client.get_model_version_by_alias(NAME, "champion").version
    client.set_registered_model_alias(NAME, "previous", old)
    client.set_registered_model_alias(NAME, "champion", version)


if __name__ == "__main__":
    try:
        client.delete_registered_model(NAME)        # a clean start for the demonstration
    except mlflow.exceptions.MlflowException:
        pass
    df = load()
    window = ("2012-04-01", "2012-05-01")           # recent hours that no model trained on

    v1 = train_and_register(SETTINGS, df, "trained on 2011")
    client.set_registered_model_alias(NAME, "champion", v1)
    print(f"1. Version {v1} registered and made champion")

    v2 = train_and_register({**SETTINGS, "train_end": "2012-04-01"}, df, "trained up to April 2012")
    ok, a, b = gate(v2, df, window)
    print(f"2. Version {v2}, trained on three more months: champion MAE {a['mae']:.1f}, challenger {b['mae']:.1f}, "
          f"bias {b['bias']:+.1f} -> {'PROMOTE' if ok else 'REJECT'}")
    if ok:
        promote(v2)

    v3 = train_and_register({**SETTINGS, "train_end": "2012-04-01", "max_iter": 20}, df, "a rushed model: 20 trees")
    ok, a, b = gate(v3, df, window)
    print(f"3. Version {v3}, only 20 trees: champion MAE {a['mae']:.1f}, challenger {b['mae']:.1f}, "
          f"bias {b['bias']:+.1f} -> {'PROMOTE' if ok else 'REJECT'}")

    print("\n   The registry now:")
    for mv in sorted(client.search_model_versions(f"name='{NAME}'"), key=lambda m: int(m.version)):
        aliases = ", ".join(client.get_model_version(NAME, mv.version).aliases) or "-"
        print(f"   version {mv.version}: {mv.description:28} aliases: {aliases}")

    champ = client.get_model_version_by_alias(NAME, "champion")
    print(f"\n4. Production loads 'models:/{NAME}@champion' -> version {champ.version}. Code never names a version.")
    client.set_registered_model_alias(NAME, "champion", client.get_model_version_by_alias(NAME, "previous").version)
    print(f"5. Something's wrong in production? Roll back: champion -> version "
          f"{client.get_model_version_by_alias(NAME, 'champion').version}, one call, no redeploy")
    client.set_registered_model_alias(NAME, "champion", champ.version)
    print(f"   (and forward again to version {champ.version})")
