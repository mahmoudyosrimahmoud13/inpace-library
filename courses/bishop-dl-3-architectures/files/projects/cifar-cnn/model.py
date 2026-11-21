"""A small convolutional network (Bishop, sections 10.2.6 to 10.2.8): stacks of 3x3 convolutions, pooling, then a classifier."""
from torch import nn


def block(c_in, c_out):
    return nn.Sequential(nn.Conv2d(c_in, c_out, 3, padding=1), nn.BatchNorm2d(c_out), nn.ReLU(),
                         nn.Conv2d(c_out, c_out, 3, padding=1), nn.BatchNorm2d(c_out), nn.ReLU(),
                         nn.MaxPool2d(2))                       # 32x32 -> 16x16 -> 8x8 -> 4x4


class SmallCNN(nn.Module):
    def __init__(self, width=32, n_classes=10):
        super().__init__()
        self.features = nn.Sequential(block(3, width), block(width, 2 * width), block(2 * width, 4 * width))
        self.classifier = nn.Sequential(nn.Flatten(), nn.Dropout(0.3), nn.Linear(4 * width * 4 * 4, n_classes))

    def forward(self, x):
        return self.classifier(self.features(x))
