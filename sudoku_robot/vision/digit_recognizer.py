"""
Reads the digit (or blank) in each of the 81 cell images produced by
grid_detector.split_into_cells().

Why template matching instead of a general OCR engine (e.g.
Tesseract): installing system packages on this Pi needs a sudo
password this session doesn't have, so pulling in `tesseract-ocr` via
apt isn't an option right now. But that's not actually a loss here --
every puzzle this project prints comes from its own `puzzles/render.py`,
in one known font (DejaVu Sans Bold). Since we control the exact
appearance of every digit we'll ever need to read back, comparing a
cell directly against a rendered reference of each digit 1-9 is both
simpler and more reliable than general-purpose OCR would be for this
narrow case.

Trade-off, stated plainly: this WILL NOT reliably read a puzzle from a
different source (a printed newspaper puzzle, a different font, a
handwritten grid). That's fine for solving what this project prints,
but if reading arbitrary puzzles matters later, swap this module for
real OCR (pytesseract) or a trained digit classifier -- nothing
outside this file needs to change, since it's used only through
recognize_grid(cells) -> Grid.
"""
import warnings
from functools import lru_cache
from typing import Dict, List

import cv2
import numpy as np
from PIL import Image, ImageDraw

from .. import fonts
from ..utils import Grid

TEMPLATE_SIZE = 100
#: Cells are normalized onto a canvas larger than the template, purely
#: to give matchTemplate room to slide and find the best alignment
#: (see _normalize_ink's docstring for why a same-size comparison
#: doesn't work).
CELL_CANVAS_SIZE = 140
# The template font is looked up via sudoku_robot.fonts (DejaVu Sans
# Bold, the same font puzzles/render.py prints with), lazily on first
# use -- not at import time, and never via a hardcoded Linux path.

#: Below this fraction of "ink" pixels, a cell is considered blank
#: rather than attempting (and risking a false-positive) match.
EMPTY_INK_RATIO = 0.02

#: A blank cell is nearly flat grayscale (empirically ~1-2 std on real
#: photos); a cell with a printed digit has real contrast (~40+ std).
#: This check has to run BEFORE Otsu thresholding, not after: Otsu
#: assumes a bimodal (ink vs. background) histogram, and a genuinely
#: flat/blank cell doesn't have one -- it still picks *some* threshold
#: regardless, which on real captured cells produced nonsense "ink"
#: ratios as high as 76% on cells that were actually blank paper.
MIN_STD_FOR_CONTENT = 12.0


#: How heavily a mismatch in ink bounding-box aspect ratio (width /
#: height) counts against an otherwise-plausible template match. This
#: exists because pixel correlation alone can be a near-tie between
#: visually related digits (a photographed "1" scored 0.65 against its
#: own template and 0.66 against "4"). Aspect ratio is a cheap, mostly
#: independent signal -- a "1" is reliably narrower than a "4" even
#: when their normalized pixel overlap is ambiguous -- so it's used to
#: break exactly those near-ties rather than to drive scoring on its
#: own. The exact weight is chosen so a large aspect gap (~0.15,
#: roughly what separates "1" from "4" in this project's font) can
#: flip a near-tie, without overriding a template match that's
#: actually decisive.
ASPECT_PENALTY_WEIGHT = 0.15


def _largest_ink_contour(binary_cell: np.ndarray):
    contours, _ = cv2.findContours(binary_cell, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    return max(contours, key=cv2.contourArea)


def _ink_bounding_box(binary: np.ndarray):
    """(x, y, w, h) of the largest ink contour, or None if the image has no ink at all."""
    contour = _largest_ink_contour(binary)
    if contour is None:
        return None
    return cv2.boundingRect(contour)


def _normalize_ink(binary: np.ndarray, bbox, canvas_size: int = TEMPLATE_SIZE) -> np.ndarray:
    """
    Crop to `bbox`, scale it to fill ~70% of a TEMPLATE_SIZE box by its
    longest side (preserving aspect ratio), and center it on a
    `canvas_size` x `canvas_size` canvas.

    The ink is always scaled relative to the fixed TEMPLATE_SIZE, not
    to `canvas_size` -- a bigger canvas just adds blank padding around
    an identically-scaled digit, which is what gives matchTemplate
    room to slide (see recognize_digit). Get the ink itself scaled
    inconsistently between templates and cells, and matching breaks in
    a way that's easy to miss: a first version normalized cells this
    way but used raw, un-normalized PIL glyph renders as templates,
    and every single "1" in a real test puzzle was misread as "4",
    because a font's glyph metrics differ per character ("1" is
    narrow, "8" is wide) so the two sides were never at comparable
    scale even though nothing raised an error about it.
    """
    if bbox is None:
        return np.zeros((canvas_size, canvas_size), dtype=np.uint8)

    x, y, w, h = bbox
    ink = binary[y : y + h, x : x + w]

    scale = (TEMPLATE_SIZE * 0.7) / max(w, h)
    resized = cv2.resize(ink, (max(1, round(w * scale)), max(1, round(h * scale))))

    canvas = np.zeros((canvas_size, canvas_size), dtype=np.uint8)
    rh, rw = resized.shape
    top = (canvas_size - rh) // 2
    left = (canvas_size - rw) // 2
    canvas[top : top + rh, left : left + rw] = resized
    return canvas


def _render_digit_template(digit: int):
    """Render `digit` in the same font puzzles/render.py uses; return (normalized image, ink aspect ratio)."""
    img = Image.new("L", (TEMPLATE_SIZE, TEMPLATE_SIZE), color=0)  # black background
    draw = ImageDraw.Draw(img)
    # Rendered oversized on purpose -- _normalize_ink crops to the
    # actual ink and rescales anyway, so what matters is resolution
    # (avoiding a blocky/aliased source glyph), not fitting the canvas.
    font = fonts.load_font(round(TEMPLATE_SIZE * 1.2), bold=True)
    draw.text((TEMPLATE_SIZE / 2, TEMPLATE_SIZE / 2), str(digit), font=font, fill=255, anchor="mm")
    raw = np.array(img)
    _, binary = cv2.threshold(raw, 127, 255, cv2.THRESH_BINARY)
    bbox = _ink_bounding_box(binary)
    _, _, w, h = bbox
    return _normalize_ink(binary, bbox, canvas_size=TEMPLATE_SIZE), w / h


@lru_cache(maxsize=1)
def get_templates() -> Dict[int, tuple]:
    """
    digit -> (normalized template image, ink aspect ratio).

    Built once, on first use (not at import time), then cached --
    rendering text with PIL is cheap and the templates never change
    within a run. Warns if the reference font (DejaVu Sans Bold) isn't
    available: templates rendered in a substitute font will still
    work, but less reliably against puzzles printed in DejaVu.
    """
    if not fonts.is_reference_font(bold=True):
        warnings.warn(
            "DejaVu Sans Bold not found; digit templates use "
            f"{fonts.describe_font(bold=True)} instead, which may not match "
            "puzzles printed by puzzles/render.py. See sudoku_robot/fonts.py.",
            RuntimeWarning,
            stacklevel=2,
        )
    return {digit: _render_digit_template(digit) for digit in range(1, 10)}


def _cell_binary(cell_bgr: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(cell_bgr, cv2.COLOR_BGR2GRAY)
    # OTSU picks the threshold automatically per-cell, which copes
    # with lighting variation across the sheet far better than one
    # fixed global threshold would.
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return binary


def is_cell_empty(cell_bgr: np.ndarray) -> bool:
    gray = cv2.cvtColor(cell_bgr, cv2.COLOR_BGR2GRAY)
    if gray.std() < MIN_STD_FOR_CONTENT:
        return True
    binary = _cell_binary(cell_bgr)
    ink_ratio = np.count_nonzero(binary) / binary.size
    return ink_ratio < EMPTY_INK_RATIO


def recognize_digit(cell_bgr: np.ndarray) -> int:
    """Return 0 for a blank cell, or the recognized digit 1-9."""
    if is_cell_empty(cell_bgr):
        return 0

    binary = _cell_binary(cell_bgr)
    bbox = _ink_bounding_box(binary)
    normalized = _normalize_ink(binary, bbox, canvas_size=CELL_CANVAS_SIZE)
    _, _, w, h = bbox
    cell_aspect = w / h

    def combined_score(template_img: np.ndarray, template_aspect: float) -> float:
        # .max() over the whole result, not a single fixed position:
        # the cell canvas is deliberately larger than the template
        # (see CELL_CANVAS_SIZE) so this is a real sliding search over
        # candidate alignments, not a single same-size comparison that
        # would be brittle to a few pixels of centering error.
        match_score = cv2.matchTemplate(normalized, template_img, cv2.TM_CCOEFF_NORMED).max()
        aspect_penalty = ASPECT_PENALTY_WEIGHT * abs(cell_aspect - template_aspect)
        return match_score - aspect_penalty

    scores = {
        digit: combined_score(template_img, template_aspect)
        for digit, (template_img, template_aspect) in get_templates().items()
    }
    return max(scores, key=scores.get)


def recognize_grid(cells: List[List[np.ndarray]]) -> Grid:
    """Apply recognize_digit to all 81 cells from split_into_cells(). Returns a 9x9 Grid."""
    return [[recognize_digit(cell) for cell in row] for row in cells]
