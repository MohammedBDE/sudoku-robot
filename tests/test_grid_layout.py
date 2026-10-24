import json
import math

import pytest

from sudoku_robot import config
from sudoku_robot.writer.corner_check import check_corners
from sudoku_robot.writer.grid_layout import PlaceholderGridLayout, TaughtCornersGridLayout


def _close(a, b, tol=1e-6):
    return all(abs(x - y) < tol for x, y in zip(a, b))


def _square_corners(tl=(80.0, -250.0), cell=20.0):
    """Correctly taught corners (cell centres) for an unrotated grid, per the config.py convention."""
    return {
        "TL": [tl[0], tl[1], 100.0, 0, 0, 0],
        "TR": [tl[0] - 8 * cell, tl[1], 100.0, 0, 0, 0],   # col -> -X
        "BL": [tl[0], tl[1] + 8 * cell, 100.0, 0, 0, 0],   # row -> +Y
    }


# -- TaughtCornersGridLayout ------------------------------------------------

def test_taught_layout_reproduces_taught_corners_when_taught_correctly():
    c = _square_corners()
    layout = TaughtCornersGridLayout(tuple(c["TL"][:2]), tuple(c["TR"][:2]), tuple(c["BL"][:2]))
    assert _close(layout.cell_center(0, 0), c["TL"][:2])
    assert _close(layout.cell_center(0, 8), c["TR"][:2])
    assert _close(layout.cell_center(8, 0), c["BL"][:2])
    # The untaught 4th corner follows from the other three.
    assert _close(layout.cell_center(8, 8), (80.0 - 160.0, -250.0 + 160.0))


def test_taught_layout_forces_ruler_cell_size_but_keeps_direction():
    # Corners taught short (edges 100mm instead of 160mm), rotated 30 degrees.
    a = math.radians(30)
    right = (math.cos(a), math.sin(a))
    down = (-math.sin(a), math.cos(a))
    tl = (10.0, -200.0)
    tr = (tl[0] + 100 * right[0], tl[1] + 100 * right[1])
    bl = (tl[0] + 100 * down[0], tl[1] + 100 * down[1])
    layout = TaughtCornersGridLayout(tl, tr, bl, cell_size_mm=20.0)

    step_col = [layout.cell_center(0, 1)[i] - layout.cell_center(0, 0)[i] for i in range(2)]
    step_row = [layout.cell_center(1, 0)[i] - layout.cell_center(0, 0)[i] for i in range(2)]
    assert math.hypot(*step_col) == pytest.approx(20.0)
    assert math.hypot(*step_row) == pytest.approx(20.0)
    assert _close(step_col, (20 * right[0], 20 * right[1]))

    axis_right, axis_up = layout.cell_axes()
    assert _close(axis_right, right)
    assert _close(axis_up, (-down[0], -down[1]))
    assert layout.cell_size_mm() == 20.0


def test_taught_layout_from_corners_file(tmp_path):
    path = tmp_path / "corners.json"
    path.write_text(json.dumps(_square_corners()))
    layout = TaughtCornersGridLayout.from_corners_file(str(path))
    assert _close(layout.cell_center(0, 0), (80.0, -250.0))
    assert _close(layout.cell_center(4, 4), (0.0, -170.0))


def test_taught_layout_rejects_coincident_corners():
    with pytest.raises(ValueError):
        TaughtCornersGridLayout((0.0, -200.0), (0.0, -200.0), (0.0, -100.0))


# -- PlaceholderGridLayout follows the documented convention ----------------

def test_placeholder_layout_follows_project_axis_convention():
    layout = PlaceholderGridLayout()
    x00, y00 = layout.cell_center(0, 0)
    x01, _ = layout.cell_center(0, 1)
    _, y10 = layout.cell_center(1, 0)
    assert x01 < x00          # increasing col -> -X (right)
    assert y10 > y00          # increasing row -> +Y (toward the base)
    assert y00 < 0            # the paper is in front of the base (-Y)
    assert layout.cell_axes() == ((-1.0, 0.0), (0.0, -1.0))


def test_placeholder_layout_is_entirely_within_reach():
    layout = PlaceholderGridLayout()
    corners = {
        "TL": list(layout.cell_center(0, 0)),
        "TR": list(layout.cell_center(0, 8)),
        "BL": list(layout.cell_center(8, 0)),
    }
    assert check_corners(corners).ok


def test_home_position_is_over_the_placeholder_grid():
    layout = PlaceholderGridLayout()
    hx, hy = config.DEFAULT_HOME_XY
    xs = [layout.cell_center(0, c)[0] for c in (0, 8)]
    ys = [layout.cell_center(r, 0)[1] for r in (0, 8)]
    assert min(xs) <= hx <= max(xs)
    assert min(ys) <= hy <= max(ys)
