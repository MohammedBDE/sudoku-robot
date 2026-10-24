"""
Locates the Sudoku grid within a captured camera frame and produces a
flat, top-down image of just the 9x9 grid -- undoing whatever angle
the camera happens to be mounted at. This matters here specifically:
the iPhone stand isn't overhead, so the paper shows up as a skewed
quadrilateral rather than a clean rectangle in a raw frame (see
calib/camera_test_frame.jpg).

This module only handles the geometry: find the grid, flatten the
perspective, slice it into 81 cell images. Reading the digit in each
cell is done separately by digit_recognizer.py, and vision/pipeline.py
chains the two (read_grid_from_frame / capture_and_read_grid).
"""
from typing import List

import cv2
import numpy as np


class GridDetectionError(Exception):
    """Raised when no plausible Sudoku grid could be found in a frame."""


def _order_corners(pts: np.ndarray) -> np.ndarray:
    """
    Order 4 points as [top-left, top-right, bottom-right, bottom-left].

    Standard trick: top-left has the smallest (x+y), bottom-right the
    largest (x+y); top-right has the smallest (y-x), bottom-left the
    largest (y-x).
    """
    pts = pts.reshape(4, 2).astype("float32")
    total = pts.sum(axis=1)
    diff = np.diff(pts, axis=1).reshape(-1)

    ordered = np.zeros((4, 2), dtype="float32")
    ordered[0] = pts[np.argmin(total)]  # top-left
    ordered[2] = pts[np.argmax(total)]  # bottom-right
    ordered[1] = pts[np.argmin(diff)]   # top-right
    ordered[3] = pts[np.argmax(diff)]   # bottom-left
    return ordered


def _largest_quad(contours, frame_area: float, min_area_ratio: float):
    """First contour (by descending area) that approximates a convex quadrilateral, or None."""
    for contour in sorted(contours, key=cv2.contourArea, reverse=True):
        area = cv2.contourArea(contour)
        if area < frame_area * min_area_ratio:
            break  # sorted descending -- nothing smaller is worth checking either
        perimeter = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
        if len(approx) == 4 and cv2.isContourConvex(approx):
            return approx
    return None


def _largest_quad_via_hull(contours, frame_area: float, min_area_ratio: float):
    """
    Fallback for when the grid's own border isn't one clean closed
    edge loop (a real failure seen on an actual photo: focus/lighting
    made Canny output a fragmented, jagged outline that approxPolyDP
    couldn't reduce to 4 points at all). Closing small gaps and taking
    the convex hull recovers a clean quadrilateral -- but it comes
    with a real trade-off, not just a quality knob: on a sheet with
    only a thin white margin between the grid's printed border and the
    paper's own edge, this can bridge past the grid border and lock
    onto the paper's outer edge instead, which throws off every
    downstream cell coordinate. It's a deliberate second choice, tried
    only after the precise method above finds nothing.
    """
    for contour in sorted(contours, key=cv2.contourArea, reverse=True):
        area = cv2.contourArea(contour)
        if area < frame_area * min_area_ratio:
            break
        hull = cv2.convexHull(contour)
        perimeter = cv2.arcLength(hull, True)
        approx = cv2.approxPolyDP(hull, 0.02 * perimeter, True)
        if len(approx) == 4:
            return approx
    return None


def find_grid_corners(frame: np.ndarray, min_area_ratio: float = 0.03) -> np.ndarray:
    """
    Find the 4 corners of the sudoku grid's own outer border in `frame`.

    Returns an ordered (top-left, top-right, bottom-right, bottom-left)
    array of (x, y) points. Raises GridDetectionError if nothing
    plausible is found.
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    # Edge detection, not thresholding: a Sudoku grid's outer border is
    # a strong, thin, high-contrast line against whatever it's sitting
    # on, which Canny picks out directly. An adaptive-threshold +
    # dilate approach was tried first and failed in practice -- it
    # segments by *brightness*, so it's thrown off by a floor that's
    # nearly as bright as the paper, and dilating to close gaps ends up
    # fusing the paper's outline together with nearby floor grout lines
    # or other objects into one useless blob. Skipping dilation and
    # using RETR_LIST (not RETR_EXTERNAL) matters too: the grid's own
    # printed border is often an *interior* edge relative to the full
    # sheet of paper, not the outermost contour in the frame.
    edges = cv2.Canny(blurred, 50, 150)
    frame_area = frame.shape[0] * frame.shape[1]

    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        raise GridDetectionError(
            "No edges found at all -- is there enough contrast "
            "between the puzzle grid and its background?"
        )

    approx = _largest_quad(contours, frame_area, min_area_ratio)
    if approx is None:
        # The precise pass found nothing usable -- try again allowing
        # small gaps in the border to be bridged (see
        # _largest_quad_via_hull's docstring for the trade-off this
        # accepts).
        closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        closed_contours, _ = cv2.findContours(closed, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        approx = _largest_quad_via_hull(closed_contours, frame_area, min_area_ratio)

    if approx is None:
        raise GridDetectionError(
            "Found edges, but none outlined a 4-cornered grid large enough "
            "to be the puzzle. Check: is the whole grid visible and "
            "unobstructed, is there good contrast against the background, "
            "and is the paper reasonably flat (not curled or folded)?"
        )
    return _order_corners(approx)


def warp_grid(frame: np.ndarray, corners: np.ndarray, output_size: int = 900) -> np.ndarray:
    """Perspective-correct `frame` so `corners` maps onto a flat output_size x output_size square."""
    destination = np.array(
        [[0, 0], [output_size - 1, 0], [output_size - 1, output_size - 1], [0, output_size - 1]],
        dtype="float32",
    )
    transform = cv2.getPerspectiveTransform(corners, destination)
    return cv2.warpPerspective(frame, transform, (output_size, output_size))


def locate_and_warp_grid(frame: np.ndarray, output_size: int = 900) -> np.ndarray:
    """Find the puzzle grid in `frame` and return a flat, top-down output_size x output_size image of it."""
    corners = find_grid_corners(frame)
    return warp_grid(frame, corners, output_size)


def split_into_cells(warped_grid: np.ndarray, margin_ratio: float = 0.12) -> List[List[np.ndarray]]:
    """
    Slice a flattened grid image (from locate_and_warp_grid) into its
    81 individual cell images, indexed [row][col].

    `margin_ratio` trims a bit off each cell's edges so the grid lines
    themselves (which sit right at cell boundaries) don't confuse
    whatever classifies the cell's digit later.
    """
    size = warped_grid.shape[0]
    cell_size = size / 9.0
    margin = cell_size * margin_ratio

    cells: List[List[np.ndarray]] = []
    for row in range(9):
        row_cells = []
        for col in range(9):
            y0 = int(row * cell_size + margin)
            y1 = int((row + 1) * cell_size - margin)
            x0 = int(col * cell_size + margin)
            x1 = int((col + 1) * cell_size - margin)
            row_cells.append(warped_grid[y0:y1, x0:x1])
        cells.append(row_cells)
    return cells
