"""
Computer vision: capturing a photo of the physical Sudoku board and
extracting the puzzle's digits from it, cell by cell.

Implemented, and validated against a real photographed puzzle (see
digit_recognizer.py's docstring for the calibration bugs that surfaced
along the way):

    camera_config.py    - resolves the iPhone's RTSP URL (explicit arg
                           > SUDOKU_ROBOT_RTSP_URL env var > config/camera_config.json)
    camera_source.py     - capture_frame(rtsp_url) -> a single BGR frame
    capture_check.py      - `python -m sudoku_robot.vision.capture_check`,
                           a standalone connectivity/quality check
    grid_detector.py      - find_grid_corners/warp_grid/split_into_cells:
                           locates the grid in a raw frame, perspective-
                           corrects it, and slices it into 81 cell images
    detect_check.py        - `python -m sudoku_robot.vision.detect_check`,
                           runs grid detection against a saved frame and
                           writes debug images to check it by eye
    digit_recognizer.py    - recognize_grid(cells) -> Grid: reads each
                           cell via template matching against this
                           project's own font (see its docstring for
                           why, and its real limitation: it won't
                           reliably read a puzzle in a different font)
    pipeline.py            - capture_and_read_grid(): the full camera
                           round-trip in one call, used by
                           `python -m sudoku_robot --from-camera`

The camera is only used to READ the puzzle. Where the arm WRITES is
decided separately: `--write --real-arm` uses TaughtCornersGridLayout
built from the hand-taught corners.json (validated by
`python -m sudoku_robot --check-corners`), and simulated runs use
PlaceholderGridLayout. So `--from-camera --write --real-arm` reads the
real puzzle from the photo but writes wherever corners.json says the
grid is -- the paper must sit exactly where the corners were taught.

Not built: a `CameraGridLayout` that would compute arm coordinates
from find_grid_corners()'s image corners. That needs a camera-to-arm
(hand-eye) calibration, which doesn't exist in this project.

Needs opencv-python-headless (cv2); the template font is DejaVu Sans
Bold, found via sudoku_robot.fonts (see that module for fallbacks).
"""
