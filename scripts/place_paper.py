"""
Plan a fully reachable grid position and have the arm show where the
paper goes -- the easy alternative to hand-teaching config/corners.json.

    python scripts/place_paper.py                 # plan + write corners.json, then guide with the REAL arm
    python scripts/place_paper.py --plan-only     # plan + write corners.json + print instructions, no arm
    python scripts/place_paper.py --simulate      # the whole flow on the simulated arm (no prompts)
    python scripts/place_paper.py --keep-corners  # don't re-plan: just hover over the CURRENT corners
                                                  # (a quick visual check of any corners.json)
    python scripts/place_paper.py --center-y -160 --rotation 5   # a different planned position

The existing config/corners.json is backed up (config/corners.backup-<time>.json)
before a planned one replaces it. See sudoku_robot/writer/placement.py.
"""
import argparse
import os
import sys

# Run as a plain script (python scripts/<name>.py), so put the project root --
# the folder containing the sudoku_robot package -- on the import path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sudoku_robot import config  # noqa: E402
from sudoku_robot.writer import placement  # noqa: E402
from sudoku_robot.writer.arm_controller import MyCobotArmController, SimulatedArmController  # noqa: E402
from sudoku_robot.writer.corner_check import check_corners, check_corners_file, format_report  # noqa: E402
from sudoku_robot.writer.grid_layout import TaughtCornersGridLayout  # noqa: E402


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Plan a reachable grid and guide the paper into place.")
    p.add_argument("--center-x", type=float, default=placement.DEFAULT_CENTER[0],
                   help="grid centre X in mm (+ = left of the base), default %(default)s")
    p.add_argument("--center-y", type=float, default=placement.DEFAULT_CENTER[1],
                   help="grid centre Y in mm (more negative = farther from the base), default %(default)s")
    p.add_argument("--rotation", type=float, default=0.0, help="grid rotation in degrees, default 0")
    p.add_argument("--clearance", type=float, default=placement.DEFAULT_CLEARANCE_MM,
                   help="how far above the paper the pen stops, mm (default %(default)s)")
    p.add_argument("--keep-corners", action="store_true",
                   help="don't plan: hover over the corners already in config/corners.json")
    p.add_argument("--plan-only", action="store_true", help="write corners.json and print instructions; no arm")
    p.add_argument("--simulate", action="store_true", help="use the simulated arm (no hardware, no prompts)")
    p.add_argument("--yes", action="store_true", help="skip the physical-safety confirmation")
    args = p.parse_args(argv)

    if args.keep_corners:
        report = check_corners_file(config.CORNERS_PATH)
        print(format_report(report, config.CORNERS_PATH))
    else:
        corners = placement.plan_corners((args.center_x, args.center_y), args.rotation)
        report = check_corners({k: v for k, v in corners.items() if k in ("TL", "TR", "BL")})
        print(format_report(report, "planned corners"))
        if not report.ok:
            print("\nThat position isn't fully reachable -- move --center-y closer to the base "
                  "(less negative) or reduce --rotation. corners.json was NOT changed.", file=sys.stderr)
            return 1
        backup = placement.write_planned_corners(corners)
        print(f"\nWrote planned corners to {config.CORNERS_PATH}"
              + (f"\n(previous file backed up to {backup})" if backup else ""))

    layout = TaughtCornersGridLayout.from_corners_file(config.CORNERS_PATH)
    print("\n" + placement.placement_instructions(layout, args.clearance))
    if args.plan_only:
        return 0

    if args.simulate:
        arm = SimulatedArmController()
        placement.guide_paper_placement(arm, layout, args.clearance, wait=print)
        return 0

    if not args.yes:
        print("\nSAFETY: the arm will move and hold the pen just ABOVE the paper (it never presses down).")
        if input("Type 'yes' to start: ").strip().lower() != "yes":
            print("Aborted.")
            return 1
    arm = MyCobotArmController()
    placement.guide_paper_placement(arm, layout, args.clearance)
    print("\nDone. Validate and test:  python -m sudoku_robot --check-corners")
    return 0


if __name__ == "__main__":
    sys.exit(main())
