"""
Classic constraint-satisfaction backtracking solver.

Two things make this "efficient" rather than the naive textbook
version that just scans for the first empty cell:

1. Bitmask constraint tracking: for each row/column/3x3 box we keep a
   9-bit mask of digits already used, so "is digit v legal at (r, c)?"
   is O(1) instead of re-scanning 20 peer cells every time.

2. MRV (Minimum Remaining Values) heuristic: at every step we branch
   on the empty cell with the *fewest* legal candidates, not just the
   next empty cell in reading order. This finds contradictions (a
   cell with zero candidates) much sooner and dramatically cuts the
   size of the search tree, especially on hard/near-empty puzzles.
"""
from typing import List, Optional, Tuple

from .base import SudokuSolver
from ..utils import Grid, box_index, candidates_mask, copy_grid


class BacktrackingSolver(SudokuSolver):
    name = "backtracking"

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

        self.stats = {"nodes_expanded": 0, "backtracks": 0}
        solved = self._backtrack(board, row_used, col_used, box_used, empties)
        return board if solved else None

    def _select_cell(self, empties, row_used, col_used, box_used):
        """Pick the empty cell with the fewest legal candidates (MRV)."""
        best_cell = None
        best_mask = 0
        best_count = 10  # more than the max possible (9)

        for (r, c) in empties:
            mask = candidates_mask(r, c, row_used, col_used, box_used)
            count = bin(mask).count("1")
            if count < best_count:
                best_cell, best_mask, best_count = (r, c), mask, count
                if count == 0:
                    break  # dead end -- no need to keep scanning
        return best_cell, best_mask

    def _backtrack(self, board, row_used, col_used, box_used, empties) -> bool:
        if not empties:
            return True  # every cell filled, no constraints violated

        self.stats["nodes_expanded"] += 1
        (r, c), mask = self._select_cell(empties, row_used, col_used, box_used)
        if mask == 0:
            return False  # chosen cell has no legal digit left -> contradiction

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

            if self._backtrack(board, row_used, col_used, box_used, empties):
                return True

            # undo and try the next candidate digit
            board[r][c] = 0
            row_used[r] &= ~bit
            col_used[c] &= ~bit
            box_used[b] &= ~bit
            self.stats["backtracks"] += 1

        empties.append((r, c))  # restore for the caller's own backtracking
        return False


def count_solutions(grid: Grid, limit: int = 2) -> int:
    """
    Count the grid's solutions, stopping as soon as `limit` are found
    (so the default answers "none / unique / more than one" cheaply).
    Same bitmask + MRV search as BacktrackingSolver, but it keeps going
    after the first solution instead of returning it.
    """
    row_used = [0] * 9
    col_used = [0] * 9
    box_used = [0] * 9
    empties: List[Tuple[int, int]] = []
    for r in range(9):
        for c in range(9):
            v = grid[r][c]
            if v == 0:
                empties.append((r, c))
                continue
            bit = 1 << v
            if (row_used[r] | col_used[c] | box_used[box_index(r, c)]) & bit:
                return 0  # a given clue already breaks the rules
            row_used[r] |= bit
            col_used[c] |= bit
            box_used[box_index(r, c)] |= bit

    def search() -> int:
        if not empties:
            return 1
        best = min(empties, key=lambda rc: bin(candidates_mask(*rc, row_used, col_used, box_used)).count("1"))
        mask = candidates_mask(*best, row_used, col_used, box_used)
        r, c = best
        b = box_index(r, c)
        empties.remove(best)
        found = 0
        for v in range(1, 10):
            bit = 1 << v
            if not mask & bit:
                continue
            row_used[r] |= bit
            col_used[c] |= bit
            box_used[b] |= bit
            found += search()
            row_used[r] &= ~bit
            col_used[c] &= ~bit
            box_used[b] &= ~bit
            if found >= limit:
                break
        empties.append(best)
        return found

    return min(search(), limit)
