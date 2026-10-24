"""
Low-level motion control: move the pen to an (x, y) point on the paper
with the pen either up (travelling) or down (drawing).

Two implementations share one interface:

- `SimulatedArmController` sends no hardware commands at all -- it
  just records every move. It's the default everywhere in this
  project so the writing pipeline can be developed and tested without
  a physical arm connected, and without pymycobot even installed.
- `MyCobotArmController` drives a real mycobot 280 via pymycobot.

`pen_writer.py` and `pipeline.py` only ever talk to the `ArmController`
interface, so switching from simulated to real hardware is a
one-argument change (which controller instance you pass in), not a
rewrite.
"""
import time
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

from .. import config

# pymycobot needs the real serial hardware to *use*, but importing it
# should never be what stops you from running the simulated pipeline
# on a laptop with no arm attached -- so the import is optional and
# only required at the point someone actually asks for real hardware.
try:
    from pymycobot.mycobot280 import MyCobot280
except ImportError:  # pragma: no cover - exercised only without the dependency
    MyCobot280 = None


class ArmMotionError(Exception):
    """Raised when a real arm move fails and a same-target retry in a different mode also fails."""


class ArmController(ABC):
    #: True for controllers that move real hardware. The write
    #: pipeline uses this to decide whether it needs to ask for
    #: physical-safety confirmation before doing anything.
    is_physical: bool = False

    @abstractmethod
    def connect(self) -> None:
        """Open the connection to the arm (or no-op for a simulation)."""
        raise NotImplementedError

    @abstractmethod
    def disconnect(self) -> None:
        """Close the connection (or no-op for a simulation)."""
        raise NotImplementedError

    @abstractmethod
    def move(self, x: float, y: float, pen_down: bool) -> None:
        """
        Move the pen tip to (x, y) in mm, at the pen-down or pen-up
        height depending on `pen_down`. A straight-line move -- not a
        drawing stroke by itself; `pen_writer.py` chains these to
        trace out a shape.
        """
        raise NotImplementedError

    @abstractmethod
    def home(self) -> None:
        """Move to a fixed, safe resting position with the pen up."""
        raise NotImplementedError

    def hover(self, x: float, y: float, clearance_mm: float) -> None:
        """
        Travel to (x, y) at pen-up height, then lower the pen tip to
        `clearance_mm` ABOVE the paper surface -- close enough to show
        exactly where it points, without touching. Used to align the
        paper under planned grid corners (writer/placement.py).
        """
        raise NotImplementedError


class SimulatedArmController(ArmController):
    """
    Records every requested move instead of sending it anywhere.
    Lets you develop and unit-test the whole writing pipeline -- grid
    layout, digit strokes, the empty-cell traversal -- without a robot
    plugged in.
    """

    is_physical = False

    def __init__(self, log: bool = True, home_xy: Tuple[float, float] = config.DEFAULT_HOME_XY):
        self.log = log
        # Same resting position as MyCobotArmController, so a simulated
        # run's move log matches what the real arm would actually do.
        self.home_xy = home_xy
        self.moves: List[Tuple[float, float, bool]] = []
        #: (x, y, clearance_mm) for every hover() -- pen held just above the paper.
        self.hovers: List[Tuple[float, float, float]] = []
        self.connected = False

    def connect(self) -> None:
        self.connected = True
        if self.log:
            print("[sim] connected")

    def disconnect(self) -> None:
        self.connected = False
        if self.log:
            print("[sim] disconnected")

    def move(self, x: float, y: float, pen_down: bool) -> None:
        self.moves.append((x, y, pen_down))
        if self.log:
            state = "pen-down" if pen_down else "pen-up  "
            print(f"[sim] {state} move to ({x:.1f}, {y:.1f})")

    def home(self) -> None:
        self.move(*self.home_xy, pen_down=False)

    def hover(self, x: float, y: float, clearance_mm: float) -> None:
        # Recorded as a pen-up move: the pen never touches the paper.
        self.move(x, y, pen_down=False)
        self.hovers.append((x, y, clearance_mm))
        if self.log:
            print(f"[sim] hover {clearance_mm:.1f}mm above ({x:.1f}, {y:.1f})")


class MyCobotArmController(ArmController):
    """
    Drives a real mycobot 280 over serial via pymycobot.

    Pen up/down is implemented as a Z-axis change: the pen is assumed
    to be mounted rigidly in the end effector (no separate pen-lift
    servo), so "lifting the pen" just means moving to a higher Z at
    the same (x, y), and "putting it down" means moving straight down
    onto the paper.

    Connection settings default to `config.serial_port()` /
    `config.baudrate()`; pen heights and tool orientation default to
    config/arm_calibration.json (`config.load_arm_calibration()`) -- the single
    source of truth shared with scripts/teach_cli.py, so the main CLI and the
    teaching tools always press to the same depth at the same angle.
    Pass explicit values only to override that file for one run.

    Calibration history (why arm_calibration.json holds what it does):
    pen_down_z=98.9 is the value proven on real hardware in 'mark'
    mode. A shallower hand-measured depth made contact at a single
    point but lost it as soon as the pen moved laterally (a commanded
    short line left only a dot), so a firmer press was needed to keep
    contact through the pen mount's own mechanical give. The
    orientation is the one read back at the taught TR corner.
    `scripts/teach_cli.py capture-surface` overwrites both from a fresh
    measurement. Coordinates follow the convention in config.py.
    """

    is_physical = True

    def __init__(
        self,
        port: Optional[str] = None,
        baudrate: Optional[str] = None,
        speed: int = 30,
        draw_speed: int = 5,
        pen_up_z: Optional[float] = None,
        pen_down_z: Optional[float] = None,
        orientation: Optional[Tuple[float, float, float]] = None,
        home_xy: Tuple[float, float] = config.DEFAULT_HOME_XY,
        move_settle_s: float = 3.5,
        calibration_path: Optional[str] = None,
    ):
        if MyCobot280 is None:
            raise ImportError(
                "pymycobot is not installed. Install it (`pip install pymycobot`) "
                "on the mycobot 280 Pi to use MyCobotArmController; "
                "SimulatedArmController needs no extra dependency."
            )
        if pen_up_z is None or pen_down_z is None or orientation is None:
            calibration = config.load_arm_calibration(calibration_path)
            pen_up_z = calibration.pen_up_z if pen_up_z is None else pen_up_z
            pen_down_z = calibration.pen_down_z if pen_down_z is None else pen_down_z
            orientation = calibration.orientation if orientation is None else orientation
        self.port = port or config.serial_port()
        self.baudrate = baudrate or config.baudrate()
        self.speed = speed
        self.draw_speed = draw_speed
        self.pen_up_z = pen_up_z
        self.pen_down_z = pen_down_z
        self.orientation = tuple(orientation)
        self.home_xy = home_xy
        self.move_settle_s = move_settle_s
        self._mc = None

    def connect(self) -> None:
        self._mc = MyCobot280(self.port, self.baudrate)
        time.sleep(1.0)  # give the controller board a moment to be ready
        # A previous run's failed move (e.g. error 33, "linear motion
        # has no adjacent solution" -- seen in practice moving from an
        # arbitrary starting pose) latches until cleared, and silently
        # blocks every move sent afterward with no exception raised.
        # Starting from a known-clean error state avoids inheriting a
        # stale failure from whatever happened last session.
        self._mc.clear_error_information()

    def disconnect(self) -> None:
        # pymycobot has no explicit "close" -- just drop the reference.
        # We do NOT power off servos here: leaving them enabled after a
        # run is safer than an unexpected torque-off mid-arm-position.
        self._mc = None

    #: pymycobot's own client-side validation rejects any X/Y outside
    #: this box before even attempting IK (see MyCobot280DataException).
    #: A hand-taught corner landed 11mm past it in practice, so this is
    #: a real case, not a hypothetical -- clamping here means a target
    #: just outside reach gets drawn at the nearest reachable point
    #: instead of raising and aborting the whole write.
    _COORD_LIMIT = config.ARM_COORD_LIMIT_MM

    def move(self, x: float, y: float, pen_down: bool) -> None:
        z = self.pen_down_z if pen_down else self.pen_up_z
        # Drawing moves use a much slower speed than travel moves --
        # requested directly to trade speed for steadier, more
        # controlled contact while the pen is actually touching paper.
        speed = self.draw_speed if pen_down else self.speed
        self._send(x, y, z, speed)

    def hover(self, x: float, y: float, clearance_mm: float) -> None:
        if clearance_mm <= 0:
            raise ValueError("hover clearance must be > 0 -- use move(pen_down=True) to touch the paper")
        self.move(x, y, pen_down=False)                                # travel at the safe height
        self._send(x, y, self.pen_down_z + clearance_mm, self.draw_speed)  # then descend slowly

    def _send(self, x: float, y: float, z: float, speed: int) -> None:
        """Send one straight-line move with the clamping / error-check / retry every move needs."""
        if self._mc is None:
            raise RuntimeError("MyCobotArmController.connect() must be called before move()")
        clamped_x = max(-self._COORD_LIMIT, min(self._COORD_LIMIT, x))
        clamped_y = max(-self._COORD_LIMIT, min(self._COORD_LIMIT, y))
        if clamped_x != x or clamped_y != y:
            print(f"[warn] target ({x:.1f}, {y:.1f}) is outside commandable range; "
                  f"clamped to ({clamped_x:.1f}, {clamped_y:.1f})")
        x, y = clamped_x, clamped_y
        rx, ry, rz = self.orientation
        # Linear mode (1) is the default for EVERY move, pen up or
        # down, and that default matters more for pen-up moves, not
        # less. A real incident on hardware showed why: angular mode
        # (0) solves IK for the destination directly without requiring
        # a valid straight-line path to it, which sounds strictly more
        # robust, but it comes at a real cost -- it gives no guarantee
        # about the path *between* two safe endpoints, and a joint-space
        # interpolation dipped the pen down mid-travel and dragged it
        # across the paper between two points that were each,
        # individually, at a safe pen-up height. Linear mode's
        # straight-line path is exactly what avoids that, and since
        # consecutive moves normally share the same Z and orientation
        # (only x, y change), it's also the case where linear mode's
        # own limitation -- failing on a large pose/orientation jump,
        # error 33 "linear motion has no adjacent solution" -- essentially
        # never triggers. Angular mode is kept ONLY as the fallback
        # below, for the rare case (e.g. the very first move of a
        # session, from an arbitrary leftover pose) where linear
        # genuinely can't find a path.
        self._mc.send_coords([x, y, z, rx, ry, rz], speed, 1)
        time.sleep(self.move_settle_s)

        # A move error (most commonly 33, "linear motion has no
        # adjacent solution") is silent otherwise -- send_coords
        # doesn't raise, and the error LATCHES, blocking every move
        # sent afterward with no exception either. Left unchecked,
        # that's exactly what turned one bad segment into a real
        # incident: a pen-down stroke errored mid-digit, the "lift
        # pen" move right after it silently failed too (still
        # latched), and the arm went on to its next travel move with
        # the pen still down, dragging it across the table. Checking
        # after every move, retrying once in angular mode (which
        # solves IK for the destination directly instead of requiring
        # a valid path to it, so it isn't subject to the same error),
        # and raising if that ALSO fails means a real failure stops
        # the whole sequence here instead of corrupting every move
        # after it.
        if self._mc.get_error_information():
            self._mc.clear_error_information()
            self._mc.send_coords([x, y, z, rx, ry, rz], speed, 0)
            time.sleep(self.move_settle_s)
            retry_error = self._mc.get_error_information()
            if retry_error:
                self._mc.clear_error_information()
                raise ArmMotionError(
                    f"Move to ({x:.1f}, {y:.1f}, {z:.1f}) failed even after "
                    f"retrying in angular mode (error code {retry_error}). "
                    "Stopping here rather than risk continuing in an unknown "
                    "state -- check the arm's actual position before retrying."
                )

    def home(self) -> None:
        x, y = self.home_xy
        self.move(x, y, pen_down=False)
