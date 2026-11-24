"""Project 5 (days 6-7): reinforcement learning on the lessons' Mars rover. Returns, policies and the Bellman
equation, solved exactly; then a slippery rover, and Q-learning from experience alone."""
import numpy as np

REWARDS = np.array([100, 0, 0, 0, 0, 40])        # states 1..6; 1 and 6 end the episode
LEFT, RIGHT = 0, 1


def q_values(gamma=0.5, misstep=0.0, iters=200):
    """Iterate the Bellman equation Q(s,a) = R(s) + gamma * E[max_a' Q(s',a')] until it stops changing.
    With probability `misstep` the rover goes the other way."""
    Q = np.zeros((6, 2))
    for _ in range(iters):
        V = Q.max(1)
        new = np.zeros_like(Q)
        for s in range(6):
            if s in (0, 5):
                new[s] = REWARDS[s]
                continue
            for a, step in ((LEFT, -1), (RIGHT, 1)):
                new[s, a] = REWARDS[s] + gamma * ((1 - misstep) * V[s + step] + misstep * V[s - step])
        Q = new
    return Q


def show(Q, name):
    pol = "".join("<" if q[0] > q[1] else ">" for q in Q[1:5])
    print(f"   {name:34} Q(s, left)  {np.round(Q[:, 0], 1)}\n   {'':34} Q(s, right) {np.round(Q[:, 1], 1)}   policy: [end]{pol}[end]")


def q_learning(gamma=0.5, misstep=0.1, episodes=3000, alpha=0.1, eps=0.3, seed=0):
    """No model of the world: the rover only tries, sees what happens, and updates its table."""
    rng = np.random.default_rng(seed)
    Q = np.zeros((6, 2))
    for _ in range(episodes):
        s = rng.integers(1, 5)
        while s not in (0, 5):
            a = rng.integers(2) if rng.random() < eps else int(Q[s].argmax())
            step = 1 if a == RIGHT else -1
            if rng.random() < misstep:
                step = -step
            s2 = s + step
            target = REWARDS[s] + gamma * (REWARDS[s2] if s2 in (0, 5) else Q[s2].max())
            Q[s, a] += alpha * (target - Q[s, a])
            s = s2
    Q[0], Q[5] = REWARDS[0], REWARDS[5]
    return Q


if __name__ == "__main__":
    print("States 1 to 6; ending at state 1 earns 100, at state 6 earns 40.\n")
    print("1. The Bellman equation, solved:")
    show(q_values(0.5), "gamma 0.5 (the lesson's example)")
    show(q_values(0.9), "gamma 0.9 (more patient)")
    show(q_values(0.3), "gamma 0.3 (impatient)")
    print("\n2. A slippery rover: 10% of moves go the wrong way")
    show(q_values(0.5, 0.1), "gamma 0.5, misstep 0.1")
    print("\n3. Q-learning: the same slippery rover learns by trying, 3,000 episodes, without knowing the rules")
    Q = q_learning()
    show(Q, "learned from experience")
    print(f"   largest difference from the exact Q: {np.abs(Q - q_values(0.5, 0.1))[1:5].max():.1f}")
