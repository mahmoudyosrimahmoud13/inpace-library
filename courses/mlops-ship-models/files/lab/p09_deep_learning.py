"""Project 9: the same MLOps steps for a deep learning model. Train a small PyTorch network on Bikecast's features,
save a checkpoint that's complete (weights AND preprocessing AND settings), export it to ONNX, check the export gives
the same numbers, and serve it with ONNX Runtime, without PyTorch.

Needs: pip install torch onnx onnxruntime onnxscript"""
import hashlib
import json
import time
import warnings

import numpy as np
import torch
from torch import nn

from common import DATA, FEATURES, TARGET, between, load, score
from p01_train import SETTINGS

warnings.filterwarnings("ignore")
torch.manual_seed(0)
torch.set_num_threads(2)
CONFIG = {"hidden": 64, "layers": 2, "lr": 3e-3, "epochs": 300, "batch": 256, "patience": 8}


class Net(nn.Module):
    """Normalization is part of the model, so whoever loads it can't forget it (a classic serving bug)."""

    def __init__(self, mean, std, hidden, layers):
        super().__init__()
        self.register_buffer("mean", torch.tensor(mean, dtype=torch.float32))
        self.register_buffer("std", torch.tensor(std, dtype=torch.float32))
        blocks, width = [], len(mean)
        for _ in range(layers):
            blocks += [nn.Linear(width, hidden), nn.ReLU()]
            width = hidden
        self.body = nn.Sequential(*blocks, nn.Linear(width, 1))

    def forward(self, x):
        # The network predicts log(1 + count); exp(...) - 1 turns it back into bikes. (Not torch.expm1: the ONNX
        # exporter doesn't support it. Checking the export, as below, is how you find such things.)
        return (torch.exp(self.body((x - self.mean) / self.std)) - 1).clamp(min=0).squeeze(-1)


def tensors(d):
    return torch.tensor(d[FEATURES].to_numpy(np.float32)), torch.tensor(d[TARGET].to_numpy(np.float32))


if __name__ == "__main__":
    df = load()
    tr = between(df, SETTINGS["train_start"], SETTINGS["train_end"])
    va = between(df, SETTINGS["train_end"], SETTINGS["valid_end"])
    Xtr, ytr = tensors(tr)
    Xva, yva = tensors(va)
    model = Net(Xtr.mean(0).numpy(), Xtr.std(0).numpy(), CONFIG["hidden"], CONFIG["layers"])
    opt = torch.optim.Adam(model.parameters(), lr=CONFIG["lr"])

    t, best, best_state, waited = time.perf_counter(), float("inf"), None, 0
    for epoch in range(CONFIG["epochs"]):
        model.train()
        for idx in torch.randperm(len(Xtr)).split(CONFIG["batch"]):
            pred_log = model.body((Xtr[idx] - model.mean) / model.std).squeeze(-1)
            loss = nn.functional.mse_loss(pred_log, torch.log1p(ytr[idx]))
            opt.zero_grad()
            loss.backward()
            opt.step()
        model.eval()
        with torch.no_grad():
            mae = (model(Xva) - yva).abs().mean().item()
        if mae < best:
            best, best_state, waited, best_epoch = mae, {k: v.clone() for k, v in model.state_dict().items()}, 0, epoch
        else:
            waited += 1
            if waited >= CONFIG["patience"]:      # early stopping: validation stopped improving
                break
    model.load_state_dict(best_state)
    stopped = "early stopping after " + str(CONFIG["patience"]) + " epochs without improvement" \
        if waited >= CONFIG["patience"] else "the epoch limit"
    print(f"1. Trained {epoch + 1} epochs in {time.perf_counter() - t:.0f} s, stopped by {stopped}; "
          f"kept the best, epoch {best_epoch + 1}")
    with torch.no_grad():
        s = score(yva.numpy(), model(Xva).numpy())
    print(f"   validation (Jan-Feb 2012): MAE {s['mae']:.1f}, bias {s['bias']:+.1f}   "
          f"(the tree model from project 1: MAE 28.0)")

    ckpt = {"state_dict": model.state_dict(), "config": CONFIG, "features": FEATURES, "settings": SETTINGS,
            "data_version": hashlib.sha256(DATA.read_bytes()).hexdigest()[:16], "valid": s,
            "torch": str(torch.__version__)}   # a plain string: weights_only loading accepts only simple types
    torch.save(ckpt, "bikecast_net.pt")
    back = torch.load("bikecast_net.pt", weights_only=True)
    net2 = Net(np.zeros(len(FEATURES)), np.ones(len(FEATURES)), back["config"]["hidden"], back["config"]["layers"])
    net2.load_state_dict(back["state_dict"])
    same = torch.allclose(net2(Xva[:100]), model(Xva[:100]))
    print(f"2. Checkpoint: weights, normalization, settings, feature order and data version in one file; "
          f"reloaded gives the same predictions: {same}")

    torch.onnx.export(model, (Xva[:1],), "bikecast_net.onnx", input_names=["features"], output_names=["bikes"],
                      dynamic_axes={"features": {0: "batch"}}, dynamo=False)
    import onnxruntime as ort
    sess = ort.InferenceSession("bikecast_net.onnx", providers=["CPUExecutionProvider"])
    x = Xva.numpy()
    onnx_pred = sess.run(None, {"features": x})[0]
    with torch.no_grad():
        torch_pred = model(Xva).numpy()
    print(f"3. ONNX export: largest difference from PyTorch on {len(x):,} hours = "
          f"{np.abs(onnx_pred - torch_pred).max():.4f} bikes")

    one = x[:1]
    for name, fn in [("PyTorch", lambda: model(torch.from_numpy(one))), ("ONNX Runtime", lambda: sess.run(None, {"features": one}))]:
        with torch.no_grad():
            for _ in range(20):
                fn()
            t = time.perf_counter()
            for _ in range(1000):
                fn()
        print(f"   {name:13} one prediction: {(time.perf_counter() - t):.3f} ms average")
    import os
    print(f"   files: bikecast_net.pt {os.path.getsize('bikecast_net.pt') / 1e3:.0f} KB, "
          f"bikecast_net.onnx {os.path.getsize('bikecast_net.onnx') / 1e3:.0f} KB. "
          "The service image needs onnxruntime (about 15 MB), not PyTorch (hundreds of MB).")
    json.dump({"valid": s, "config": CONFIG}, open("p09_result.json", "w"), indent=1)
