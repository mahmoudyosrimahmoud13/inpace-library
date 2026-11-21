# CIFAR-10 image classifier

A convolutional network written in PyTorch and trained from scratch on CIFAR-10 (60,000 colour photos, 10 classes):
three blocks of 3x3 convolutions with batch normalization and max-pooling, flip and crop augmentation, and a one-cycle
learning-rate schedule.

## Results

| | |
|---|---|
| parameters | 82,778 |
| training | 6 epochs, laptop CPU (about 15 minutes) |
| validation accuracy | 0.801 |
| **test accuracy** | **0.796** |

Easiest classes: car 0.92, ship 0.89, truck 0.87. Hardest: cat 0.64 (mistaken for dog 153 times), bird 0.67.

## Run it

```bash
pip install -r requirements.txt
python train.py --epochs 6     # --width 32 and more epochs on a GPU for higher accuracy
python evaluate.py
```

## What I learned

- Convolutions share small filters across the image, which suits photos far better than fully connected layers.
- Augmentation must fit the data: mirror images of cars are still cars, so flips help here.
- Per-class errors show what the model really learned: confusions between cats and dogs, and between planes and ships.

Based on chapter 10 of *Deep Learning: Foundations and Concepts* (Bishop & Bishop, 2024).
