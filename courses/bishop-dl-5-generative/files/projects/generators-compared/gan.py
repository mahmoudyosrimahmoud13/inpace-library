"""A generator and a discriminator (Bishop, section 17.1): two networks trained against each other."""
from torch import nn

Z = 64                                           # size of the random input vector


def generator():
    """Random vector z (64 numbers) -> a 28x28 image, pixels in [-1, 1]."""
    return nn.Sequential(nn.Linear(Z, 256), nn.LeakyReLU(0.2),
                         nn.Linear(256, 512), nn.BatchNorm1d(512), nn.LeakyReLU(0.2),
                         nn.Linear(512, 784), nn.Tanh())


def discriminator():
    """Image -> one score (a logit): high means 'this looks like a real photo'."""
    return nn.Sequential(nn.Linear(784, 512), nn.LeakyReLU(0.2), nn.Dropout(0.3),
                         nn.Linear(512, 256), nn.LeakyReLU(0.2), nn.Dropout(0.3),
                         nn.Linear(256, 1))
