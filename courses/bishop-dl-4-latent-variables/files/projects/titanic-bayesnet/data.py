"""The 891 Titanic passengers of the well-known training set, reduced to four discrete variables."""
from pathlib import Path
import pandas as pd
import torch

URL = "https://raw.githubusercontent.com/datasciencedojo/datasets/master/titanic.csv"
CACHE = Path("data/titanic.csv")
VALUES = {"Class": ["1st", "2nd", "3rd"], "Sex": ["female", "male"],
          "Age": ["child", "adult", "unknown"], "Survived": ["no", "yes"]}


def load():
    if not CACHE.exists():
        CACHE.parent.mkdir(exist_ok=True)
        pd.read_csv(URL).to_csv(CACHE, index=False)
    t = pd.read_csv(CACHE)
    age = t.Age.apply(lambda a: "unknown" if pd.isna(a) else ("child" if a < 16 else "adult"))
    table = pd.DataFrame({"Class": t.Pclass.map({1: "1st", 2: "2nd", 3: "3rd"}), "Sex": t.Sex, "Age": age,
                          "Survived": t.Survived.map({0: "no", 1: "yes"})})
    # one integer column per variable
    return {v: torch.tensor([VALUES[v].index(x) for x in table[v]]) for v in VALUES}


if __name__ == "__main__":
    d = load()
    n = len(d["Survived"])
    print(f"{n} passengers, {d['Survived'].float().mean():.1%} survived")
    for v, vals in VALUES.items():
        print(f"{v:9s}", ", ".join(f"{x} {(d[v] == i).sum().item()}" for i, x in enumerate(vals)))
