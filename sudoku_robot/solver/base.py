"""
Common interface every solving strategy must implement.

This is the whole point of the abstraction layer: the CLI, the
benchmark harness, and the camera-to-pen pipeline only ever talk
to a `SudokuSolver`. They don't know or care whether that's backtracking,
the RL agent, or something else added later -- swapping strategies is
just a matter of passing a different name to `get_solver()`.
"""
from abc import ABC, abstractmethod
from typing import Optional

from ..utils import Grid


class SudokuSolver(ABC):
    #: Short identifier used in the CLI / factory / benchmark reports.
    name: str = "base"

    def __init__(self):
        # Populated by solve() so the benchmark can compare *how* each
        # strategy found its answer (search effort), not just whether
        # it did. Kept as a plain dict rather than a fixed schema
        # since different strategies may want to report different things.
        self.stats = {}

    @abstractmethod
    def solve(self, grid: Grid) -> Optional[Grid]:
        """
        Solve a 9x9 Sudoku grid (0 = empty cell).

        Must NOT mutate the input grid. Returns a fully solved grid,
        or None if the puzzle has no solution.
        """
        raise NotImplementedError
