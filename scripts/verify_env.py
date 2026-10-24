"""
Checks that this environment can actually run the project, and says
exactly what's wrong if not -- run after installing requirements.txt
(scripts/setup.sh / scripts/setup.ps1 run it automatically).

    python scripts/verify_env.py             # dev machine: simulation, tests, rendering
    python scripts/verify_env.py --hardware  # the robot's Pi: also checks the serial port
                                     # and requires the DejaVu font

Each check prints OK / WARN / FAIL. Exit code 0 = no FAILs, 1 = at
least one FAIL. WARNs don't fail the run but tell you what won't work.
"""
import argparse
import importlib
import json
import os
import re
import sys

#: scripts/verify_env.py -> scripts -> project root
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REQUIREMENTS = os.path.join(ROOT, "requirements.txt")
REQUIRED_PYTHON = (3, 13)

# requirement name -> import name, for the packages the code imports directly
IMPORT_NAMES = {
    "numpy": "numpy",
    "pillow": "PIL",
    "opencv-python-headless": "cv2",
    "pymycobot": "pymycobot",
    "pyserial": "serial",
    "pytest": "pytest",
}

_results = []


def report(status: str, what: str, detail: str = "") -> None:
    _results.append(status)
    line = f"[{status:<4}] {what}"
    if detail:
        line += f" -- {detail}"
    print(line)


def read_pins(path: str = REQUIREMENTS) -> dict:
    """{normalized name: pinned version} for every applicable `name==version` line."""
    pins = {}
    with open(path) as fh:
        for raw in fh:
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            spec, _, marker = line.partition(";")
            if marker and "win32" in marker and sys.platform != "win32":
                continue
            m = re.fullmatch(r"([A-Za-z0-9_.\-]+)==([A-Za-z0-9_.\-+]+)", spec.strip())
            if m:
                pins[m.group(1).lower().replace("_", "-")] = m.group(2)
    return pins


def check_python() -> None:
    v = sys.version_info
    if (v.major, v.minor) == REQUIRED_PYTHON:
        report("OK", f"Python {v.major}.{v.minor}.{v.micro}")
    else:
        report("WARN", f"Python {v.major}.{v.minor}.{v.micro}",
               f"the pins in requirements.txt target Python {REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]}; "
               "other versions may not have matching wheels")


def check_packages() -> None:
    from importlib import metadata

    for name, pinned in read_pins().items():
        try:
            installed = metadata.version(name)
        except metadata.PackageNotFoundError:
            report("FAIL", f"{name}=={pinned}", "not installed -- run: pip install -r requirements.txt")
            continue
        import_name = IMPORT_NAMES.get(name)
        if import_name:
            try:
                importlib.import_module(import_name)
            except Exception as e:  # a broken install, missing system library, etc.
                report("FAIL", f"{name}=={installed}", f"installed but `import {import_name}` failed: {e}")
                continue
        if installed == pinned:
            report("OK", f"{name}=={installed}")
        else:
            report("WARN", f"{name}=={installed}", f"requirements.txt pins {pinned}")


def check_pymycobot_api() -> None:
    try:
        from pymycobot.mycobot280 import MyCobot280
    except Exception as e:
        report("FAIL", "pymycobot MyCobot280", f"cannot import: {e}")
        return
    missing = [m for m in ("send_coords", "get_coords", "release_all_servos", "focus_all_servos",
                           "get_error_information", "clear_error_information")
               if not hasattr(MyCobot280, m)]
    if missing:
        report("FAIL", "pymycobot MyCobot280 API", f"missing methods this project uses: {missing}")
    else:
        report("OK", "pymycobot MyCobot280 API")


def check_font(hardware: bool) -> None:
    sys.path.insert(0, ROOT)
    from sudoku_robot import fonts

    path = fonts.find_reference_font(bold=True)
    if path:
        report("OK", "DejaVu Sans Bold font", path)
        return
    detail = (f"not found; using {fonts.describe_font(bold=True)} instead. Printed puzzles and the "
              "digit recognizer should both use DejaVu -- copy DejaVuSans-Bold.ttf and DejaVuSans.ttf "
              "into sudoku_robot/assets/fonts/ (or `sudo apt install fonts-dejavu-core` on the Pi)")
    report("FAIL" if hardware else "WARN", "DejaVu Sans Bold font", detail)


def check_robot_files() -> None:
    """These files describe ONE physical setup -- present doesn't mean valid for yours."""
    sys.path.insert(0, ROOT)
    from sudoku_robot import config

    try:
        cal = config.load_arm_calibration()
        report("OK", "config/arm_calibration.json", f"pen_down_z={cal.pen_down_z}, pen_up_z={cal.pen_up_z} "
               "(specific to one physical robot -- re-measure on yours, see README)")
    except config.ArmCalibrationError as e:
        report("WARN", "config/arm_calibration.json", str(e))

    if not os.path.exists(config.CORNERS_PATH):
        report("WARN", "config/corners.json", "missing -- teach it with scripts/jog_console.py before "
               "real-arm writes." + config.legacy_location_hint(config.CORNERS_PATH))
    else:
        from sudoku_robot.writer.corner_check import check_corners_file

        try:
            ok = check_corners_file(config.CORNERS_PATH).ok
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            report("WARN", "config/corners.json", f"unreadable: {e}")
        else:
            if ok:
                report("OK", "config/corners.json", "passes --check-corners (re-teach if the paper or robot moved)")
            else:
                report("WARN", "config/corners.json", "FAILS validation -- real-arm writes are refused until "
                       "it's re-taught (python -m sudoku_robot --check-corners)")

    if os.path.exists(config.CAMERA_CONFIG_PATH):
        report("OK", "config/camera_config.json")
    else:
        report("WARN", "config/camera_config.json",
               "missing -- only needed for --from-camera: "
               "cp config/camera_config.example.json config/camera_config.json"
               + config.legacy_location_hint(config.CAMERA_CONFIG_PATH))

    # Leftovers from before config/ existed would be silently ignored -- say so.
    stale = [name for name in config.LEGACY_CONFIG_FILES if os.path.exists(os.path.join(ROOT, name))]
    if stale:
        report("WARN", "old config files in the project root",
               f"{stale} are no longer read -- the project uses config/ now. Move (or delete) them.")


def check_serial() -> None:
    sys.path.insert(0, ROOT)
    from sudoku_robot import config

    port = config.serial_port()
    if port.startswith("/dev/") and not os.path.exists(port):
        report("FAIL", f"serial port {port}", "does not exist -- is this the robot's Pi, with serial enabled? "
               f"(override with {config.SERIAL_PORT_ENV})")
    else:
        report("OK", f"serial port {port}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--hardware", action="store_true",
                        help="also require what the real robot needs (serial port, DejaVu font)")
    args = parser.parse_args(argv)

    print(f"Checking environment for {ROOT}\n")
    check_python()
    check_packages()
    check_pymycobot_api()
    check_font(args.hardware)
    check_robot_files()
    if args.hardware:
        check_serial()

    fails, warns = _results.count("FAIL"), _results.count("WARN")
    print()
    if fails:
        print(f"NOT READY: {fails} check(s) failed, {warns} warning(s). Fix the FAIL lines above.")
        return 1
    print(f"READY ({warns} warning(s)). Next: python -m pytest, then python -m sudoku_robot --puzzle physical_demo --write")
    return 0


if __name__ == "__main__":
    sys.exit(main())
