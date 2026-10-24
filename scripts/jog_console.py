"""
Interactive jog console -- run this yourself and control the arm directly:

    python scripts/jog_console.py

Use it to teach config/corners.json to wherever the paper lies (or use
scripts/place_paper.py to put the paper where a planned grid is). The servos stay
powered, so each position is held steady and read back precisely.

Commands (type one, press Enter):
    f <mm>     move forward  (away from the base, toward the paper's top edge: -Y)
    b <mm>     move backward (toward the base: +Y)
    l <mm>     move left     (+X)
    r <mm>     move right    (-X)
    u <mm>     move up       (+Z)
    d <mm>     move down     (-Z)
    pos        print current coordinates
    save NAME  record current position under NAME in config/corners.json
               (TL = centre of cell (0,0), TR = centre of (0,8), BL = centre of (8,0))
    check      validate config/corners.json (edge lengths, 90-degree corner, reach)
    q          quit

Directions are as seen from behind the arm's base, looking out over
the paper -- the project-wide convention documented in
sudoku_robot/config.py (confirmed empirically on this setup).

Example: "f 10" moves forward 10mm. Start with small numbers (5-10mm)
once you're close to the paper.
"""
import json
import os
import sys
import time

# Run as a plain script (python scripts/<name>.py), so put the project root --
# the folder containing the sudoku_robot package -- on the import path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sudoku_robot import config  # noqa: E402

# (dx, dy, dz) unit steps, per the convention in sudoku_robot/config.py.
DIRS = {
    "f": (0, -1, 0), "b": (0, 1, 0),
    "l": (1, 0, 0), "r": (-1, 0, 0),
    "u": (0, 0, 1), "d": (0, 0, -1),
}


def move_delta(mc, dx, dy, dz):
    cur = mc.get_coords()
    target = [cur[0] + dx, cur[1] + dy, cur[2] + dz, cur[3], cur[4], cur[5]]
    mc.send_coords(target, 15, 1)
    time.sleep(1.0)
    err = mc.get_error_information()
    if err:
        mc.clear_error_information()
        mc.send_coords(target, 15, 0)
        time.sleep(1.0)
        err = mc.get_error_information()
        if err:
            mc.clear_error_information()
            print(f"  MOVE FAILED (error {err}). Staying at current position.")
            return
    print("  now at:", [round(v, 1) for v in mc.get_coords()])


def save_corner(mc, name, path=config.CORNERS_PATH):
    data = {}
    if os.path.exists(path):
        with open(path) as fh:
            data = json.load(fh)
    coords = mc.get_coords()
    data[name] = coords
    with open(path, "w") as fh:
        json.dump(data, fh, indent=2)
    print(f"  saved '{name}':", [round(v, 1) for v in coords])


def check_corners():
    from sudoku_robot.writer.corner_check import check_corners_file, format_report

    try:
        print(format_report(check_corners_file(config.CORNERS_PATH), config.CORNERS_PATH))
    except (OSError, ValueError, KeyError) as e:
        print(f"  can't check corners yet: {e}")


def main():
    # Imported here, not at module level, so this file can be imported
    # (e.g. by tests or on a dev machine) without pymycobot or an arm.
    from pymycobot.mycobot280 import MyCobot280

    mc = MyCobot280(config.serial_port(), config.baudrate())
    time.sleep(1.0)
    mc.clear_error_information()
    print("Connected. Current position:", mc.get_coords())
    print(__doc__)
    while True:
        try:
            line = input("> ").strip()
        except EOFError:
            break
        if not line:
            continue
        parts = line.split()
        cmd = parts[0].lower()
        if cmd == "q":
            break
        elif cmd == "pos":
            print(" ", [round(v, 1) for v in mc.get_coords()])
        elif cmd == "save" and len(parts) == 2:
            save_corner(mc, parts[1])
        elif cmd == "check":
            check_corners()
        elif cmd in DIRS and len(parts) == 2:
            try:
                mm = float(parts[1])
            except ValueError:
                print("  give a number, e.g. 'f 10'")
                continue
            dx, dy, dz = DIRS[cmd]
            move_delta(mc, dx * mm, dy * mm, dz * mm)
        else:
            print("  unknown command -- see the instructions above")
    print("Done. Position left as-is (pen state unchanged).")


if __name__ == "__main__":
    main()
