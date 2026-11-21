"""A two-link robot arm in a plane. Forward kinematics is easy: angles -> hand position.
The inverse (position -> angles) is the hard, useful direction, and it has two answers: elbow up or elbow down."""
import math
import torch

L1, L2 = 1.0, 0.7                     # link lengths


def forward(theta):
    """theta: (N, 2) shoulder and elbow angles in radians -> (N, 2) hand positions."""
    a, b = theta[:, 0], theta[:, 1]
    x = L1 * torch.cos(a) + L2 * torch.cos(a + b)
    y = L1 * torch.sin(a) + L2 * torch.sin(a + b)
    return torch.stack([x, y], 1)


def sample(n, seed=0):
    """Random reachable poses: shoulder in [-pi/2, pi/2], elbow bent either way by 0.3 to 2.6 radians."""
    g = torch.Generator().manual_seed(seed)
    shoulder = (torch.rand(n, generator=g) - 0.5) * math.pi
    bend = 0.3 + torch.rand(n, generator=g) * 2.3
    sign = torch.where(torch.rand(n, generator=g) < 0.5, -1.0, 1.0)
    theta = torch.stack([shoulder, sign * bend], 1)
    return forward(theta), theta       # inputs (positions), targets (angles)


if __name__ == "__main__":
    pos, theta = sample(5)
    for p, t in zip(pos, theta):
        print(f"angles ({t[0]:+.2f}, {t[1]:+.2f}) -> hand at ({p[0]:+.2f}, {p[1]:+.2f})")
    # the same hand position, reached the other way: mirror the arm across the line from shoulder to hand
    t = theta[:1]
    p = forward(t)[0]
    other = torch.tensor([[torch.atan2(p[1], p[0]) * 2 - t[0, 0], -t[0, 1]]])
    print(f"other solution for the first point: angles ({other[0, 0]:+.2f}, {other[0, 1]:+.2f}) -> "
          f"hand at ({forward(other)[0, 0]:+.2f}, {forward(other)[0, 1]:+.2f})")
