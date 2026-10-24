"""
Reinforcement-learning-guided backtracking solver.

Structurally this is the *same* DFS/backtracking search as
BacktrackingSolver (same bitmask constraint tracking, same
undo-on-failure), which is deliberate: the only thing that changes is
which empty cell gets branched on at each node. Instead of the
hand-coded MRV heuristic, that choice comes from a small Q-learning
agent (see agent.py) trained offline on many practice puzzles
(train.py).

Because the underlying search is still a complete backtracking search,
RLSolver would eventually find a solution whenever one exists -- but
unlike the hand-tuned MRV heuristic, a learned heuristic is not
guaranteed to be *good*. A poor cell ordering can blow up the search
tree combinatorially, especially on sparse puzzles. `max_nodes` is a
hard safety cap: if the search exceeds it, solve() gives up and
returns None rather than running indefinitely. Hitting that cap is a
legitimate, reportable outcome for the benchmark (it means "this
heuristic performed badly here"), not a bug to hide.
"""
import os
from typing import List, Optional, Tuple

from ..base import SudokuSolver
from ...utils import Grid, box_index, candidates_mask, copy_grid
from .agent import LinearQAgent

DEFAULT_WEIGHTS_PATH = os.path.join(os.path.dirname(__file__), "weights.npy")


class RLSolver(SudokuSolver):
    name = "rl"

    def __init__(self, weights_path: Optional[str] = None, explore: bool = False, max_nodes: int = 100_000):
        super().__init__()
        self.agent = LinearQAgent()
        path = weights_path or DEFAULT_WEIGHTS_PATH
        if os.path.exists(path):
            self.agent.load(path)
        # Exploration (epsilon-greedy random branching) is only useful
        # while training the agent; solving a real puzzle should use
        # the learned policy deterministically.
        self.explore = explore
        self.max_nodes = max_nodes

    def solve(self, grid: Grid) -> Optional[Grid]:
        board = copy_grid(grid)
        row_used = [0] * 9
        col_used = [0] * 9
        box_used = [0] * 9
        empties: List[Tuple[int, int]] = []

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

        self.stats = {"nodes_expanded": 0, "backtracks": 0, "budget_exceeded": False}
        solved = self._search(board, row_used, col_used, box_used, empties)
        return board if solved else None

    def _search(self, board, row_used, col_used, box_used, empties) -> bool:
        if not empties:
            return True
        if self.stats["nodes_expanded"] >= self.max_nodes:
            self.stats["budget_exceeded"] = True
            return False

        self.stats["nodes_expanded"] += 1
        candidates = {
            (r, c): candidates_mask(r, c, row_used, col_used, box_used)
            for (r, c) in empties
        }
        if any(mask == 0 for mask in candidates.values()):
            return False  # some empty cell already has no legal digit

        (r, c), _feats = self.agent.select_cell(candidates, explore=self.explore)
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

            if self._search(board, row_used, col_used, box_used, empties):
                return True

            board[r][c] = 0
            row_used[r] &= ~bit
            col_used[c] &= ~bit
            box_used[b] &= ~bit
            self.stats["backtracks"] += 1

        empties.append((r, c))
        return False
