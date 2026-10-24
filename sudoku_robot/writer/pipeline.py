"""
The full solve-to-paper pipeline: given the original (unsolved) grid
and a solved grid -- from *either* solving strategy, since both return
the same plain Grid type -- find every cell the solver filled in and
physically write each digit there.

    write_solution(original_grid, solved_grid, arm, layout)

`arm` and `layout` are passed in rather than constructed here, which
is what keeps this module decoupled from both the solver package (it
never imports BacktrackingSolver/RLSolver -- it only cares that
`solved_grid` is a Grid) and from real hardware (SimulatedArmController
and PlaceholderGridLayout are what the CLI uses for simulated runs,
MyCobotArmController and TaughtCornersGridLayout for real ones;
nothing here hardcodes either). Digit shapes always come from
digit_strokes.py -- the optional hand-teaching tool (writer/teach.py,
teach_data/) is deliberately not used here.
"""
from typing import List, Optional, Sequence, Tuple

from ..utils import Grid
from .arm_controller import ArmController, ArmMotionError
from .grid_layout import GridLayout
from .pen_writer import mark_cell, write_digit

#: "digit" draws the full seven-segment digit (pen_writer.write_digit);
#: "mark" presses the pen straight down once per cell (pen_writer.mark_cell).
WRITE_MODES = ("digit", "mark")

#: The one default shared by write_solution() and the CLI's --write-mode.
#: "mark" is the conservative default: it involves no lateral motion with
#: the pen down, so it only depends on reaching the right cell and making
#: contact. "digit" has also been run end to end on the real arm; it needs
#: well-calibrated corners and pen pressure to stay legible, so opt into
#: it explicitly (--write-mode digit).
DEFAULT_WRITE_MODE = "mark"


def _empty_cells(original_grid: Grid) -> List[Tuple[int, int]]:
    return [(r, c) for r in range(9) for c in range(9) if original_grid[r][c] == 0]


def _confirm_physical_move(num_cells: int) -> bool:
    """
    Blocks and asks a human to confirm before any real hardware moves.

    This only runs for a physical ArmController (see `is_physical` on
    ArmController) -- there is nothing to confirm before a simulated
    run, since it never leaves Python.
    """
    print("=" * 60)
    print("SAFETY CHECK: about to move a PHYSICAL robot arm.")
    print(f"Plan: write {num_cells} digit(s) onto paper.")
    print("Make sure: the workspace is clear, paper is positioned under")
    print("the pen, the pen is loaded, and you're ready to hit e-stop /")
    print("power off if the arm moves somewhere it shouldn't.")
    print("=" * 60)
    answer = input("Type 'yes' to proceed with the physical write: ").strip().lower()
    return answer == "yes"


def write_solution(
    original_grid: Grid,
    solved_grid: Grid,
    arm: ArmController,
    layout: GridLayout,
    auto_confirm: bool = False,
    mode: str = DEFAULT_WRITE_MODE,
    order: Optional[Sequence[Tuple[int, int]]] = None,
) -> bool:
    """
    Write every solver-filled cell of `solved_grid` onto paper.

    Args:
        original_grid: the puzzle as given (0 = empty). Only cells
            that were empty here get written -- pre-printed clues are
            left alone.
        solved_grid: the completed grid from either solver's `solve()`.
        arm: where to send moves (SimulatedArmController by default
            elsewhere in the project; MyCobotArmController for real
            hardware).
        layout: maps cell -> real (x, y). Swap in a camera-calibrated
            GridLayout later without changing this function.
        auto_confirm: skip the interactive physical-safety prompt.
            Only meaningful for a physical arm -- use with care, and
            only once you already trust the calibration. Simulated
            runs never prompt regardless of this flag.
        mode: "digit" draws the full digit shape (pen_writer.write_digit);
            "mark" just presses the pen straight down once per cell
            (pen_writer.mark_cell) -- no lateral motion while down, so
            it doesn't depend on stroke-to-stroke precision. Use "mark"
            when the hardware/calibration can't reliably produce
            legible digit shapes but can reliably reach the right cell.
            Defaults to DEFAULT_WRITE_MODE ("mark") -- see its comment.
        order: the sequence to visit the empty cells in. Default: row by
            row. Must contain every empty cell exactly once. The CLI
            passes the Humanizer solver's placement_order here, so the
            pen fills cells in the order a person solving it would --
            only the visiting order changes, never how a digit is drawn.

    Returns:
        True if writing happened, False if it was aborted at the
        safety confirmation step.
    """
    if mode not in WRITE_MODES:
        raise ValueError(f"mode must be 'digit' or 'mark', got {mode!r}")

    empty_cells = _empty_cells(original_grid)
    if order is not None:
        order = [tuple(cell) for cell in order]
        if sorted(order) != empty_cells:
            raise ValueError("order must list every empty cell of original_grid exactly once")
        empty_cells = order
    if not empty_cells:
        print("Nothing to write -- the puzzle had no empty cells.")
        return True

    if arm.is_physical and not auto_confirm:
        if not _confirm_physical_move(len(empty_cells)):
            print("Aborted: physical write was not confirmed.")
            return False

    skipped: List[Tuple[int, int]] = []
    arm.connect()
    try:
        arm.home()
        for (r, c) in empty_cells:
            try:
                if mode == "digit":
                    write_digit(arm, layout, r, c, solved_grid[r][c])
                else:
                    mark_cell(arm, layout, r, c)
            except ArmMotionError as e:
                # Some cells can be genuinely out of the arm's physical
                # reach depending on where the paper sits (its ~280mm
                # working radius, not a software limit) -- skipping one
                # unreachable cell and continuing gets the rest of the
                # puzzle done instead of losing the whole run to it.
                # arm.home() re-establishes a known-safe pose before
                # continuing, since the failure leaves position unknown
                # relative to what the next cell's move expects.
                print(f"[skip] cell ({r},{c}) unreachable, continuing: {e}")
                skipped.append((r, c))
                arm.home()
        arm.home()
    finally:
        arm.disconnect()

    if skipped:
        print(f"\n{len(skipped)} cell(s) skipped as unreachable: {skipped}")

    return True
