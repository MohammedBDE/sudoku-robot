import random

import pytest

from sudoku_robot.puzzles.generator import generate_full_grid
from sudoku_robot.puzzles.samples import PUZZLES, get_puzzle
from sudoku_robot.solver import AVAILABLE_STRATEGIES, get_solver
from sudoku_robot.solver import humanizer as hz
from sudoku_robot.solver.humanizer import (
    BOX_LINE_REDUCTION,
    GUESS,
    HIDDEN_PAIR,
    HIDDEN_SINGLE,
    LOGIC_TECHNIQUES,
    NAKED_PAIR,
    NAKED_SINGLE,
    POINTING_PAIR,
    HumanizerSolver,
    _State,
)
from sudoku_robot.utils import is_valid_solution, parse_grid


# -- Interface & correctness -------------------------------------------------

def test_registered_and_selectable():
    assert AVAILABLE_STRATEGIES["humanizer"] is HumanizerSolver
    assert isinstance(get_solver("humanizer"), HumanizerSolver)

    from sudoku_robot.cli import build_parser
    assert build_parser().parse_args(["--solver", "humanizer"]).solver == "humanizer"


@pytest.mark.parametrize("puzzle", PUZZLES, ids=lambda p: p.name)
def test_solves_every_sample_with_a_valid_board(puzzle):
    solver = HumanizerSolver()
    solution = solver.solve(puzzle.grid)
    assert solution is not None
    assert is_valid_solution(solution, given=puzzle.grid)

    # The step log accounts for every empty cell exactly once, with the final digit.
    empties = {(r, c) for r in range(9) for c in range(9) if puzzle.grid[r][c] == 0}
    placements = solver.placements
    assert len(placements) == len(empties)
    assert {s.cell for s in placements} == empties
    for s in placements:
        assert solution[s.cell[0]][s.cell[1]] == s.digit


def test_does_not_mutate_input():
    grid = get_puzzle("hard_1").grid
    before = [row[:] for row in grid]
    HumanizerSolver().solve(grid)
    assert grid == before


def test_unsolvable_and_invalid_puzzles_return_none():
    grid = generate_full_grid(random.Random(0))
    grid[0][0], grid[0][1] = grid[0][1], grid[0][0]  # breaks the rules
    assert HumanizerSolver().solve(grid) is None

    dup = [[0] * 9 for _ in range(9)]
    dup[0][0] = dup[0][5] = 4
    assert HumanizerSolver().solve(dup) is None


# -- Genuinely different from backtracking -------------------------------------

def test_solves_physical_demo_by_pure_logic_with_zero_guesses():
    solver = HumanizerSolver()
    assert solver.solve(get_puzzle("physical_demo").grid) is not None
    assert solver.stats["guesses"] == 0
    assert solver.stats["backtracks"] == 0
    assert {s.technique for s in solver.placements} <= {NAKED_SINGLE, HIDDEN_SINGLE}
    assert not any(s.after_guess for s in solver.steps)


def test_never_calls_the_other_solvers(monkeypatch):
    from sudoku_robot.solver.backtracking import BacktrackingSolver
    from sudoku_robot.solver.rl.rl_solver import RLSolver

    def forbidden(*_a, **_k):
        raise AssertionError("humanizer must not delegate to another solver")

    monkeypatch.setattr(BacktrackingSolver, "solve", forbidden)
    monkeypatch.setattr(RLSolver, "solve", forbidden)
    monkeypatch.setattr("sudoku_robot.solver.backtracking.count_solutions", forbidden)
    for name in ("physical_demo", "hard_1", "inkala_hardest"):
        puzzle = get_puzzle(name)
        assert is_valid_solution(HumanizerSolver().solve(puzzle.grid), given=puzzle.grid)


def test_fill_order_is_by_technique_not_raster():
    solver = HumanizerSolver()
    solver.solve(get_puzzle("physical_demo").grid)
    order = solver.placement_order
    assert order != sorted(order)                      # not row by row
    assert order != sorted(order, key=lambda rc: (rc[1], rc[0]))  # not column by column
    # The first cell filled is one of the most "obvious": its fullest unit is
    # at least as full as any other naked single's was at the start.
    state = _State.from_grid(get_puzzle("physical_demo").grid)
    singles = [cell for cell in state.empty_cells() if len(state.cands[cell[0]][cell[1]]) == 1]
    assert order[0] in singles
    assert state.obviousness(order[0]) == max(state.obviousness(c) for c in singles)


def test_extreme_puzzle_needs_guesses_and_marks_them():
    solver = HumanizerSolver()
    assert solver.solve(get_puzzle("inkala_hardest").grid) is not None
    stats = solver.stats
    assert stats["guesses"] > 0 and stats["guess_placements"] > 0
    assert stats["backtracks"] > 0                     # some guesses were wrong and undone
    guessed = [s for s in solver.placements if s.technique == GUESS]
    assert guessed and all(s.after_guess for s in guessed)
    # Logic after a guess is still labelled as logic, but flagged as conditional.
    after = [s for s in solver.placements if s.technique in LOGIC_TECHNIQUES and s.after_guess]
    assert after
    text = solver.format_steps()
    assert "[GUESS]" in text and "(after guess)" in text


def test_uses_far_less_search_than_backtracking_on_extreme_puzzle():
    grid = get_puzzle("inkala_hardest").grid
    human, brute = HumanizerSolver(), get_solver("backtracking")
    human.solve(grid)
    brute.solve(grid)
    assert human.stats["guesses"] * 10 < brute.stats["nodes_expanded"]


def test_step_log_is_human_readable():
    solver = HumanizerSolver()
    solver.solve(get_puzzle("physical_demo").grid)
    text = solver.format_steps()
    first = text.splitlines()[0]
    assert first.strip().startswith("1. r") and "[naked single]" in first
    assert "51 cell(s) by logic" in text
    assert solver.cell_techniques[solver.placement_order[0]] == NAKED_SINGLE


# -- Each technique, on hand-built candidate situations ----------------------------

def _blank_state():
    return _State.from_grid([[0] * 9 for _ in range(9)])


def test_naked_single_detected():
    state = _blank_state()
    state.cands[4][4] = {7}
    step = hz.find_naked_single(state)
    assert (step.technique, step.cell, step.digit) == (NAKED_SINGLE, (4, 4), 7)


def test_hidden_single_detected():
    state = _blank_state()
    for r, c in hz._BOXES[0]:
        state.cands[r][c].discard(5)
    state.cands[1][1].add(5)
    step = hz.find_hidden_single(state)
    assert (step.technique, step.cell, step.digit) == (HIDDEN_SINGLE, (1, 1), 5)


def test_naked_pair_eliminates_from_rest_of_unit():
    state = _blank_state()
    state.cands[0][0] = {1, 2}
    state.cands[0][5] = {1, 2}
    step = hz.find_naked_pair(state)
    assert step.technique == NAKED_PAIR
    removed = set(step.eliminations)
    assert ((0, 8), 1) in removed and ((0, 8), 2) in removed
    assert all(cell not in ((0, 0), (0, 5)) for cell, _d in removed)


def test_hidden_pair_strips_other_candidates():
    state = _blank_state()
    for c in range(9):
        if c not in (2, 6):
            state.cands[3][c] -= {4, 8}
    step = hz.find_hidden_pair(state)
    assert step.technique == HIDDEN_PAIR
    removed = set(step.eliminations)
    assert ((3, 2), 1) in removed and ((3, 6), 9) in removed
    assert not any(d in (4, 8) for _cell, d in removed)


def test_pointing_pair_eliminates_along_the_line():
    state = _blank_state()
    for r, c in hz._BOXES[0]:
        if r != 0:
            state.cands[r][c].discard(6)
    step = hz.find_pointing_pair(state)
    assert step.technique == POINTING_PAIR
    removed = set(step.eliminations)
    assert ((0, 3), 6) in removed and ((0, 8), 6) in removed
    assert all(cell[0] == 0 and cell[1] >= 3 for cell, _d in removed)


def test_box_line_reduction_eliminates_within_the_box():
    state = _blank_state()
    # 9 in row 1 is confined to box 1 (columns 1-3 only).
    for c in range(3, 9):
        state.cands[0][c].discard(9)
    step = hz.find_box_line_reduction(state)
    assert step.technique == BOX_LINE_REDUCTION
    removed = set(step.eliminations)
    assert ((1, 0), 9) in removed and ((2, 2), 9) in removed
    assert all(cell[0] in (1, 2) and cell[1] < 3 for cell, _d in removed)


def test_advanced_techniques_are_used_in_practice():
    used = set()
    for puzzle in PUZZLES:
        solver = HumanizerSolver()
        solver.solve(puzzle.grid)
        used |= {t for t, n in solver.stats["eliminations_by_technique"].items() if n}
    assert {NAKED_PAIR, HIDDEN_PAIR, POINTING_PAIR, BOX_LINE_REDUCTION} <= used


@pytest.mark.parametrize("name", ["physical_demo", "hard_1", "near_empty_17", "inkala_hardest"])
def test_every_step_used_the_simplest_technique_available(name):
    """Replay the whole log: before each step, no simpler technique may have applied anywhere,
    and a guess only ever happens when no technique applies at all."""
    solver = HumanizerSolver()
    solver.solve(get_puzzle(name).grid)
    order = [f.__name__ for f in hz._FINDERS]
    technique_of = dict(zip(order, hz.TECHNIQUES))
    rank = {t: i for i, t in enumerate(hz.TECHNIQUES)}
    rank[GUESS] = len(hz.TECHNIQUES)

    state = _State.from_grid(get_puzzle(name).grid)
    for step in solver.steps:
        for finder in hz._FINDERS[: rank[step.technique]]:
            assert finder(state) is None, (
                f"{technique_of[finder.__name__]} was available but {step.technique} was used: "
                f"{step.describe()}"
            )
        hz.apply_step(state, step)
    assert state.is_complete()
