"""
STANDALONE, OPTIONAL tool: hand-teach real digit shapes on the physical
arm, as an alternative to the synthetic seven-segment strokes in
digit_strokes.py. The main solve-and-write pipeline (cli.py ->
writer.pipeline.write_solution) never imports this module or reads
teach_data/ -- it always draws with digit_strokes.DIGIT_PATHS. This
module is kept only in case hand-teaching is revisited later.

Status: the only hand-taught data ever recorded (digit 1, unusable) has
been deleted, so teach_data/ holds just digits.json -- the generated
digit database (see digit_database.py), which this tool does not touch.
Teaching a digit from scratch creates its own files there.

Why hand-teach at all: digit_strokes.DIGIT_PATHS assumes the arm can accurately trace an
arbitrary straight line between two commanded points on the real paper.
In practice the bottleneck this whole project hit was never the arm's
own repeatability (that's proven solid -- ~1mm on commanded moves) but
getting the *reference frame* right (where the paper actually is,
which way it's rotated). Hand-teaching each digit directly on the real
paper sidesteps that: every segment's start/end is captured with the
arm's own encoders (get_coords()) at the exact moment a human holds the
pen tip there, so the recorded shape is automatically correct for
whatever the paper's true position/rotation is -- no separate
axis-correction math needed for the digit's *shape*. Only *translating*
a taught digit to a different cell still depends on GridLayout knowing
real cell centers.

Freeing the arm to move by hand: use release_all_servos(), NEVER
power_off(). In pymycobot, power_off() "closes communication with
Atom" (the end controller), after which get_coords()/get_angles()
return -1 -- this was also observed on the real arm, and makes
recording impossible. release_all_servos() only relaxes the joint
servos: the arm moves by hand and get_coords() keeps working.
focus_all_servos() is its inverse and re-engages every servo so the
arm holds its pose again. (Some joints can be stiff to move by hand
even when released; for precise single points such as the grid
corners, scripts/jog_console.py -- small powered moves -- is the better tool.)
capture_coords() is kept short (a quick average, not a long poll)
since a human hand can't hold a point perfectly steady.

Pen-down height and tool orientation are shared with the main
pipeline through config/arm_calibration.json (config.load_arm_calibration);
teach_data/teach_calibration.json holds only teaching-specific values
(box_origin, teach_scale).

Workflow (each step is one process invocation -- see scripts/teach_cli.py):

    1. release-servos                     (once)
    2. capture-surface                    (touch paper, hold, capture -> arm_calibration.json)
    3. capture-box-origin                 (touch center of teaching box, hold, capture)
    4. capture-point --digit N --segment S --which start/end   (repeat per segment)
       or: record-path --digit N          (freehand the whole digit in one motion)
    5. finish-digit --digit N             (repeat per digit)
    6. lock-servos                        (once, when done teaching)

Then replay_digit() draws a taught digit at any (row, col) cell via an
existing GridLayout, by translating every recorded point by
(target_cell_center - box_origin) -- see replay_digit()'s docstring for
why no rotation correction is needed on top of that.
"""
import json
import os
import time
from typing import Dict, List, Optional, Tuple

try:
    from pymycobot.mycobot280 import MyCobot280
except ImportError:  # pragma: no cover
    MyCobot280 = None

from .. import config
from .arm_controller import MyCobotArmController

_DATA_DIR = config.TEACH_DATA_DIR

# Classic seven-segment membership, same names/geometry as
# digit_strokes.py's _SEGMENTS, plus digit 0 (which digit_strokes.py
# skips since 0 means "empty cell" there -- but a hand-taught library
# should cover the full 0-9 range this tool is meant to build).
SEVEN_SEG_DIGITS: Dict[int, List[str]] = {
    0: ["top", "top_left", "top_right", "bottom_left", "bottom_right", "bottom"],
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

TOUCH_TOLERANCE_MM = 2.0


def _data_path(*parts: str) -> str:
    os.makedirs(_DATA_DIR, exist_ok=True)
    return os.path.join(_DATA_DIR, *parts)


def _calibration_path() -> str:
    return _data_path("teach_calibration.json")


def _digit_progress_path(digit: int) -> str:
    return _data_path(f"digit_{digit}_inprogress.json")


def _digit_final_path(digit: int) -> str:
    return _data_path(f"digit_{digit}.json")


def connect_raw() -> "MyCobot280":
    if MyCobot280 is None:
        raise ImportError("pymycobot is not installed")
    mc = MyCobot280(config.serial_port(), config.baudrate())
    time.sleep(1.0)
    mc.clear_error_information()
    return mc


def release_servos_for_teaching(mc) -> None:
    """Frees the arm to move by hand while keeping get_coords() readable (NOT power_off -- see module docstring)."""
    mc.release_all_servos()
    time.sleep(0.3)


def lock_servos_after_teaching(mc) -> None:
    """Re-engages every servo so the arm holds its pose again -- the inverse of release_servos_for_teaching."""
    mc.focus_all_servos()
    time.sleep(0.3)


def capture_coords(mc, samples: int = 3, interval: float = 0.08) -> List[float]:
    """
    Average a few rapid get_coords() reads into one point. Kept short
    (samples * interval ~= 0.25s total) because a human hand holding a
    released arm can keep a point steady for a fraction of a second
    but drifts over a longer window, so this trades away some
    smoothing to keep the required "hold still" window short.
    """
    readings = []
    for _ in range(samples):
        c = mc.get_coords()
        if c and len(c) == 6:
            readings.append(c)
        time.sleep(interval)
    if not readings:
        raise RuntimeError("get_coords() returned nothing -- check connection/power state")
    avg = [sum(r[i] for r in readings) / len(readings) for i in range(6)]
    return avg


def load_calibration() -> dict:
    """Teaching-only values (box_origin, teach_scale) from teach_data/teach_calibration.json."""
    path = _calibration_path()
    if not os.path.exists(path):
        return {}
    with open(path) as fh:
        return json.load(fh)


def save_calibration(data: dict) -> None:
    existing = load_calibration()
    existing.update(data)
    with open(_calibration_path(), "w") as fh:
        json.dump(existing, fh, indent=2)


def _surface_z() -> float:
    """Paper surface height: arm_calibration.json's pen_down_z, shared with the main pipeline."""
    return config.load_arm_calibration().pen_down_z


def capture_surface(mc) -> dict:
    """
    Touch pen to paper, hold, call this. Writes the measured Z as
    pen_down_z, and the current tool orientation, into
    arm_calibration.json -- the same file the main CLI's real-arm
    writes read. pen_up_z is kept (or set 30mm above the surface if
    there was no calibration file yet).
    """
    coords = capture_coords(mc)
    x, y, z, rx, ry, rz = coords
    try:
        pen_up_z = config.load_arm_calibration().pen_up_z
    except config.ArmCalibrationError:
        pen_up_z = z + 30.0
    config.save_arm_calibration(
        config.ArmCalibration(pen_down_z=z, pen_up_z=pen_up_z, orientation=(rx, ry, rz))
    )
    return {"surface_z": z, "orientation": [rx, ry, rz]}


def capture_box_origin(mc) -> Tuple[float, float]:
    """Touch the center of the 2x2cm box you'll teach every digit inside, hold, call this."""
    coords = capture_coords(mc)
    x, y = coords[0], coords[1]
    save_calibration({"box_origin": [x, y]})
    return (x, y)


def _load_progress(digit: int) -> dict:
    path = _digit_progress_path(digit)
    if os.path.exists(path):
        with open(path) as fh:
            return json.load(fh)
    return {"segments": []}


def _save_progress(digit: int, data: dict) -> None:
    with open(_digit_progress_path(digit), "w") as fh:
        json.dump(data, fh, indent=2)


def capture_segment_point(mc, digit: int, segment: str, which: str) -> dict:
    """
    which is "start" or "end". Touch the pen down at that point on the
    real digit, hold it there, then call this. Warns (doesn't block) if
    the z reading isn't close to the calibrated surface -- a cheap
    sanity check that the pen was actually touching down, not hovering.
    """
    if which not in ("start", "end"):
        raise ValueError("which must be 'start' or 'end'")
    coords = capture_coords(mc)
    x, y, z = coords[0], coords[1], coords[2]

    surface_z = _surface_z()
    if abs(z - surface_z) > TOUCH_TOLERANCE_MM:
        print(f"[warn] z={z:.1f} is {abs(z - surface_z):.1f}mm from calibrated "
              f"surface_z={surface_z:.1f} -- pen may not have been touching down")

    progress = _load_progress(digit)
    segs = progress["segments"]
    target = next((s for s in segs if s["name"] == segment), None)
    if target is None:
        target = {"name": segment}
        segs.append(target)
    target[which] = [x, y, z]
    _save_progress(digit, progress)
    return target


def record_continuous_path(
    mc,
    digit: int,
    max_wait_s: float = 20.0,
    interval_s: float = 0.1,
    lift_confirm: int = 3,
) -> List[List[float]]:
    """
    Alternative to the per-segment start/end capture: freehand-guide
    the pen through the whole digit shape in one motion, pen down
    throughout. Touch-gated rather than tied to a fixed timing window
    (a blind timer doesn't work over chat -- there's no way to start
    the human's motion and this poll loop at the same instant): this
    polls up to `max_wait_s`, discards every reading until z comes
    within TOUCH_TOLERANCE_MM of the calibrated surface (pen_down_z; pen actually
    touching down), records every reading from then on, and stops as
    soon as it sees `lift_confirm` consecutive readings clearly above
    the surface again (pen lifted back off) -- so it can be started
    proactively before the human even begins moving, and it ends itself.

    Picks up natural hand wobble instead of clean straight lines --
    acceptable tradeoff under time pressure, and still far more
    reliable than the old synthetic DIGIT_PATHS since every point is a
    real measurement in the paper's true frame.
    """
    surface_z = _surface_z()

    path: List[List[float]] = []
    touching = False
    lift_count = 0
    steps = max(1, round(max_wait_s / interval_s))
    for _ in range(steps):
        c = mc.get_coords()
        if c and len(c) == 6:
            is_touch = abs(c[2] - surface_z) <= TOUCH_TOLERANCE_MM
            if is_touch:
                touching = True
                lift_count = 0
                path.append(c[:3])
            elif touching:
                lift_count += 1
                if lift_count >= lift_confirm and len(path) >= 3:
                    break
        time.sleep(interval_s)

    if not path:
        raise RuntimeError(
            "no touch-down detected within the wait window -- check pen_down_z in arm_calibration.json "
            "calibration, or the pen may not have pressed flat enough to register"
        )
    with open(_digit_final_path(digit).replace(".json", "_path.json"), "w") as fh:
        json.dump({"path": path}, fh, indent=2)
    return path


def load_digit_path(digit: int) -> List[List[float]]:
    path = _digit_final_path(digit).replace(".json", "_path.json")
    with open(path) as fh:
        return json.load(fh)["path"]


def replay_digit_path(
    arm: MyCobotArmController,
    target_xy: Tuple[float, float],
    digit: Optional[int] = None,
    path: Optional[List[List[float]]] = None,
) -> None:
    """Replay a continuously-recorded path (see record_continuous_path) as one pen-down stroke."""
    if path is None:
        if digit is None:
            raise ValueError("must pass either digit or path")
        path = load_digit_path(digit)

    calib = load_calibration()
    box_origin = calib.get("box_origin")
    if box_origin is None:
        raise RuntimeError("no box_origin in calibration -- run capture_box_origin() first")
    scale = calib.get("teach_scale", 1.0)

    pts = [
        (target_xy[0] + (p[0] - box_origin[0]) * scale, target_xy[1] + (p[1] - box_origin[1]) * scale)
        for p in path
    ]
    arm.move(*pts[0], pen_down=False)  # travel above the digit's start
    arm.move(*pts[0], pen_down=True)   # drop the pen once
    for (x, y) in pts[1:]:
        arm.move(x, y, pen_down=True)  # keep drawing, no lifts in between
    arm.move(*pts[-1], pen_down=False)  # lift only at the very end


def finish_digit(digit: int) -> List[dict]:
    """
    Validate every segment recorded so far for this digit has both a
    start and an end, then write digit_{N}.json. Leaves the in-progress
    file alone (harmless if you record more later; finish again to
    re-finalize).
    """
    progress = _load_progress(digit)
    segs = progress["segments"]
    incomplete = [s["name"] for s in segs if "start" not in s or "end" not in s]
    if incomplete:
        raise ValueError(f"digit {digit}: segment(s) missing a point: {incomplete}")
    if not segs:
        raise ValueError(f"digit {digit}: no segments recorded")
    with open(_digit_final_path(digit), "w") as fh:
        json.dump({"segments": segs}, fh, indent=2)
    return segs


def load_digit(digit: int) -> List[dict]:
    path = _digit_final_path(digit)
    with open(path) as fh:
        return json.load(fh)["segments"]


def replay_digit(
    arm: MyCobotArmController,
    target_xy: Tuple[float, float],
    digit: Optional[int] = None,
    segments: Optional[List[dict]] = None,
    waypoint_step_mm: float = 2.0,
) -> None:
    """
    Draw a taught digit at `target_xy` (a real (x, y) on the paper,
    typically from GridLayout.cell_center(row, col)).

    Translation only, no rotation: every recorded point gets the same
    (dx, dy) = target_xy - box_origin added to it. This is correct (not
    an approximation) as long as `target_xy` itself came from the same
    GridLayout that correctly accounts for the paper's real rotation --
    the digit's *shape* was already taught in the paper's true
    orientation by a human hand, so it doesn't need a separate rotation
    correction the way the old synthetic DIGIT_PATHS did.

    Uses arm.move() (not raw send_coords) so every point gets the
    controller's existing clamping / linear-mode / error-retry / settle
    time -- all proven necessary on this hardware.
    """
    if segments is None:
        if digit is None:
            raise ValueError("must pass either digit or segments")
        segments = load_digit(digit)

    calib = load_calibration()
    box_origin = calib.get("box_origin")
    if box_origin is None:
        raise RuntimeError("no box_origin in calibration -- run capture_box_origin() first")
    scale = calib.get("teach_scale", 1.0)

    def _place(point):
        # Scale the recorded offset from box_origin (fixes teaching
        # motions that came out larger/smaller than the real target
        # size), then re-anchor at target_xy. Uniform scaling around
        # one fixed center -- not the axis-rotation math that caused
        # trouble before.
        lx = (point[0] - box_origin[0]) * scale
        ly = (point[1] - box_origin[1]) * scale
        return target_xy[0] + lx, target_xy[1] + ly

    for seg in segments:
        sx, sy = _place(seg["start"])
        ex, ey = _place(seg["end"])

        arm.move(sx, sy, pen_down=False)  # travel above segment start
        arm.move(sx, sy, pen_down=True)   # touch down

        length = ((ex - sx) ** 2 + (ey - sy) ** 2) ** 0.5
        steps = max(1, round(length / waypoint_step_mm))
        for i in range(1, steps + 1):
            t = i / steps
            wx = sx + (ex - sx) * t
            wy = sy + (ey - sy) * t
            arm.move(wx, wy, pen_down=True)

        arm.move(ex, ey, pen_down=False)  # lift at end of this segment
