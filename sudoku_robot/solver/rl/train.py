"""
Trains the LinearQAgent used by RLSolver.

No external RL framework needed: for many random practice puzzles, we
run the exact same DFS search RLSolver uses at inference time, letting
the *current* agent choose which cell to branch on (with epsilon-greedy
exploration), and apply an online TD update after every placement.

Run it with:

    python -m sudoku_robot.solver.rl.train

This overwrites weights.npy, which RLSolver loads automatically the
next time it's constructed.
"""
import os
import random

from .agent import LinearQAgent
from ...puzzles.generator import make_puzzle
from ...utils import Grid, box_index, candidates_mask, copy_grid

WEIGHTS_PATH = os.path.join(os.path.dirname(__file__), "weights.npy")

# Reward shaping: every placement costs a little (we want short
# searches), a placement that dead-ends costs a lot more (that's the
# signal that tells the agent "don't branch on cells like that"), and
# finally solving the puzzle is a big win.
STEP_REWARD = -1.0
BACKTRACK_PENALTY = -3.0
SOLVED_REWARD = 10.0


def run_training_episode(agent: LinearQAgent, grid: Grid, max_nodes: int = 600):
    """
    Solve one puzzle with the agent in exploring/learning mode,
    updating its weights after every branching decision.

    Returns (solved: bool, nodes_expanded: int).
    """
    board = copy_grid(grid)
    row_used = [0] * 9
    col_used = [0] * 9
    box_used = [0] * 9
    empties = []
    for r in range(9):
        for c in range(9):
            v = board[r][c]
            if v == 0:
                empties.append((r, c))
            else:
                bit = 1 << v
                row_used[r] |= bit
                col_used[c] |= bit
                box_used[box_index(r, c)] |= bit

    nodes = {"count": 0}

    def search() -> bool:
        if nodes["count"] > max_nodes:
            return False
        if not empties:
            return True

        nodes["count"] += 1
        candidates = {
            (r, c): candidates_mask(r, c, row_used, col_used, box_used)
            for (r, c) in empties
        }
        if any(mask == 0 for mask in candidates.values()):
            return False

        (r, c), feats = agent.select_cell(candidates, explore=True)
        mask = candidates[(r, c)]
        empties.remove((r, c))
        b = box_index(r, c)

        for v in range(1, 10):
            bit = 1 << v
            if not (mask & bit):
                continue

            board[r][c] = v
            row_used[r] |= bit
            col_used[c] |= bit
            box_used[b] |= bit

            if search():
                # This branching decision led straight to a full
                # solution -- reward it and propagate success upward.
                agent.update(feats, SOLVED_REWARD)
                return True

            board[r][c] = 0
            row_used[r] &= ~bit
            col_used[c] &= ~bit
            box_used[b] &= ~bit
            # This digit choice dead-ended -- penalise having branched
            # on this cell. (One-step credit assignment: each failed
            # digit at this cell reinforces the same signal.)
            agent.update(feats, STEP_REWARD + BACKTRACK_PENALTY)

        empties.append((r, c))
        return False

    solved = search()
    return solved, nodes["count"]


def train(num_puzzles: int = 150, seed: int = 42) -> LinearQAgent:
    rng = random.Random(seed)
    agent = LinearQAgent()
    # Cycle through a spread of difficulties (clue counts) so the
    # agent doesn't overfit to only-easy or only-hard puzzles. Kept on
    # the easier side (more givens -> a much smaller search tree) so a
    # full training run finishes in seconds rather than minutes -- the
    # search itself is plain Python with no vectorisation.
    difficulties = [50, 44, 38, 32]

    for i in range(num_puzzles):
        clues = difficulties[i % len(difficulties)]
        puzzle = make_puzzle(rng, clues)
        solved, nodes = run_training_episode(agent, puzzle)
        if (i + 1) % 25 == 0:
            print(f"episode {i + 1}/{num_puzzles}  clues={clues}  solved={solved}  "
                  f"nodes={nodes}  weights={agent.weights}")

    agent.save(WEIGHTS_PATH)
    print(f"Saved trained weights to {WEIGHTS_PATH}")
    return agent


if __name__ == "__main__":
    train()
