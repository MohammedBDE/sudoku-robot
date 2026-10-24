"""
Turns "draw digit D in cell (row, col)" into a sequence of ArmController
moves, by scaling the normalised digit strokes (digit_strokes.py) onto
a real cell (grid_layout.py) and tracing them with the pen.
"""
from .arm_controller import ArmController
from .digit_strokes import DIGIT_PATHS
from .grid_layout import GridLayout

#: Digit is drawn at this fraction of the cell's size, so it doesn't
#: touch the printed grid lines on either side.
DEFAULT_FILL_RATIO = 0.8


def write_digit(
    arm: ArmController,
    layout: GridLayout,
    row: int,
    col: int,
    digit: int,
    fill_ratio: float = DEFAULT_FILL_RATIO,
) -> None:
    """
    Move the arm to cell (row, col) and draw `digit` (1-9) there as one
    continuous pen-down stroke (see DIGIT_PATHS's docstring for why:
    lifting between segments turned out to visibly misalign them on
    real hardware, since the arm's repeatability between separate
    touch-downs is a large fraction of one segment's length).
    """
    if digit not in DIGIT_PATHS:
        raise ValueError(f"No stroke definition for digit {digit!r} (expected 1-9)")

    cx, cy = layout.cell_center(row, col)
    size = layout.cell_size_mm() * fill_ratio
    (right_x, right_y), (up_x, up_y) = layout.cell_axes()

    # Map each unit-square point (u, v) onto the paper's actual
    # orientation: u steps along "right as printed", v steps along "up
    # as printed" -- not the arm's raw X/Y axes, which don't line up
    # with the paper unless it happens to be laid perfectly square to
    # the arm's base.
    path = []
    for (u, v) in DIGIT_PATHS[digit]:
        du, dv = (u - 0.5) * size, (v - 0.5) * size
        x = cx + du * right_x + dv * up_x
        y = cy + du * right_y + dv * up_y
        path.append((x, y))

    arm.move(*path[0], pen_down=False)  # travel to the digit's start point
    arm.move(*path[0], pen_down=True)   # drop the pen once
    for (x, y) in path[1:]:
        arm.move(x, y, pen_down=True)   # keep drawing, no lifts in between
    arm.move(*path[-1], pen_down=False)  # lift only at the very end


def mark_cell(arm: ArmController, layout: GridLayout, row: int, col: int) -> None:
    """
    Travel to cell (row, col) and press the pen straight down once,
    then lift straight back up. No lateral motion happens with the
    pen down, so this doesn't depend on the arm's stroke-to-stroke
    precision at all -- only on it reaching the right cell and making
    contact. Use it as the conservative option, e.g. for a first test of
    a new paper placement, before drawing full digits.
    """
    cx, cy = layout.cell_center(row, col)
    arm.move(cx, cy, pen_down=False)  # travel, pen up
    arm.move(cx, cy, pen_down=True)   # press straight down
    arm.move(cx, cy, pen_down=False)  # lift straight back up
