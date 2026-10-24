"""
Ties the vision building blocks into the two calls anything outside
this package actually needs: read a grid from an already-captured
frame, or do the whole camera round-trip in one call.
"""
from typing import Optional

import numpy as np

from ..utils import Grid, grid_to_string, is_consistent_partial_grid
from .camera_config import resolve_rtsp_url
from .camera_source import capture_frame
from .digit_recognizer import recognize_grid
from .grid_detector import GridDetectionError, find_grid_corners, split_into_cells, warp_grid


def read_grid_from_frame(frame: np.ndarray) -> Grid:
    """
    Find the sudoku grid in `frame` and read its digits.

    Raises GridDetectionError if no grid is found, OR if one was found
    but the digits read back from it don't form a plausible partial
    Sudoku (a duplicate digit in some row/column/box) -- in practice
    this means detection locked onto the wrong region of the photo
    (see grid_detector.find_grid_corners's fallback-path docstring for
    a real example: a thin paper margin let it lock onto the sheet's
    outer edge instead of the grid's own border). Reporting that
    clearly here beats silently handing the solver, or the pen, a
    grid that isn't the puzzle that's actually on the table.
    """
    corners = find_grid_corners(frame)
    warped = warp_grid(frame, corners)
    cells = split_into_cells(warped)
    grid = recognize_grid(cells)

    if not is_consistent_partial_grid(grid):
        raise GridDetectionError(
            "Found a grid-shaped region and read digits from it, but they "
            "don't form a valid partial Sudoku (the same digit appears "
            "twice in some row, column, or box):\n"
            f"    {grid_to_string(grid)}\n"
            "This usually means detection locked onto the wrong region of "
            "the photo (e.g. the paper's outer edge instead of the grid's "
            "own border) rather than that recognition made a small mistake. "
            "Try retaking the photo with the grid clearly separated from "
            "the paper's edge, or with more consistent lighting/focus."
        )
    return grid


def capture_and_read_grid(rtsp_url: Optional[str] = None) -> Grid:
    """
    The full camera round-trip: resolve the RTSP URL, capture one
    frame, and read the grid from it. Raises CameraConfigError,
    CameraCaptureError, or GridDetectionError depending on what fails.
    """
    url = resolve_rtsp_url(rtsp_url)
    frame = capture_frame(url)
    return read_grid_from_frame(frame)
