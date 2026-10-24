"""
Random Sudoku generation, used both to build the static sample puzzle
bank (see samples.py) and to create fresh practice puzzles for
training the RL agent (see solver/rl/train.py).

The approach is the standard one: randomly fill a complete, valid 9x9
grid (via randomized backtracking), then blank out cells to reach the
desired number of clues. By default this does NOT guarantee a
*unique* solution once many cells are removed -- fine for solver
testing and RL training, since solvers only need to find *a* valid
completion. Pass unique=True to make_puzzle() to only remove clues
while the solution stays unique (checked with
solver.backtracking.count_solutions).
"""
import random
from typing import List

from ..utils import Grid, box_index


def generate_full_grid(rng: random.Random) -> Grid:
    """Produce a random, fully solved 9x9 grid via randomized backtracking."""
    board = [[0] * 9 for _ in range(9)]
    row_used = [0] * 9
    col_used = [0] * 9
    box_used = [0] * 9

    def fill(pos: int = 0) -> bool:
        if pos == 81:
            return True
        r, c = divmod(pos, 9)
        digits = list(range(1, 10))
        rng.shuffle(digits)
        b = box_index(r, c)
        for v in digits:
            bit = 1 << v
            if not (row_used[r] | col_used[c] | box_used[b]) & bit:
                board[r][c] = v
                row_used[r] |= bit
                col_used[c] |= bit
                box_used[b] |= bit
                if fill(pos + 1):
                    return True
                board[r][c] = 0
                row_used[r] &= ~bit
                col_used[c] &= ~bit
                box_used[b] &= ~bit
        return False

    fill()
    return board


def make_puzzle(rng: random.Random, clues: int, unique: bool = False) -> Grid:
    """
    Start from a full grid and blank out cells until only `clues` remain.

    With unique=False (the default, and what the sample bank and RL
    training use) cells are removed blindly, so the result usually has
    many solutions. With unique=True a cell is only blanked if the
    puzzle still has exactly one solution afterwards; if no further
    cell can be removed without breaking uniqueness, the returned
    puzzle may keep more than `clues` givens.
    """
    grid = generate_full_grid(rng)
    cells: List = [(r, c) for r in range(9) for c in range(9)]
    rng.shuffle(cells)
    if not unique:
        for (r, c) in cells[: 81 - clues]:
            grid[r][c] = 0
        return grid

    from ..solver.backtracking import count_solutions

    remaining = 81
    for (r, c) in cells:
        if remaining <= clues:
            break
        value, grid[r][c] = grid[r][c], 0
        if count_solutions(grid, limit=2) == 1:
            remaining -= 1
        else:
            grid[r][c] = value
    return grid
