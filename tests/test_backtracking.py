import random

from sudoku_robot.puzzles.generator import generate_full_grid
from sudoku_robot.puzzles.samples import PUZZLES
from sudoku_robot.solver.backtracking import BacktrackingSolver
from sudoku_robot.utils import is_valid_solution


def test_solves_all_sample_puzzles():
    solver = BacktrackingSolver()
    for puzzle in PUZZLES:
        solution = solver.solve(puzzle.grid)
        assert solution is not None, f"{puzzle.name} was not solved"
        assert is_valid_solution(solution, given=puzzle.grid), f"{puzzle.name} solution invalid"


def test_does_not_mutate_input():
    solver = BacktrackingSolver()
    puzzle = PUZZLES[0]
    original = [row[:] for row in puzzle.grid]
    solver.solve(puzzle.grid)
    assert puzzle.grid == original


def test_unsolvable_puzzle_returns_none():
    # Start from a real solved grid, blank exactly one cell, then
    # duplicate that cell's value onto a same-row peer. That leaves a
    # single empty cell whose row/column/box masks combine to block
    # all 9 digits -- a genuine contradiction the solver detects in
    # its very first node. (A puzzle that's merely "mostly empty with
    # a duplicate clue somewhere" is a bad test: with almost every
    # other cell also empty, plain MRV backtracking has nothing to
    # prune on and can take an impractically long time to explore its
    # way to the one contradiction -- it's technically finite, but not
    # something a test suite should wait around for.)
    rng = random.Random(0)
    grid = generate_full_grid(rng)
    x = grid[0][0]
    grid[0][0] = 0
    grid[0][1] = x
    assert BacktrackingSolver().solve(grid) is None


def test_count_solutions_distinguishes_unique_multiple_and_none():
    from sudoku_robot.puzzles.samples import get_puzzle
    from sudoku_robot.solver.backtracking import count_solutions

    assert count_solutions(get_puzzle("physical_demo").grid) == 1
    assert count_solutions(get_puzzle("near_empty_17").grid) == 2   # capped at the limit
    assert count_solutions([[0] * 9 for _ in range(9)], limit=5) == 5
    broken = [[0] * 9 for _ in range(9)]
    broken[0][0] = broken[0][1] = 7
    assert count_solutions(broken) == 0


def test_sample_uniqueness_matches_documentation():
    """samples.py documents which sample puzzles are unique -- keep that note honest."""
    from sudoku_robot.puzzles.samples import get_puzzle
    from sudoku_robot.solver.backtracking import count_solutions

    unique = {p.name for p in PUZZLES if count_solutions(p.grid) == 1}
    assert unique == {"physical_demo", "inkala_hardest"}
    clues = sum(v != 0 for row in get_puzzle("near_empty_17").grid for v in row)
    assert clues == 19


def test_generator_unique_mode_produces_a_unique_puzzle():
    from sudoku_robot.puzzles.generator import make_puzzle
    from sudoku_robot.solver.backtracking import count_solutions

    grid = make_puzzle(random.Random(7), clues=30, unique=True)
    assert count_solutions(grid) == 1
    assert sum(v != 0 for row in grid for v in row) >= 30
