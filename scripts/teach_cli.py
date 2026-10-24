"""
One-shot commands for the OPTIONAL hand-teaching tool (sudoku_robot.writer.teach),
run one at a time (no interactive terminal needed -- each call is a
fresh process, and state persists on disk between calls). The main
solve-and-write pipeline doesn't need any of this; see teach.py's
docstring for status and background.

    python scripts/teach_cli.py release-servos      # relax joints so the arm moves by hand (get_coords still works)
    python scripts/teach_cli.py capture-surface     # pen on paper -> pen_down_z + orientation in config/arm_calibration.json
    python scripts/teach_cli.py capture-box-origin
    python scripts/teach_cli.py capture-point --digit 3 --segment top --which start
    python scripts/teach_cli.py capture-point --digit 3 --segment top --which end
    python scripts/teach_cli.py finish-digit --digit 3
    python scripts/teach_cli.py record-path --digit 3 [--max-wait 20]
    python scripts/teach_cli.py show-digit --digit 3
    python scripts/teach_cli.py lock-servos         # re-engage the servos when done (alias: power-on)

    python scripts/teach_cli.py replay --digit 3 --row 4 --col 4 [--path-mode]
    python scripts/teach_cli.py replay --digit 3 --x 10.0 --y -260.0

There is deliberately no power-off command: pymycobot's power_off()
closes communication with the arm's controller, after which
get_coords() returns -1 and nothing can be recorded.

Serial port/baud come from sudoku_robot.config (override with the
SUDOKU_ROBOT_SERIAL_PORT / SUDOKU_ROBOT_BAUDRATE env vars). config/corners.json
and config/arm_calibration.json are found via sudoku_robot.config, the same
as the main CLI, whatever folder you run this from.
"""
import argparse
import os
import sys

# Run as a plain script (python scripts/<name>.py), so put the project root --
# the folder containing the sudoku_robot package -- on the import path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sudoku_robot import config  # noqa: E402
from sudoku_robot.writer import teach  # noqa: E402
from sudoku_robot.writer.arm_controller import MyCobotArmController  # noqa: E402
from sudoku_robot.writer.grid_layout import TaughtCornersGridLayout  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="Hand-teaching tool for the mycobot 280 (optional).")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("release-servos")
    sub.add_parser("lock-servos", aliases=["power-on"])
    sub.add_parser("capture-surface")
    sub.add_parser("capture-box-origin")

    cp = sub.add_parser("capture-point")
    cp.add_argument("--digit", type=int, required=True)
    cp.add_argument("--segment", required=True,
                     choices=["top", "top_left", "top_right", "middle",
                              "bottom_left", "bottom_right", "bottom"])
    cp.add_argument("--which", required=True, choices=["start", "end"])

    fd = sub.add_parser("finish-digit")
    fd.add_argument("--digit", type=int, required=True)

    rec = sub.add_parser("record-path")
    rec.add_argument("--digit", type=int, required=True)
    rec.add_argument("--max-wait", type=float, default=20.0)

    sd = sub.add_parser("show-digit")
    sd.add_argument("--digit", type=int, required=True)

    rp = sub.add_parser("replay")
    rp.add_argument("--digit", type=int, required=True)
    rp.add_argument("--row", type=int)
    rp.add_argument("--col", type=int)
    rp.add_argument("--x", type=float)
    rp.add_argument("--y", type=float)
    rp.add_argument("--corners-file", default=config.CORNERS_PATH)
    rp.add_argument("--path-mode", action="store_true",
                     help="replay a continuously-recorded path instead of named segments")

    args = p.parse_args()

    if args.cmd == "release-servos":
        mc = teach.connect_raw()
        teach.release_servos_for_teaching(mc)
        print("Servos released -- arm is free to move by hand now.")
        return

    if args.cmd in ("lock-servos", "power-on"):
        mc = teach.connect_raw()
        teach.lock_servos_after_teaching(mc)
        print("Servos re-engaged -- the arm holds its pose again.")
        return

    if args.cmd == "capture-surface":
        mc = teach.connect_raw()
        result = teach.capture_surface(mc)
        print(f"surface_z={result['surface_z']:.1f}  orientation={result['orientation']}  "
              f"(saved to {config.ARM_CALIBRATION_PATH})")
        return

    if args.cmd == "capture-box-origin":
        mc = teach.connect_raw()
        x, y = teach.capture_box_origin(mc)
        print(f"box_origin=({x:.1f}, {y:.1f})")
        return

    if args.cmd == "capture-point":
        mc = teach.connect_raw()
        target = teach.capture_segment_point(mc, args.digit, args.segment, args.which)
        print(f"digit {args.digit} segment '{args.segment}' {args.which} = "
              f"{target[args.which]}")
        return

    if args.cmd == "record-path":
        mc = teach.connect_raw()
        print(f"Waiting for pen touch-down (up to {args.max_wait}s) -- go ahead and draw.")
        path = teach.record_continuous_path(mc, args.digit, max_wait_s=args.max_wait)
        print(f"Captured {len(path)} points for digit {args.digit}.")
        return

    if args.cmd == "finish-digit":
        segs = teach.finish_digit(args.digit)
        names = [s["name"] for s in segs]
        print(f"digit {args.digit} finished with {len(segs)} segment(s): {names}")
        return

    if args.cmd == "show-digit":
        segs = teach.load_digit(args.digit)
        for s in segs:
            print(f"  {s['name']:14s} start={s['start']}  end={s['end']}")
        return

    if args.cmd == "replay":
        if args.row is not None and args.col is not None:
            layout = TaughtCornersGridLayout.from_corners_file(args.corners_file)
            target_xy = layout.cell_center(args.row, args.col)
        elif args.x is not None and args.y is not None:
            target_xy = (args.x, args.y)
        else:
            print("replay needs either --row/--col or --x/--y", file=sys.stderr)
            sys.exit(1)

        # Pen heights/orientation come from arm_calibration.json -- the
        # same source the main CLI's real-arm writes use.
        arm = MyCobotArmController()
        arm.connect()
        try:
            if args.path_mode:
                teach.replay_digit_path(arm, target_xy, digit=args.digit)
            else:
                teach.replay_digit(arm, target_xy, digit=args.digit)
            arm.home()
        finally:
            arm.disconnect()
        print(f"replayed digit {args.digit} at {target_xy}")
        return


if __name__ == "__main__":
    main()
