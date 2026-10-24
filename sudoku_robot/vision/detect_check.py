"""
Visual test for grid detection: runs it against an already-captured
frame (no camera/network needed -- point it at any .jpg from
capture_check.py) and saves debug images so detection can be checked
by eye before trusting it in a real pipeline.

Run with:

    python -m sudoku_robot.vision.detect_check
    python -m sudoku_robot.vision.detect_check --frame some_other_frame.jpg

By default it reads calib/camera_test_frame.jpg (what capture_check
saves) and writes calib/grid_debug_{corners,warped,cells}.jpg.
"""
import argparse
import os
import sys

import cv2

from .. import config
from .grid_detector import GridDetectionError, find_grid_corners, split_into_cells, warp_grid

DEFAULT_FRAME = os.path.join(config.CALIB_DIR, "camera_test_frame.jpg")
DEFAULT_OUT_PREFIX = os.path.join(config.CALIB_DIR, "grid_debug")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Debug grid detection against a saved frame.")
    parser.add_argument(
        "--frame", default=DEFAULT_FRAME,
        help=f"Path to a captured frame to test against (default: {DEFAULT_FRAME}).",
    )
    parser.add_argument(
        "--out-prefix", default=DEFAULT_OUT_PREFIX,
        help=f"Path prefix for the debug images written out (default: {DEFAULT_OUT_PREFIX}).",
    )
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    frame = cv2.imread(args.frame)
    if frame is None:
        print(f"Could not read image: {args.frame}", file=sys.stderr)
        return 1

    try:
        corners = find_grid_corners(frame)
    except GridDetectionError as e:
        print(f"Grid detection failed:\n{e}", file=sys.stderr)
        return 1

    # Draw the detected outline/corners on the original frame so a
    # wrong detection (e.g. it locked onto the robot base instead of
    # the paper) is obvious at a glance.
    overlay = frame.copy()
    cv2.polylines(overlay, [corners.astype(int)], isClosed=True, color=(0, 0, 255), thickness=4)
    for (x, y) in corners.astype(int):
        cv2.circle(overlay, (x, y), 10, (0, 255, 0), -1)
    os.makedirs(os.path.dirname(os.path.abspath(args.out_prefix)), exist_ok=True)
    overlay_path = f"{args.out_prefix}_corners.jpg"
    cv2.imwrite(overlay_path, overlay)

    warped = warp_grid(frame, corners)
    warped_path = f"{args.out_prefix}_warped.jpg"
    cv2.imwrite(warped_path, warped)

    cells = split_into_cells(warped)
    grid_overlay = warped.copy()
    size = grid_overlay.shape[0]
    for i in range(10):
        pos = int(i * size / 9)
        cv2.line(grid_overlay, (pos, 0), (pos, size), (0, 255, 0), 2)
        cv2.line(grid_overlay, (0, pos), (size, pos), (0, 255, 0), 2)
    cells_path = f"{args.out_prefix}_cells.jpg"
    cv2.imwrite(cells_path, grid_overlay)

    print(f"Detected corners (top-left, top-right, bottom-right, bottom-left):\n{corners.tolist()}")
    print(f"Extracted {len(cells)}x{len(cells[0])} cell images.")
    print(f"Saved: {overlay_path} (detection overlay), {warped_path} (flattened grid), "
          f"{cells_path} (cell boundaries on flattened grid)")
    print("Check all three: did it find the actual paper, is the warped grid square "
          "and undistorted, and do the green lines line up with the printed grid lines?")
    return 0


if __name__ == "__main__":
    sys.exit(main())
