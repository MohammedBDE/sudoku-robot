"""
Planned paper placement: instead of teaching corners.json to wherever
the paper happens to lie, PLAN a grid position that is square, exactly
20mm per cell, and fully inside the arm's reach -- then let the arm show
where the paper goes.

    1. plan_corners()            computes TL/TR/BL for a grid centred at
                                 `center` (default: 170mm in front of the
                                 base, on its centreline), optionally rotated
    2. write_planned_corners()   saves them to config/corners.json (the old
                                 file is backed up first)
    3. guide_paper_placement()   the real arm hovers the pen a few mm above
                                 the centre of each corner cell in turn;
                                 the person slides the sheet so the pen tip
                                 sits over each cell centre, then tapes it

Why this works better than hand-teaching: the geometry is exact by
construction (it always passes `--check-corners`), and aligning paper
under a pen that is held still is far easier and more precise than
steering a heavy arm onto a printed point. The fourth corner (cell 9,9)
is shown last as a check -- if TL, TR and BL line up but it doesn't,
the sheet wasn't printed at 100% scale.

Coordinates follow the convention in config.py: -Y is forward (away
from the base), +X is left; row 0 is farthest from the base.
"""
import json
import math
import os
import shutil
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

from .. import config
from .arm_controller import ArmController
from .grid_layout import GridLayout

#: Grid centre (cell r5c5) in the arm frame. With 20mm cells this puts the
#: grid's far edge 260mm out and its near edge 80mm out, centred left/right:
#: every cell, with half a cell of margin, is inside the 280mm reach.
DEFAULT_CENTER: Tuple[float, float] = (0.0, -170.0)
#: How far above the paper the pen tip stops while showing a corner.
DEFAULT_CLEARANCE_MM = 3.0

#: (label, (row, col)) of the cells the arm points at, in order. BR is a check only.
PLACEMENT_TARGETS: List[Tuple[str, Tuple[int, int]]] = [
    ("TL", (0, 0)),
    ("TR", (0, 8)),
    ("BL", (8, 0)),
    ("BR", (8, 8)),
]


def plan_corners(
    center: Tuple[float, float] = DEFAULT_CENTER,
    rotation_deg: float = 0.0,
    cell_size_mm: float = config.CELL_SIZE_MM,
    calibration: Optional[config.ArmCalibration] = None,
) -> Dict[str, list]:
    """
    Corner-cell centres for a square grid centred at `center`, rotated by
    `rotation_deg` (counter-clockwise seen from above). Returned in
    corners.json's format: {"TL": [x, y, z, rx, ry, rz], ...}.
    """
    calibration = calibration or config.load_arm_calibration()
    t = math.radians(rotation_deg)
    # Unrotated: one column right = -X, one row down (toward the base) = +Y.
    right = (-math.cos(t), -math.sin(t))
    down = (-math.sin(t), math.cos(t))
    cx, cy = center
    tl = (cx - 4 * cell_size_mm * (right[0] + down[0]), cy - 4 * cell_size_mm * (right[1] + down[1]))
    tr = (tl[0] + 8 * cell_size_mm * right[0], tl[1] + 8 * cell_size_mm * right[1])
    bl = (tl[0] + 8 * cell_size_mm * down[0], tl[1] + 8 * cell_size_mm * down[1])

    def pose(xy):
        return [round(xy[0], 2), round(xy[1], 2), calibration.pen_down_z, *calibration.orientation]

    return {
        "TL": pose(tl),
        "TR": pose(tr),
        "BL": pose(bl),
        "_note": (
            f"PLANNED by scripts/place_paper.py (grid centre {cx:.1f}, {cy:.1f} mm, rotation "
            f"{rotation_deg:.1f} deg, {cell_size_mm:.0f}mm cells). Align the paper to it with "
            "scripts/place_paper.py; re-run that (or re-teach with jog_console.py) if the paper moves."
        ),
    }


def write_planned_corners(corners: Dict[str, list], path: Optional[str] = None) -> Optional[str]:
    """Write corners to `path` (default config/corners.json). Backs up an existing file; returns the backup path."""
    path = path or config.CORNERS_PATH
    backup = None
    if os.path.exists(path):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = os.path.join(os.path.dirname(path), f"corners.backup-{stamp}.json")
        shutil.copy2(path, backup)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(corners, fh, indent=2)
        fh.write("\n")
    return backup


def placement_instructions(layout: GridLayout, clearance_mm: float = DEFAULT_CLEARANCE_MM) -> str:
    lines = [
        "How to place the paper (about 5 minutes):",
        "  1. Print printable_puzzles/physical_demo.png at 100% / 'Actual size'; check one cell = 20 mm.",
        f"  2. The arm will hold the pen {clearance_mm:.0f} mm above each point below, one at a time.",
        "     Slide the sheet (grid upright as seen from behind the arm: row 1 farthest away)",
        "     until the pen tip is over the CENTRE of the named cell.",
    ]
    for label, (r, c) in PLACEMENT_TARGETS:
        x, y = layout.cell_center(r, c)
        what = "check only -- should already line up" if label == "BR" else "align"
        lines.append(f"       {label}: cell r{r + 1}c{c + 1} at arm ({x:7.1f}, {y:7.1f}) mm   [{what}]")
    lines += [
        "  3. Align TL first, then pivot the sheet around TL until TR lines up; tape it down.",
        "     BL should then line up by itself; BR confirms the print scale.",
        "  4. Test with dots only:  python -m sudoku_robot --puzzle physical_demo --write --real-arm",
    ]
    return "\n".join(lines)


def guide_paper_placement(
    arm: ArmController,
    layout: GridLayout,
    clearance_mm: float = DEFAULT_CLEARANCE_MM,
    wait: Callable[[str], object] = input,
) -> None:
    """Hover the pen over each corner cell in turn, waiting for the person to align the paper."""
    arm.connect()
    try:
        arm.home()
        for label, (r, c) in PLACEMENT_TARGETS:
            x, y = layout.cell_center(r, c)
            arm.hover(x, y, clearance_mm)
            action = "Check that the pen is over" if label == "BR" else "Slide the paper so the pen is over"
            wait(f"[{label}] {action} the centre of cell r{r + 1}c{c + 1}, then press Enter... ")
        arm.home()
    finally:
        arm.disconnect()
