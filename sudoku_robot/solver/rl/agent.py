"""
A small reinforcement-learning agent that learns a *search heuristic*
for Sudoku backtracking, rather than trying to output a solved grid
directly.

Why this design? Framing Sudoku as "one giant action space, learn to
output 81 digits" is a genuinely hard, largely-unsolved deep RL
problem -- training an agent to do that reliably takes far more
compute and data than fits a course project. Instead we keep RLSolver's
search structure identical to BacktrackingSolver (same DFS, same
undo-on-failure) and let RL replace just one decision: *which empty
cell should we branch on next?* That is a small, well-defined action
space (one action per remaining empty cell) with an obvious reward
signal (fewer backtracks = better), which makes it tractable to learn
with a genuinely simple method.

The agent itself is linear Q-learning with hand-picked features (no
neural network needed for a 3-feature, near-linear problem):

    Q(cell) = weights . features(cell)

Q is interpreted the standard RL way -- predicted *expected return*,
higher is better -- so at decision time we pick the cell with the
HIGHEST predicted Q, and we train the weights with gradient descent on
the TD error, using rewards that are negative for a step/backtrack and
a large positive bonus for reaching a full solution (see train.py for
the training loop itself). Getting this sign convention right matters:
picking argmin instead of argmax here would have the agent actively
seek out backtracking-prone cells.

Credit assignment here is intentionally simple: each branching
decision is updated using only the reward its own subtree produced
(a one-step/terminal update: target = reward, no bootstrapped next
state), not across the whole solve trajectory. That's also why there
is no discount factor (gamma): with nothing bootstrapped there is
nothing to discount. A full multi-step TD chain across the search tree
would be the natural next step -- it would reintroduce gamma and a
next-state term in update().
"""
from typing import Dict, Tuple

import numpy as np

Coord = Tuple[int, int]


def _popcount(mask: int) -> int:
    return bin(mask).count("1")


def _peers(r: int, c: int):
    """The 20 cells sharing a row, column, or 3x3 box with (r, c)."""
    for cc in range(9):
        if cc != c:
            yield (r, cc)
    for rr in range(9):
        if rr != r:
            yield (rr, c)
    br, bc = (r // 3) * 3, (c // 3) * 3
    for rr in range(br, br + 3):
        for cc in range(bc, bc + 3):
            if (rr, cc) != (r, c):
                yield (rr, cc)


class LinearQAgent:
    """Linear function-approximation Q-learning agent for cell selection."""

    FEATURE_NAMES = ["bias", "num_candidates", "peer_candidate_sum"]
    FEATURE_DIM = len(FEATURE_NAMES)

    def __init__(self, weights=None, alpha: float = 0.02, epsilon: float = 0.15):
        self.weights = np.array(weights, dtype=float) if weights is not None else np.zeros(self.FEATURE_DIM)
        self.alpha = alpha      # learning rate
        self.epsilon = epsilon  # exploration rate, training only

    def features(self, candidates: Dict[Coord, int], r: int, c: int) -> np.ndarray:
        """
        Hand-picked features describing how "good" it is to branch on
        cell (r, c) right now:

          - num_candidates: how constrained this cell already is
            (fewer legal digits -> more like the classic MRV heuristic)
          - peer_candidate_sum: how constrained its row/col/box
            neighbours are (branching here narrows their options too)

        A bias term lets the linear model learn a constant offset.
        Both real-valued features are scaled to roughly [0, 1] --
        without that, peer_candidate_sum (up to 20 peers * 9 = 180)
        dwarfs a learning rate tuned for small inputs and the weights
        blow up within the first few updates.
        """
        n_cand = _popcount(candidates[(r, c)])
        peer_sum = sum(_popcount(candidates[p]) for p in _peers(r, c) if p in candidates)
        return np.array([1.0, n_cand / 9.0, peer_sum / 180.0], dtype=float)

    def q(self, feats: np.ndarray) -> float:
        return float(self.weights @ feats)

    def select_cell(self, candidates: Dict[Coord, int], explore: bool = False) -> Tuple[Coord, np.ndarray]:
        """
        Choose which empty cell to branch on next.

        `candidates` maps each remaining empty cell to its bitmask of
        legal digits. Returns the chosen cell and its feature vector
        (the caller needs the features to later call `update`).
        """
        cells = list(candidates.keys())
        feats = {cell: self.features(candidates, *cell) for cell in cells}

        if explore and np.random.rand() < self.epsilon:
            choice = cells[np.random.randint(len(cells))]
        else:
            # Higher predicted return is better, so we maximise Q.
            choice = max(cells, key=lambda cell: self.q(feats[cell]))

        return choice, feats[choice]

    def update(self, feats: np.ndarray, reward: float) -> None:
        """One-step (terminal) TD update: weights += alpha * (reward - Q(feats)) * feats."""
        td_error = reward - self.q(feats)
        self.weights += self.alpha * td_error * feats
        # Clip as a safety net against divergence -- with normalised
        # features and a small alpha this shouldn't normally trigger,
        # but it keeps a bad hyperparameter choice from ever producing
        # NaN/inf weights that would silently break inference.
        np.clip(self.weights, -50.0, 50.0, out=self.weights)

    def save(self, path: str) -> None:
        np.save(path, self.weights)

    def load(self, path: str) -> None:
        self.weights = np.load(path)
