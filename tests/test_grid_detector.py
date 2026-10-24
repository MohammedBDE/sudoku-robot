import numpy as np
import pytest

cv2 = pytest.importorskip("cv2", reason="opencv-python-headless not installed (pip install -r requirements.txt)")

from sudoku_robot.vision.grid_detector import (
    GridDetectionError,
    _order_corners,
    find_grid_corners,
    split_into_cells,
    warp_grid,
)


def test_order_corners_sorts_scrambled_points():
    # top-left, top-right, bottom-right, bottom-left, but shuffled
    scrambled = np.array([[100, 100], [0, 0], [100, 0], [0, 100]], dtype="float32")
    ordered = _order_corners(scrambled)

    assert list(ordered[0]) == [0, 0]      # top-left
    assert list(ordered[1]) == [100, 0]    # top-right
    assert list(ordered[2]) == [100, 100]  # bottom-right
    assert list(ordered[3]) == [0, 100]    # bottom-left


def _synthetic_grid_frame(size=600, square_size=400, margin_noise=True):
    """A black square outline on a noisy gray background, standing in for a photographed grid."""
    frame = np.full((size, size, 3), 90, dtype=np.uint8)
    if margin_noise:
        rng = np.random.default_rng(0)
        noise = rng.integers(-15, 15, frame.shape, dtype=np.int16)
        frame = np.clip(frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    top_left = ((size - square_size) // 2, (size - square_size) // 2)
    bottom_right = (top_left[0] + square_size, top_left[1] + square_size)
    cv2.rectangle(frame, top_left, bottom_right, color=(250, 250, 250), thickness=-1)
    cv2.rectangle(frame, top_left, bottom_right, color=(20, 20, 20), thickness=4)
    return frame, top_left, bottom_right


def test_find_grid_corners_locates_a_synthetic_square():
    frame, top_left, bottom_right = _synthetic_grid_frame()
    corners = find_grid_corners(frame)

    assert corners.shape == (4, 2)
    xs, ys = corners[:, 0], corners[:, 1]
    # Allow a little slack for the border thickness/antialiasing.
    assert abs(xs.min() - top_left[0]) < 10
    assert abs(ys.min() - top_left[1]) < 10
    assert abs(xs.max() - bottom_right[0]) < 10
    assert abs(ys.max() - bottom_right[1]) < 10


def test_find_grid_corners_raises_on_blank_frame():
    blank = np.full((400, 400, 3), 128, dtype=np.uint8)
    with pytest.raises(GridDetectionError):
        find_grid_corners(blank)


def test_warp_grid_produces_requested_size():
    frame, _, _ = _synthetic_grid_frame()
    corners = find_grid_corners(frame)
    warped = warp_grid(frame, corners, output_size=450)
    assert warped.shape[:2] == (450, 450)


def test_split_into_cells_returns_9x9_nonempty_images():
    frame, _, _ = _synthetic_grid_frame()
    corners = find_grid_corners(frame)
    warped = warp_grid(frame, corners, output_size=450)
    cells = split_into_cells(warped)

    assert len(cells) == 9
    for row in cells:
        assert len(row) == 9
        for cell in row:
            assert cell.size > 0
