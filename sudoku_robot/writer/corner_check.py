"""
Sanity-checks the hand-taught grid corners in config/corners.json before the
real arm is allowed to write with them.

corners.json holds three arm poses taught at the CENTRES of the grid's
three corner cells -- TL = cell (0, 0), TR = cell (0, 8), BL = cell
(8, 0) -- which is what TaughtCornersGridLayout assumes (it divides each
edge by 8 cell pitches). So on a correctly taught 9x9 grid of 20mm
cells:

    |TL -> TR| ~= 8 * 20mm = 160mm   (col pitch * (cols - 1))
    |TL -> BL| ~= 8 * 20mm = 160mm   (row pitch * (rows - 1))
    angle(TL->TR, TL->BL) ~= 90 degrees

It also maps all 81 cells through TaughtCornersGridLayout (exactly the
targets the arm would be sent to) and flags any whose footprint falls
outside the arm's commandable/reachable area.

Run with:

    python -m sudoku_robot --check-corners
    python -m sudoku_robot.writer.corner_check [--corners-file PATH]

Exit code 0 = everything within tolerance, 1 = re-teach needed.
"""
import argparse
import json
import math
import os
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .. import config
from .grid_layout import TaughtCornersGridLayout

GRID_CELLS = 9

#: Allowed relative error on each edge length (5% of 160mm = 8mm).
DEFAULT_LENGTH_TOLERANCE = 0.05
#: Allowed deviation of the TL corner angle from 90 degrees.
DEFAULT_ANGLE_TOLERANCE_DEG = 3.0


@dataclass
class CornerCheckReport:
    expected_edge_mm: float
    top_edge_mm: float           # |TL -> TR|
    left_edge_mm: float          # |TL -> BL|
    corner_angle_deg: float      # angle between TL->TR and TL->BL
    length_tolerance: float
    angle_tolerance_deg: float
    #: (row, col, x, y, reason) for every cell the arm can't safely reach.
    unreachable_cells: List[Tuple[int, int, float, float, str]] = field(default_factory=list)

    @property
    def top_edge_ok(self) -> bool:
        return abs(self.top_edge_mm - self.expected_edge_mm) <= self.expected_edge_mm * self.length_tolerance

    @property
    def left_edge_ok(self) -> bool:
        return abs(self.left_edge_mm - self.expected_edge_mm) <= self.expected_edge_mm * self.length_tolerance

    @property
    def angle_ok(self) -> bool:
        return abs(self.corner_angle_deg - 90.0) <= self.angle_tolerance_deg

    @property
    def reach_ok(self) -> bool:
        return not self.unreachable_cells

    @property
    def ok(self) -> bool:
        return self.top_edge_ok and self.left_edge_ok and self.angle_ok and self.reach_ok


def _cell_unreachable_reason(
    x: float, y: float, margin: float, coord_limit: float, max_reach: float
) -> Optional[str]:
    if abs(x) + margin > coord_limit or abs(y) + margin > coord_limit:
        return f"outside the +/-{coord_limit:.0f}mm X/Y command limit"
    radius = math.hypot(x, y)
    if radius + margin > max_reach:
        return f"{radius:.0f}mm from the base axis (max reach {max_reach:.0f}mm)"
    return None


def check_corners(
    corners: Dict[str, Sequence[float]],
    cell_size_mm: float = config.CELL_SIZE_MM,
    length_tolerance: float = DEFAULT_LENGTH_TOLERANCE,
    angle_tolerance_deg: float = DEFAULT_ANGLE_TOLERANCE_DEG,
    coord_limit_mm: float = config.ARM_COORD_LIMIT_MM,
    max_reach_mm: float = config.ARM_MAX_REACH_MM,
    reach_margin_mm: Optional[float] = None,
) -> CornerCheckReport:
    """
    Validate a corners dict ({"TL": [x, y, ...], "TR": [...], "BL": [...]}).

    `reach_margin_mm` (default: half a cell) is added to each cell
    centre's distance so a cell only passes if the whole cell -- where
    the pen actually draws -- is reachable, not just its centre point.
    """
    for key in ("TL", "TR", "BL"):
        if key not in corners:
            raise ValueError(f"corners is missing '{key}' (need TL, TR and BL)")
    tl, tr, bl = (tuple(corners[k][:2]) for k in ("TL", "TR", "BL"))

    top = (tr[0] - tl[0], tr[1] - tl[1])
    left = (bl[0] - tl[0], bl[1] - tl[1])
    top_len = math.hypot(*top)
    left_len = math.hypot(*left)
    if top_len == 0 or left_len == 0:
        raise ValueError("two taught corners are identical -- re-teach corners.json")
    cos_angle = (top[0] * left[0] + top[1] * left[1]) / (top_len * left_len)
    angle = math.degrees(math.acos(max(-1.0, min(1.0, cos_angle))))

    report = CornerCheckReport(
        expected_edge_mm=(GRID_CELLS - 1) * cell_size_mm,
        top_edge_mm=top_len,
        left_edge_mm=left_len,
        corner_angle_deg=angle,
        length_tolerance=length_tolerance,
        angle_tolerance_deg=angle_tolerance_deg,
    )

    margin = cell_size_mm / 2 if reach_margin_mm is None else reach_margin_mm
    layout = TaughtCornersGridLayout(tl, tr, bl, cell_size_mm=cell_size_mm)
    for row in range(GRID_CELLS):
        for col in range(GRID_CELLS):
            x, y = layout.cell_center(row, col)
            reason = _cell_unreachable_reason(x, y, margin, coord_limit_mm, max_reach_mm)
            if reason:
                report.unreachable_cells.append((row, col, x, y, reason))
    return report


def check_corners_file(path: Optional[str] = None, **kwargs) -> CornerCheckReport:
    path = path or config.CORNERS_PATH
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"No corners file at {path}. Teach it with `python scripts/jog_console.py` "
            "(save TL / save TR / save BL)." + config.legacy_location_hint(path)
        )
    with open(path) as fh:
        return check_corners(json.load(fh), **kwargs)


def format_report(report: CornerCheckReport, path: str = "") -> str:
    def mark(ok: bool) -> str:
        return "OK  " if ok else "FAIL"

    tol_mm = report.expected_edge_mm * report.length_tolerance
    lines = [f"Corner check{f' for {path}' if path else ''}:"]
    lines.append(
        f"  [{mark(report.top_edge_ok)}] TL->TR (top edge):  {report.top_edge_mm:7.1f}mm  "
        f"expected {report.expected_edge_mm:.1f} +/- {tol_mm:.1f}mm"
    )
    lines.append(
        f"  [{mark(report.left_edge_ok)}] TL->BL (left edge): {report.left_edge_mm:7.1f}mm  "
        f"expected {report.expected_edge_mm:.1f} +/- {tol_mm:.1f}mm"
    )
    lines.append(
        f"  [{mark(report.angle_ok)}] corner angle:       {report.corner_angle_deg:7.1f}deg "
        f"expected 90.0 +/- {report.angle_tolerance_deg:.1f}deg"
    )
    n_bad = len(report.unreachable_cells)
    lines.append(f"  [{mark(report.reach_ok)}] reachable cells:    {81 - n_bad}/81")
    for row, col, x, y, reason in report.unreachable_cells:
        lines.append(f"         cell ({row},{col}) -> ({x:7.1f}, {y:7.1f}): {reason}")

    if report.ok:
        lines.append("All checks passed.")
    else:
        lines.append(
            "\nRE-TEACH NEEDED: corners.json does not describe a square 9x9 grid of "
            f"{report.expected_edge_mm / (GRID_CELLS - 1):.0f}mm cells within the arm's reach.\n"
            "Easiest fix: `python scripts/place_paper.py` on the Pi plans a square, fully reachable grid\n"
            "and has the arm point at each corner while you slide the paper into place.\n"
            "Or, to keep the paper where it is: `python scripts/jog_console.py`, jog the pen onto the\n"
            "CENTRE of cell (0,0), (0,8) and (8,0) in turn, and `save TL` / `save TR` / `save BL`.\n"
            "(If cells are out of reach, the paper is too far from the base.)"
        )
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate corners.json geometry and reach.")
    parser.add_argument("--corners-file", default=config.CORNERS_PATH)
    args = parser.parse_args(argv)
    report = check_corners_file(args.corners_file)
    print(format_report(report, args.corners_file))
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
