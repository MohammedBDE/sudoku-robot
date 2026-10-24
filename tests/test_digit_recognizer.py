import pytest

cv2 = pytest.importorskip("cv2", reason="opencv-python-headless not installed (pip install -r requirements.txt)")
import numpy as np
from PIL import Image, ImageDraw

from sudoku_robot import fonts
from sudoku_robot.vision.digit_recognizer import is_cell_empty, recognize_digit

CELL_SIZE = 80


def _render_cell(digit) -> np.ndarray:
    """A synthetic cell image: either blank, or a digit in the project's own font, like a real crop."""
    img = Image.new("L", (CELL_SIZE, CELL_SIZE), color=255)  # white background
    if digit != 0:
        draw = ImageDraw.Draw(img)
        font = fonts.load_font(round(CELL_SIZE * 0.6), bold=True)
        draw.text((CELL_SIZE / 2, CELL_SIZE / 2), str(digit), font=font, fill=0, anchor="mm")
    gray = np.array(img)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)


def test_recognizes_every_digit_in_its_own_font():
    # This is the easy case (own font, no photo noise/perspective) --
    # the real accuracy test is against an actual photographed puzzle,
    # done manually during development (see digit_recognizer.py's
    # docstring for that validation and the bugs it caught). This test
    # just guards against a regression breaking the basic case.
    for digit in range(1, 10):
        cell = _render_cell(digit)
        assert recognize_digit(cell) == digit


def test_blank_cell_is_empty_and_recognized_as_zero():
    cell = _render_cell(0)
    assert is_cell_empty(cell)
    assert recognize_digit(cell) == 0


def test_uniform_gray_cell_is_empty():
    # No contrast at all -- guards the std-based short-circuit that
    # fixed a real bug where Otsu produced ~76% "ink" on a flat cell.
    cell = np.full((CELL_SIZE, CELL_SIZE, 3), 200, dtype=np.uint8)
    assert is_cell_empty(cell)
