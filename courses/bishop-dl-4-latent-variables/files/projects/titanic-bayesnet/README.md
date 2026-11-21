# Titanic survival as a Bayesian network

A discrete Bayesian network over four variables of the 891 Titanic passengers (class, sex, age group, survival), written
from scratch with PyTorch tensors: conditional tables learned by counting, exact inference by summing the joint table,
and five graph structures compared by cross-validation.

## Questions answered

| question | answer |
|---|---|
| p(survived) | 0.38 |
| p(survived \| woman, 1st class) | 0.94 |
| p(survived \| man, 3rd class) | 0.15 |
| p(survived \| boy, 2nd class) vs man, 2nd class | 0.91 vs 0.08 |
| p(1st class) before vs after learning someone survived | 0.24 -> 0.37 |

## Which graph? (5-fold cross-validation)

| graph | parameters | held-out log p per passenger | survival accuracy |
|---|---|---|---|
| no edges | 6 | -3.110 | 0.616 |
| naive Bayes | 11 | -2.895 | 0.787 |
| class -> age; class, sex, age -> survived | 27 | -2.837 | 0.807 |
| + class -> sex | 29 | -2.829 | 0.807 |
| every edge (full table) | 35 | -2.824 | 0.807 |

## Run it

```bash
pip install -r requirements.txt
python queries.py
python compare_graphs.py
```

## What I learned

- A graph turns a joint distribution into small conditional tables (equation 11.6), and every question is answered by
  the same procedure: multiply, sum out what you don't know, normalize.
- Inference runs both ways: from class to survival, and from survival back to class.
- With 4 variables and 891 rows, even the full table can be estimated; graphs pay off when there are many variables.

Based on chapter 11 of *Deep Learning: Foundations and Concepts* (Bishop & Bishop, 2024).
