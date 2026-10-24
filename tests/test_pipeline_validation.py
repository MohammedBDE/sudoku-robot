import pytest

from sudoku_robot.utils import is_consistent_partial_grid


def test_empty_grid_is_consistent():
    grid = [[0] * 9 for _ in range(9)]
    assert is_consistent_partial_grid(grid)


def test_partially_filled_valid_grid_is_consistent():
    grid = [[0] * 9 for _ in range(9)]
    grid[0][0] = 5
    grid[0][1] = 3
    grid[1][0] = 6
    assert is_consistent_partial_grid(grid)


def test_duplicate_in_row_is_inconsistent():
    grid = [[0] * 9 for _ in range(9)]
    grid[0][0] = 5
    grid[0][5] = 5
    assert not is_consistent_partial_grid(grid)


def test_duplicate_in_column_is_inconsistent():
    grid = [[0] * 9 for _ in range(9)]
    grid[0][0] = 7
    grid[8][0] = 7
    assert not is_consistent_partial_grid(grid)


def test_duplicate_in_box_is_inconsistent():
    grid = [[0] * 9 for _ in range(9)]
    grid[0][0] = 4
    grid[1][1] = 4  # same 3x3 box, different row/column
    assert not is_consistent_partial_grid(grid)
