import builtins

import pytest

from sudoku_robot.writer.arm_controller import ArmController, SimulatedArmController
from sudoku_robot.writer.digit_strokes import DIGIT_PATHS, DIGIT_STROKES
from sudoku_robot.writer.grid_layout import PlaceholderGridLayout
from sudoku_robot.writer.pen_writer import write_digit
from sudoku_robot.writer.pipeline import write_solution


def test_digit_strokes_cover_1_through_9():
    for digit in range(1, 10):
        strokes = DIGIT_STROKES[digit]
        assert len(strokes) > 0
        for (start, end) in strokes:
            for point in (start, end):
                x, y = point
                assert 0.0 <= x <= 1.0
                assert 0.0 <= y <= 1.0


def test_grid_layout_gives_distinct_cell_centers():
    layout = PlaceholderGridLayout()
    centers = {layout.cell_center(r, c) for r in range(9) for c in range(9)}
    assert len(centers) == 81
    assert layout.cell_size_mm() > 0


def test_write_digit_is_one_continuous_stroke():
    arm = SimulatedArmController(log=False)
    layout = PlaceholderGridLayout()
    write_digit(arm, layout, row=0, col=0, digit=8)

    path_len = len(DIGIT_PATHS[8])
    # travel (pen up), drop (pen down), then pen-down through every
    # remaining path point, then one final lift -- no lifts in between.
    assert len(arm.moves) == path_len + 2

    pen_states = [pen_down for (_, _, pen_down) in arm.moves]
    assert pen_states == [False] + [True] * path_len + [False]


def test_write_digit_rejects_invalid_digit():
    arm = SimulatedArmController(log=False)
    layout = PlaceholderGridLayout()
    with pytest.raises(ValueError):
        write_digit(arm, layout, row=0, col=0, digit=0)


def test_write_solution_only_writes_solver_filled_cells():
    original = [[0] * 9 for _ in range(9)]
    original[0][0] = 5  # a pre-printed clue -- should NOT be written
    solved = [[1] * 9 for _ in range(9)]
    solved[0][0] = 5

    arm = SimulatedArmController(log=False)
    layout = PlaceholderGridLayout()
    ok = write_solution(original, solved, arm, layout, mode="digit")

    assert ok is True
    # 80 empty cells were written, each digit "1" costs (path_len + 2)
    # moves (travel, drop, path_len-1 draw moves, lift), plus one
    # home() move bookending the run at each end.
    moves_per_digit = len(DIGIT_PATHS[1]) + 2
    expected = 80 * moves_per_digit + 2
    assert len(arm.moves) == expected


def test_simulated_arm_never_prompts_for_confirmation(monkeypatch):
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("input() should not be called for a simulated arm")

    monkeypatch.setattr(builtins, "input", fail_if_called)

    original = [[0] * 9 for _ in range(9)]
    solved = [[1] * 9 for _ in range(9)]
    ok = write_solution(original, solved, SimulatedArmController(log=False), PlaceholderGridLayout())
    assert ok is True


class _FakePhysicalArm(SimulatedArmController):
    """A stand-in "physical" arm that still just records moves, so the
    safety-confirmation gate can be tested without real hardware."""

    is_physical = True


def test_physical_arm_write_is_blocked_without_confirmation(monkeypatch):
    monkeypatch.setattr(builtins, "input", lambda *_: "no")

    original = [[0] * 9 for _ in range(9)]
    solved = [[1] * 9 for _ in range(9)]
    arm = _FakePhysicalArm(log=False)
    ok = write_solution(original, solved, arm, PlaceholderGridLayout())

    assert ok is False
    assert arm.connected is False
    assert arm.moves == []


def test_physical_arm_write_proceeds_after_confirmation(monkeypatch):
    monkeypatch.setattr(builtins, "input", lambda *_: "yes")

    original = [[0] * 9 for _ in range(9)]
    solved = [[1] * 9 for _ in range(9)]
    arm = _FakePhysicalArm(log=False)
    ok = write_solution(original, solved, arm, PlaceholderGridLayout())

    assert ok is True
    assert len(arm.moves) > 0


def test_physical_arm_write_with_auto_confirm_skips_prompt(monkeypatch):
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("input() should not be called when auto_confirm=True")

    monkeypatch.setattr(builtins, "input", fail_if_called)

    original = [[0] * 9 for _ in range(9)]
    solved = [[1] * 9 for _ in range(9)]
    arm = _FakePhysicalArm(log=False)
    ok = write_solution(original, solved, arm, PlaceholderGridLayout(), auto_confirm=True)

    assert ok is True


def test_writer_module_does_not_import_solver():
    # Enforces the "modular from the solver" requirement: the writer
    # package should work on a plain Grid, without knowing or caring
    # which solving strategy produced it.
    import ast
    import inspect

    from sudoku_robot import writer

    for module in (writer.pipeline, writer.pen_writer, writer.arm_controller, writer.grid_layout):
        source = inspect.getsource(module)
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = getattr(node, "module", "") or ""
                names += "".join(alias.name for alias in node.names)
                assert "solver" not in names, f"{module.__name__} should not import the solver package"


# -- mark mode, default mode, skip-on-ArmMotionError, home position ---------

from sudoku_robot import config  # noqa: E402
from sudoku_robot.writer.arm_controller import ArmMotionError  # noqa: E402
from sudoku_robot.writer.pen_writer import mark_cell  # noqa: E402
from sudoku_robot.writer.pipeline import DEFAULT_WRITE_MODE  # noqa: E402


def _two_empty_cells():
    original = [[5] * 9 for _ in range(9)]
    original[0][0] = 0
    original[4][4] = 0
    solved = [[5] * 9 for _ in range(9)]
    solved[0][0] = 1
    solved[4][4] = 7
    return original, solved


def test_mark_cell_presses_straight_down_without_lateral_motion():
    arm = SimulatedArmController(log=False)
    layout = PlaceholderGridLayout()
    mark_cell(arm, layout, 3, 5)
    center = layout.cell_center(3, 5)
    assert arm.moves == [(*center, False), (*center, True), (*center, False)]


def test_write_solution_mark_mode_marks_each_empty_cell_once():
    original, solved = _two_empty_cells()
    arm = SimulatedArmController(log=False)
    layout = PlaceholderGridLayout()
    assert write_solution(original, solved, arm, layout, mode="mark") is True

    home = (*config.DEFAULT_HOME_XY, False)
    c00, c44 = layout.cell_center(0, 0), layout.cell_center(4, 4)
    assert arm.moves == [
        home,
        (*c00, False), (*c00, True), (*c00, False),
        (*c44, False), (*c44, True), (*c44, False),
        home,
    ]


def test_default_write_mode_is_mark_everywhere():
    import inspect

    from sudoku_robot.cli import build_parser

    assert DEFAULT_WRITE_MODE == "mark"
    assert inspect.signature(write_solution).parameters["mode"].default == DEFAULT_WRITE_MODE
    assert build_parser().parse_args([]).write_mode == DEFAULT_WRITE_MODE


def test_write_solution_rejects_unknown_mode():
    original, solved = _two_empty_cells()
    with pytest.raises(ValueError):
        write_solution(original, solved, SimulatedArmController(log=False), PlaceholderGridLayout(), mode="scribble")


class _FailingAtCellArm(SimulatedArmController):
    """Simulated arm whose pen-down move at one target raises ArmMotionError, like an unreachable cell."""

    def __init__(self, bad_xy):
        super().__init__(log=False)
        self.bad_xy = bad_xy
        self.homes = 0

    def move(self, x, y, pen_down):
        if pen_down and (x, y) == self.bad_xy:
            raise ArmMotionError("simulated error 33")
        super().move(x, y, pen_down)

    def home(self):
        self.homes += 1
        super().home()


def test_write_solution_skips_cell_on_arm_motion_error_and_continues(capsys):
    original, solved = _two_empty_cells()
    layout = PlaceholderGridLayout()
    arm = _FailingAtCellArm(bad_xy=layout.cell_center(0, 0))

    assert write_solution(original, solved, arm, layout, mode="mark") is True

    c44 = layout.cell_center(4, 4)
    assert (*c44, True) in arm.moves          # the reachable cell was still written
    assert arm.homes == 3                     # start, re-home after the failure, end
    assert not arm.connected                  # always disconnected afterwards
    out = capsys.readouterr().out
    assert "[skip] cell (0,0)" in out
    assert "1 cell(s) skipped" in out


def test_simulated_home_matches_real_arm_home():
    import inspect

    from sudoku_robot.writer.arm_controller import MyCobotArmController

    arm = SimulatedArmController(log=False)
    arm.home()
    assert arm.moves == [(*config.DEFAULT_HOME_XY, False)]
    assert inspect.signature(MyCobotArmController).parameters["home_xy"].default == config.DEFAULT_HOME_XY


def test_main_pipeline_never_imports_hand_teaching_module():
    import subprocess
    import sys

    code = (
        "import sys, sudoku_robot.cli, sudoku_robot.writer;"
        "sys.exit(1 if 'sudoku_robot.writer.teach' in sys.modules else 0)"
    )
    assert subprocess.run([sys.executable, "-c", code]).returncode == 0


def test_write_solution_follows_a_given_cell_order():
    original, solved = _two_empty_cells()
    arm = SimulatedArmController(log=False)
    layout = PlaceholderGridLayout()
    write_solution(original, solved, arm, layout, mode="mark", order=[(4, 4), (0, 0)])
    pressed = [(x, y) for (x, y, down) in arm.moves if down]
    assert pressed == [layout.cell_center(4, 4), layout.cell_center(0, 0)]


def test_write_solution_rejects_an_order_that_misses_or_adds_cells():
    original, solved = _two_empty_cells()
    for bad in ([(0, 0)], [(0, 0), (4, 4), (1, 1)], [(0, 0), (0, 0)]):
        with pytest.raises(ValueError):
            write_solution(original, solved, SimulatedArmController(log=False), PlaceholderGridLayout(),
                           mode="mark", order=bad)


def test_humanizer_order_drives_the_pen_but_not_the_strokes():
    from sudoku_robot.puzzles.samples import get_puzzle
    from sudoku_robot.solver.humanizer import HumanizerSolver

    puzzle = get_puzzle("physical_demo")
    solver = HumanizerSolver()
    solved = solver.solve(puzzle.grid)
    layout = PlaceholderGridLayout()

    human = SimulatedArmController(log=False)
    write_solution(puzzle.grid, solved, human, layout, mode="digit", order=solver.placement_order)
    raster = SimulatedArmController(log=False)
    write_solution(puzzle.grid, solved, raster, layout, mode="digit")

    # Same moves (identical digit strokes), different visiting order.
    assert sorted(human.moves) == sorted(raster.moves)
    assert human.moves != raster.moves
