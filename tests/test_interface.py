import pytest

from sudoku_robot.solver import AVAILABLE_STRATEGIES, get_solver
from sudoku_robot.solver.base import SudokuSolver


def test_all_strategies_share_the_interface():
    for name in AVAILABLE_STRATEGIES:
        solver = get_solver(name)
        assert isinstance(solver, SudokuSolver)
        assert callable(solver.solve)


def test_unknown_strategy_raises():
    with pytest.raises(ValueError):
        get_solver("not_a_real_strategy")
