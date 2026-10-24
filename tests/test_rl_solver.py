import random

from sudoku_robot.puzzles.generator import generate_full_grid
from sudoku_robot.puzzles.samples import PUZZLES
from sudoku_robot.solver.rl.rl_solver import RLSolver
from sudoku_robot.utils import is_valid_solution


def test_solves_all_sample_puzzles():
    # RLSolver's search is still a complete backtracking search, so --
    # like BacktrackingSolver -- it must solve every sample puzzle.
    # What the learned heuristic changes is *how many nodes it
    # explores*, not *whether* it finds an answer.
    solver = RLSolver()
    for puzzle in PUZZLES:
        solution = solver.solve(puzzle.grid)
        assert solution is not None, f"{puzzle.name} was not solved"
        assert is_valid_solution(solution, given=puzzle.grid), f"{puzzle.name} solution invalid"


def test_does_not_mutate_input():
    solver = RLSolver()
    puzzle = PUZZLES[0]
    original = [row[:] for row in puzzle.grid]
    solver.solve(puzzle.grid)
    assert puzzle.grid == original


def test_unsolvable_puzzle_returns_none():
    # See test_backtracking.test_unsolvable_puzzle_returns_none for why
    # this specific construction (one genuinely zero-candidate cell)
    # is used instead of a duplicate-clue-in-an-otherwise-empty-grid.
    rng = random.Random(0)
    grid = generate_full_grid(rng)
    x = grid[0][0]
    grid[0][0] = 0
    grid[0][1] = x
    assert RLSolver().solve(grid) is None


def test_agent_update_is_one_step_terminal_td():
    import numpy as np

    from sudoku_robot.solver.rl.agent import LinearQAgent

    agent = LinearQAgent(weights=[1.0, 2.0, 3.0], alpha=0.1)
    feats = np.array([1.0, 0.5, 0.25])
    q_before = agent.q(feats)                     # 2.75
    agent.update(feats, reward=-4.0)
    expected = np.array([1.0, 2.0, 3.0]) + 0.1 * (-4.0 - q_before) * feats
    assert np.allclose(agent.weights, expected)
