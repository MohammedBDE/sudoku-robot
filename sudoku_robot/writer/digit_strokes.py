"""
Hand-writable stroke paths for the digits 1-9, defined on a normalised
unit square (0,0) = bottom-left, (1,1) = top-right, so they're
independent of cell size/position -- `pen_writer.py` scales and
translates them onto a real cell later.

Each digit is built out of straight-line "segments" using the same
seven-segment layout as a digital clock display:

        TL-------TR
        |          |
        |          |
        ML---------MR
        |          |
        |          |
        BL---------BR

Straight lines only (no curves) because that's what's easy and
reliable for an arm to draw accurately -- and seven-segment digits are
still perfectly legible. The pen writer draws each digit from DIGIT_PATHS
below: ONE continuous pen-down path through the segment corner points
(the pen lifts only at the start and the end), because lifting between
segments misaligned them on real hardware. DIGIT_STROKES, the same
digits split into independent single-segment strokes, is kept for
reference only; the writer does not use it.
"""
from typing import Dict, List, Tuple

Point = Tuple[float, float]
Stroke = Tuple[Point, Point]  # (start, end) -- a single straight segment

# The seven corner/midpoint anchors of the seven-segment layout.
_TL, _TR = (0.0, 1.0), (1.0, 1.0)
_ML, _MR = (0.0, 0.5), (1.0, 0.5)
_BL, _BR = (0.0, 0.0), (1.0, 0.0)

_SEGMENTS: Dict[str, Stroke] = {
    "top": (_TL, _TR),
    "top_left": (_TL, _ML),
    "top_right": (_TR, _MR),
    "middle": (_ML, _MR),
    "bottom_left": (_ML, _BL),
    "bottom_right": (_MR, _BR),
    "bottom": (_BL, _BR),
}

# Standard seven-segment encodings. Only 1-9 are defined -- 0 is not a
# legal Sudoku digit (0 means "empty" in this project's Grid type), so
# there's nothing that should ever ask to write it.
_DIGIT_SEGMENTS: Dict[int, List[str]] = {
    1: ["top_right", "bottom_right"],
    2: ["top", "top_right", "middle", "bottom_left", "bottom"],
    3: ["top", "top_right", "middle", "bottom_right", "bottom"],
    4: ["top_left", "top_right", "middle", "bottom_right"],
    5: ["top", "top_left", "middle", "bottom_right", "bottom"],
    6: ["top", "top_left", "middle", "bottom_left", "bottom_right", "bottom"],
    7: ["top", "top_right", "bottom_right"],
    8: ["top", "top_left", "top_right", "middle", "bottom_left", "bottom_right", "bottom"],
    9: ["top", "top_left", "top_right", "middle", "bottom_right", "bottom"],
}

# What pen_writer.py actually consumes: digit -> list of (start, end) strokes.
DIGIT_STROKES: Dict[int, List[Stroke]] = {
    digit: [_SEGMENTS[name] for name in names] for digit, names in _DIGIT_SEGMENTS.items()
}

# Each digit's segments walked as ONE continuous polyline (a single
# pen-down run), instead of independent lift-travel-drop strokes per
# segment. This matters more than it looks like it should: on real
# hardware, drawing each segment as its own independent stroke means
# the pen lifts and re-lands at every shared vertex between segments,
# and the arm's repeatability between separate touch-downs (~2-3mm in
# practice) is a large fraction of a single segment's length (as
# little as 8mm) -- enough to visibly misalign two segments that are
# supposed to meet exactly, which is what "looks like it drew the
# stroke twice, offset" on paper actually was. A continuous run only
# lifts once at the very start and once at the very end, so segment
# junctions are never re-landed at all.
#
# These were derived by hand as an Eulerian (or near-Eulerian) walk of
# each digit's segment graph -- most digits trace every required
# segment exactly once with no retracing; digits 3 and 4 need one
# short out-and-back retrace of a single segment (their segment graphs
# have 4 odd-degree vertices, one more pair than a clean Euler path
# allows for, so one edge has to be walked twice to connect everything
# in a single run).
DIGIT_PATHS: Dict[int, List[Point]] = {
    1: [_TR, _MR, _BR],
    2: [_TL, _TR, _MR, _ML, _BL, _BR],
    3: [_TL, _TR, _MR, _ML, _MR, _BR, _BL],
    4: [_TL, _ML, _MR, _TR, _MR, _BR],
    5: [_TR, _TL, _ML, _MR, _BR, _BL],
    6: [_TR, _TL, _ML, _MR, _BR, _BL, _ML],
    7: [_TL, _TR, _MR, _BR],
    8: [_ML, _TL, _TR, _MR, _BR, _BL, _ML, _MR],
    9: [_BL, _BR, _MR, _ML, _TL, _TR, _MR],
}
