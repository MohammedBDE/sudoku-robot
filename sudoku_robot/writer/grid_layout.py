"""
Maps a Sudoku (row, col) cell to a real-world (x, y) coordinate on the
paper, in millimetres, in the arm's own coordinate frame.

All coordinates follow the project-wide convention documented in
sudoku_robot/config.py: viewed from behind the arm's base, -Y is
"forward" (toward the paper's top edge), +X is left, -X is right. With
the puzzle laid upright in front of the arm, row 0 is farthest from
the base (most negative Y) and col 0 is leftmost (most positive X), so
increasing row -> +Y and increasing col -> -X.

This is deliberately the *only* place that knows where the grid is on
the table. Everything else in `writer/` (stroke drawing, the write
pipeline) asks a `GridLayout` for coordinates and never hardcodes a
position itself -- so swapping in camera-calibrated coordinates later
means writing one new class (e.g. a future `vision.CameraGridLayout`)
and passing it in, not touching any other file.
"""
import json
from abc import ABC, abstractmethod
from typing import Tuple

from .. import config


class GridLayout(ABC):
    @abstractmethod
    def cell_center(self, row: int, col: int) -> Tuple[float, float]:
        """(x, y) in mm of the centre of cell (row, col), row/col in 0..8."""
        raise NotImplementedError

    @abstractmethod
    def cell_size_mm(self) -> float:
        """Edge length of one cell, in mm (assumed square)."""
        raise NotImplementedError

    @abstractmethod
    def cell_axes(self) -> Tuple[Tuple[float, float], Tuple[float, float]]:
        """
        Unit vectors, in the arm's (x, y) frame, for "one step right"
        and "one step up" *as printed on the paper* -- i.e. the
        direction of increasing column and the direction of
        decreasing row, respectively.

        Needed because the paper isn't necessarily aligned with the
        arm's own X/Y axes (a rotated or skewed sheet is normal, not
        an edge case). `pen_writer.py` uses these to orient a digit's
        strokes to the paper's actual rotation -- mapping a digit's
        local (u, v) unit square straight onto global (x, y) instead
        drew a "vertical" line at whatever angle the arm's Y axis
        happens to be, which on a rotated sheet is not vertical on the
        paper at all -- confirmed on real hardware where a straight
        single-stroke "1" came out spanning most of the width of two
        columns instead of running the height of one.
        """
        raise NotImplementedError


class PlaceholderGridLayout(GridLayout):
    """
    An idealised, square-on grid used for SIMULATED runs only (the CLI
    uses TaughtCornersGridLayout for the real arm). It follows the
    project coordinate convention exactly:

        increasing col -> -X (to the right), increasing row -> +Y (toward the base)

    The default origin puts cell (0,0)'s centre at (80, -250): the
    9 columns span X = +80 ... -80 (centred on the arm's own
    centreline) and the 9 rows span Y = -250 (far) ... -90 (near), so
    every cell -- including half a cell of margin around it -- lies
    inside the arm's 280mm reach. The simulated arm's home position,
    config.DEFAULT_HOME_XY = (0, -220), sits over this area, matching
    the real arm's.

    These are sensible, reach-checked numbers, not a measurement of
    where any real sheet of paper is. Earlier versions of this class
    assumed the rows ran along +X; that contradicted both the
    empirically confirmed jog directions (jog_console.py) and the
    hand-taught corners.json, and was replaced.
    """

    def __init__(
        self,
        origin_mm: Tuple[float, float] = (80.0, -250.0),
        cell_size_mm: float = config.CELL_SIZE_MM,
    ):
        # origin_mm is the centre of cell (row=0, col=0) -- the
        # puzzle's farthest, leftmost cell -- in the arm's (X, Y) frame.
        self.origin_x, self.origin_y = origin_mm
        self._cell_size_mm = cell_size_mm

    def cell_center(self, row: int, col: int) -> Tuple[float, float]:
        x = self.origin_x - col * self._cell_size_mm
        y = self.origin_y + row * self._cell_size_mm
        return (x, y)

    def cell_size_mm(self) -> float:
        return self._cell_size_mm

    def cell_axes(self) -> Tuple[Tuple[float, float], Tuple[float, float]]:
        # Increasing col -> -X ("right"); decreasing row -> -Y ("up" on paper).
        return ((-1.0, 0.0), (0.0, -1.0))


class TaughtCornersGridLayout(GridLayout):
    """
    Builds the 81 cell centers by affine interpolation between 3
    hand-taught points: the CENTRES of the top-left cell (row=0,col=0),
    top-right cell (row=0,col=8), and bottom-left cell (row=8,col=0) --
    so each taught edge spans 8 cell pitches. The 4th corner is never
    needed -- 3 points fully determine an affine map (translation + 2
    basis vectors), and a flat sheet of paper on a rigid arm has no
    perspective distortion for a 4th point to correct, unlike a camera
    image. The taught points are in the arm frame described in
    config.py; the class works for any rotation of the sheet.

    Coordinates come from `get_coords()` with the arm's servos powered
    -- scripts/jog_console.py (`save TL` / `save TR` / `save BL`) is the
    recommended way to teach them, since it moves in precise small
    steps and holds position. (Hand-guiding requires
    release_all_servos(), never power_off(), which stops get_coords()
    from working -- see writer/teach.py.)

    Row/col basis *directions* come from the taught corners, but their
    *length* is forced to a known ruler-measured cell size rather than
    trusting the raw corner-to-corner distance / 8, so a corner taught
    slightly short doesn't compound its error across all 8 steps.

    That normalisation can't fix a corner that's badly wrong, though:
    a wrong *direction* shears the whole grid. Validate corners.json
    with `python -m sudoku_robot --check-corners` (writer/corner_check.py)
    -- the CLI refuses real-arm writes when it fails.
    """

    def __init__(
        self,
        top_left: Tuple[float, float],
        top_right: Tuple[float, float],
        bottom_left: Tuple[float, float],
        cell_size_mm: float = config.CELL_SIZE_MM,
    ):
        self.top_left = top_left
        raw_col = tuple((top_right[i] - top_left[i]) / 8.0 for i in range(2))
        raw_row = tuple((bottom_left[i] - top_left[i]) / 8.0 for i in range(2))
        col_len = (raw_col[0] ** 2 + raw_col[1] ** 2) ** 0.5
        row_len = (raw_row[0] ** 2 + raw_row[1] ** 2) ** 0.5
        if col_len == 0 or row_len == 0:
            raise ValueError("taught corners coincide -- re-teach corners.json")
        self.col_vec = tuple(raw_col[i] / col_len * cell_size_mm for i in range(2))
        self.row_vec = tuple(raw_row[i] / row_len * cell_size_mm for i in range(2))
        self._cell_size_mm = cell_size_mm

    @classmethod
    def from_corners_file(cls, path: str = config.CORNERS_PATH,
                          cell_size_mm: float = config.CELL_SIZE_MM) -> "TaughtCornersGridLayout":
        with open(path) as fh:
            data = json.load(fh)
        return cls(
            top_left=tuple(data["TL"][:2]),
            top_right=tuple(data["TR"][:2]),
            bottom_left=tuple(data["BL"][:2]),
            cell_size_mm=cell_size_mm,
        )

    def cell_center(self, row: int, col: int) -> Tuple[float, float]:
        x = self.top_left[0] + row * self.row_vec[0] + col * self.col_vec[0]
        y = self.top_left[1] + row * self.row_vec[1] + col * self.col_vec[1]
        return (x, y)

    def cell_size_mm(self) -> float:
        return self._cell_size_mm

    def cell_axes(self) -> Tuple[Tuple[float, float], Tuple[float, float]]:
        col_len = (self.col_vec[0] ** 2 + self.col_vec[1] ** 2) ** 0.5
        row_len = (self.row_vec[0] ** 2 + self.row_vec[1] ** 2) ** 0.5
        right = tuple(self.col_vec[i] / col_len for i in range(2))
        up = tuple(-self.row_vec[i] / row_len for i in range(2))
        return (right, up)
