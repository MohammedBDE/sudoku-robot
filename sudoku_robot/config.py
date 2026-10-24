"""
Single source of truth for machine-specific settings: file locations,
the arm's serial connection, its reach limits, and its pen calibration.

Nothing here touches hardware or reads a file at import time -- the
constants are plain values, and anything that has to come from disk
(`load_arm_calibration()`) is only read when something asks for it.
That keeps every module importable on a Windows dev machine with no
arm attached.

Arm coordinate convention
-------------------------
Every (x, y, z) in this project -- config/corners.json,
config/arm_calibration.json, GridLayout.cell_center(),
scripts/jog_console.py's directions -- is in the
mycobot 280's own base frame, in millimetres, as returned by
`get_coords()`. Viewed from behind the arm's base, looking out over
the paper:

    -Y  = "forward": away from the base, toward the far (top) edge of the paper
    +Y  = "backward": toward the base
    +X  = left
    -X  = right
    +Z  = up (pen lift); the paper surface sits at arm_calibration.json's pen_down_z

The puzzle is laid upright as read from that viewpoint, so:

    row 0 is the row farthest from the base (most negative Y),
    increasing row  -> +Y (toward the base),
    col 0 is the leftmost column (most positive X),
    increasing col  -> -X (to the right).

This matches jog_console.py's empirically confirmed axis mapping and
the hand-taught corners.json (TL is farther from the base than BL).
"""
import json
import os
from dataclasses import asdict, dataclass
from typing import Optional, Tuple

# -- File locations ---------------------------------------------------------

#: sudoku_robot/config.py -> sudoku_robot -> project root
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

#: Per-robot files a person edits or re-teaches (see README "Robot-specific files").
CONFIG_DIR = os.path.join(PROJECT_ROOT, "config")
#: Generated calibration/debug images (camera test frames, grid-detection overlays).
CALIB_DIR = os.path.join(PROJECT_ROOT, "calib")
#: Command-line tools and setup scripts (jog_console.py, teach_cli.py, verify_env.py, setup.*).
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")

#: Hand-taught grid corners (TL/TR/BL arm poses), see writer.grid_layout.TaughtCornersGridLayout.
CORNERS_PATH = os.path.join(CONFIG_DIR, "corners.json")
#: Pen heights + tool orientation used for every real-arm move.
ARM_CALIBRATION_PATH = os.path.join(CONFIG_DIR, "arm_calibration.json")
#: iPhone RTSP URL, see vision.camera_config.
CAMERA_CONFIG_PATH = os.path.join(CONFIG_DIR, "camera_config.json")
#: Standalone hand-teaching tool data (writer.teach / teach_cli.py). Not used by the main pipeline.
TEACH_DATA_DIR = os.path.join(PROJECT_ROOT, "teach_data")
#: Output of puzzles/render.py.
PRINTABLE_PUZZLES_DIR = os.path.join(PROJECT_ROOT, "printable_puzzles")

#: Where these files lived before the config/ folder existed -- only used to
#: point people with an old checkout at the new location.
LEGACY_CONFIG_FILES = ("corners.json", "arm_calibration.json", "camera_config.json")

# -- Serial connection ------------------------------------------------------

SERIAL_PORT_ENV = "SUDOKU_ROBOT_SERIAL_PORT"
BAUDRATE_ENV = "SUDOKU_ROBOT_BAUDRATE"
#: The mycobot 280 Pi's built-in UART. Override with SUDOKU_ROBOT_SERIAL_PORT
#: (e.g. "COM3") when driving the arm over USB from another machine.
DEFAULT_SERIAL_PORT = "/dev/serial0"
DEFAULT_BAUDRATE = "1000000"


def serial_port() -> str:
    return os.environ.get(SERIAL_PORT_ENV) or DEFAULT_SERIAL_PORT


def baudrate() -> str:
    return os.environ.get(BAUDRATE_ENV) or DEFAULT_BAUDRATE


# -- Geometry / reach -------------------------------------------------------

#: Ruler-measured edge of one printed cell (puzzles/render.py prints at exactly this).
CELL_SIZE_MM = 20.0
#: pymycobot's own client-side X/Y validation limit -- targets outside it are rejected before IK.
ARM_COORD_LIMIT_MM = 280.0
#: The mycobot 280's nominal working radius from the base axis.
ARM_MAX_REACH_MM = 280.0
#: Safe resting position, pen up, in front of the base (see the convention above).
DEFAULT_HOME_XY: Tuple[float, float] = (0.0, -220.0)


# -- Pen calibration --------------------------------------------------------

@dataclass(frozen=True)
class ArmCalibration:
    #: Z (mm) at which the pen tip presses onto the paper.
    pen_down_z: float
    #: Z (mm) for travel moves, clear of the paper.
    pen_up_z: float
    #: Tool orientation (rx, ry, rz) in degrees, held constant for every move.
    orientation: Tuple[float, float, float]


class ArmCalibrationError(Exception):
    """arm_calibration.json is missing or malformed."""


def legacy_location_hint(path: str) -> str:
    """
    If a config file is missing from config/ but an old copy still sits
    in the project root (from before the config/ folder existed), say so.
    """
    old = os.path.join(PROJECT_ROOT, os.path.basename(path))
    if os.path.dirname(os.path.abspath(path)) == CONFIG_DIR and os.path.exists(old):
        return f" Found an old copy at {old} -- move it into {CONFIG_DIR}{os.sep}."
    return ""


def load_arm_calibration(path: Optional[str] = None) -> ArmCalibration:
    path = path or ARM_CALIBRATION_PATH
    if not os.path.exists(path):
        raise ArmCalibrationError(
            f"No arm calibration file at {path}. Create it with "
            '{"pen_down_z": <mm>, "pen_up_z": <mm>, "orientation": [rx, ry, rz]}, '
            "or record the surface with `python scripts/teach_cli.py capture-surface`."
            + legacy_location_hint(path)
        )
    with open(path) as fh:
        data = json.load(fh)
    try:
        orientation = tuple(float(v) for v in data["orientation"])
        if len(orientation) != 3:
            raise ValueError("orientation must have 3 values")
        return ArmCalibration(
            pen_down_z=float(data["pen_down_z"]),
            pen_up_z=float(data["pen_up_z"]),
            orientation=orientation,
        )
    except (KeyError, TypeError, ValueError) as e:
        raise ArmCalibrationError(f"Malformed arm calibration in {path}: {e}") from e


def save_arm_calibration(calibration: ArmCalibration, path: Optional[str] = None) -> None:
    path = path or ARM_CALIBRATION_PATH
    data = asdict(calibration)
    data["orientation"] = list(calibration.orientation)
    with open(path, "w") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
