"""Ask the network questions, in both directions: from causes to effects and back."""
from data import load
from bayesnet import BayesNet

GRAPH = {"Class": [], "Sex": [], "Age": ["Class"], "Survived": ["Class", "Sex", "Age"]}
net = BayesNet(GRAPH).fit(load())

def show(target, **ev):
    p = net.query(target, **ev)
    cond = ", ".join(f"{k}={v}" for k, v in ev.items()) or "nothing"
    print(f"p({target} | {cond}): " + ", ".join(f"{k} {v:.2f}" for k, v in p.items()))

print("Predicting (causes -> effect):")
show("Survived")
show("Survived", Sex="female", Class="1st")
show("Survived", Sex="male", Class="3rd")
show("Survived", Sex="male", Class="2nd", Age="child")
show("Survived", Sex="male", Class="2nd", Age="adult")
print("\nReasoning backwards (effect -> causes):")
show("Class")
show("Class", Survived="yes")
show("Age", Survived="yes", Sex="male")
