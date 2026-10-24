"""
Shared grid utilities used by every solver strategy, the puzzle bank,
and the benchmark harness.

A grid is a plain 9x9 list of lists of ints, 0 meaning "empty". Using
a plain Python type (rather than a custom class) keeps the solver
interface trivial: `solve(grid) -> grid`.
"""
from typing import List, Optional

Grid = List[List[int]]

# Bits 1..9 set (bit 0 is unused so bit index == digit value, which
# keeps all the bit-twiddling below readable).
FULL_MASK = sum(1 << d for d in range(1, 10))


def box_index(r: int, c: int) -> int:
    """Index (0-8) of the 3x3 box containing cell (r, c)."""
    return (r // 3) * 3 + (c // 3)


def candidates_mask(r: int, c: int, row_used: List[int], col_used: List[int], box_used: List[int]) -> int:
    """Bitmask of the digits (1-9) still legal at (r, c)."""
    used = row_used[r] | col_used[c] | box_used[box_index(r, c)]
    return FULL_MASK & ~used


def copy_grid(grid: Grid) -> Grid:
    return [row[:] for row in grid]


def parse_grid(text: str) -> Grid:
    """
    Parse an 81-character puzzle string into a grid. '0', '.' and '_'
    all mean "empty"; any other whitespace/formatting in the input is
    ignored, so puzzles can be written as one line or as 9 lines of 9.
    """
    digits = [ch for ch in text if ch in "0123456789.-_"]
    if len(digits) != 81:
        raise ValueError(f"Expected 81 cells, got {len(digits)}")
    grid = []
    for r in range(9):
        row = []
        for c in range(9):
            ch = digits[r * 9 + c]
            row.append(0 if ch in ".-_0" else int(ch))
        grid.append(row)
    return grid


def grid_to_string(grid: Grid) -> str:
    return "".join(str(v) for row in grid for v in row)


def print_grid(grid: Grid) -> None:
    """Pretty-print a grid with 3x3 box separators."""
    lines = []
    for r in range(9):
        if r % 3 == 0 and r != 0:
            lines.append("------+-------+------")
        row_cells = []
        for c in range(9):
            if c % 3 == 0 and c != 0:
                row_cells.append("|")
            v = grid[r][c]
            row_cells.append(str(v) if v != 0 else ".")
        lines.append(" ".join(row_cells))
    print("\n".join(lines))


def is_complete(grid: Grid) -> bool:
    return all(v != 0 for row in grid for v in row)


def is_valid_solution(grid: Grid, given: Optional[Grid] = None) -> bool:
    """
    True if `grid` is a fully-filled, rule-valid Sudoku solution, and
    (when `given` is provided) it agrees with every clue in `given`.
    """
    full_set = set(range(1, 10))

    for r in range(9):
        if set(grid[r]) != full_set:
            return False
    for c in range(9):
        if {grid[r][c] for r in range(9)} != full_set:
            return False
    for br in range(0, 9, 3):
        for bc in range(0, 9, 3):
            box = {grid[r][c] for r in range(br, br + 3) for c in range(bc, bc + 3)}
            if box != full_set:
                return False

    if given is not None:
        for r in range(9):
            for c in range(9):
                if given[r][c] != 0 and given[r][c] != grid[r][c]:
                    return False

    return True


def is_consistent_partial_grid(grid: Grid) -> bool:
    """
    True if no digit repeats within any row, column, or box among the
    NON-empty cells (unlike is_valid_solution, this doesn't require
    every cell to be filled -- it's for checking a freshly-read puzzle
    before solving, not a finished solution).

    This is a cheap, useful sanity check on vision output specifically:
    grid detection locking onto the wrong region of a photo produces
    cell crops that don't line up with the real cells, and the digits
    "read" from them are essentially random -- which will almost
    always violate Sudoku's constraints somewhere, since a real puzzle
    never does. A random-looking grid failing this check is a strong
    signal to report a read failure rather than silently handing a
    solver (or worse, the pen) nonsense.
    """
    for r in range(9):
        values = [v for v in grid[r] if v != 0]
        if len(values) != len(set(values)):
            return False
    for c in range(9):
        values = [grid[r][c] for r in range(9) if grid[r][c] != 0]
        if len(values) != len(set(values)):
            return False
    for br in range(0, 9, 3):
        for bc in range(0, 9, 3):
            values = [grid[r][c] for r in range(br, br + 3) for c in range(bc, bc + 3) if grid[r][c] != 0]
            if len(values) != len(set(values)):
                return False
    return True
