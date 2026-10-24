import json
import os

import pytest

from sudoku_robot import config, fonts
from sudoku_robot.writer import arm_controller


def test_repo_arm_calibration_file_loads():
    cal = config.load_arm_calibration()
    assert cal.pen_up_z > cal.pen_down_z
    assert len(cal.orientation) == 3


def test_missing_or_malformed_calibration_raises(tmp_path):
    with pytest.raises(config.ArmCalibrationError):
        config.load_arm_calibration(str(tmp_path / "nope.json"))
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"pen_down_z": 1.0}))
    with pytest.raises(config.ArmCalibrationError):
        config.load_arm_calibration(str(bad))


def test_calibration_round_trip(tmp_path):
    path = str(tmp_path / "cal.json")
    cal = config.ArmCalibration(pen_down_z=97.5, pen_up_z=127.5, orientation=(-170.0, 2.0, 90.0))
    config.save_arm_calibration(cal, path)
    assert config.load_arm_calibration(path) == cal


def test_serial_settings_default_and_env_override(monkeypatch):
    monkeypatch.delenv(config.SERIAL_PORT_ENV, raising=False)
    monkeypatch.delenv(config.BAUDRATE_ENV, raising=False)
    assert config.serial_port() == "/dev/serial0"
    assert config.baudrate() == "1000000"
    monkeypatch.setenv(config.SERIAL_PORT_ENV, "COM7")
    monkeypatch.setenv(config.BAUDRATE_ENV, "115200")
    assert config.serial_port() == "COM7"
    assert config.baudrate() == "115200"


def test_project_paths_are_absolute_and_rooted_at_the_repo():
    for path in (config.CORNERS_PATH, config.ARM_CALIBRATION_PATH, config.CAMERA_CONFIG_PATH):
        assert os.path.isabs(path)
        assert os.path.dirname(path) == config.CONFIG_DIR
    assert config.CONFIG_DIR == os.path.join(config.PROJECT_ROOT, "config")
    assert os.path.exists(os.path.join(config.PROJECT_ROOT, "sudoku_robot", "config.py"))


def test_legacy_location_hint_points_at_old_root_copies(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(config, "CONFIG_DIR", str(tmp_path / "config"))
    new = str(tmp_path / "config" / "corners.json")
    assert config.legacy_location_hint(new) == ""
    (tmp_path / "corners.json").write_text("{}")
    assert "move it into" in config.legacy_location_hint(new)


class _FakeMyCobot:
    def __init__(self, port, baud):
        self.port, self.baud = port, baud


def test_real_controller_reads_pen_settings_from_arm_calibration(tmp_path, monkeypatch):
    monkeypatch.setattr(arm_controller, "MyCobot280", _FakeMyCobot)
    path = str(tmp_path / "cal.json")
    config.save_arm_calibration(
        config.ArmCalibration(pen_down_z=91.0, pen_up_z=121.0, orientation=(1.0, 2.0, 3.0)), path
    )
    monkeypatch.setenv(config.SERIAL_PORT_ENV, "COM9")

    arm = arm_controller.MyCobotArmController(calibration_path=path)
    assert (arm.pen_down_z, arm.pen_up_z, arm.orientation) == (91.0, 121.0, (1.0, 2.0, 3.0))
    assert arm.port == "COM9"
    assert arm.home_xy == config.DEFAULT_HOME_XY

    # Explicit arguments still override the file for one run.
    arm = arm_controller.MyCobotArmController(pen_down_z=90.0, calibration_path=path)
    assert arm.pen_down_z == 90.0 and arm.pen_up_z == 121.0


def test_teach_tools_share_the_same_calibration(tmp_path, monkeypatch):
    from sudoku_robot.writer import teach

    path = str(tmp_path / "cal.json")
    monkeypatch.setattr(config, "ARM_CALIBRATION_PATH", path)
    config.save_arm_calibration(
        config.ArmCalibration(pen_down_z=99.0, pen_up_z=130.0, orientation=(0.0, 0.0, 0.0))
    )

    class FakeMc:
        def get_coords(self):
            return [1.0, -200.0, 97.0, -175.0, 1.0, 90.0]

    monkeypatch.setattr(teach.time, "sleep", lambda _s: None)
    teach.capture_surface(FakeMc())
    cal = config.load_arm_calibration()
    assert cal.pen_down_z == 97.0
    assert cal.orientation == (-175.0, 1.0, 90.0)
    assert cal.pen_up_z == 130.0          # kept
    assert teach._surface_z() == 97.0     # teach's touch checks use the same value


def test_teach_frees_arm_with_release_and_relocks_with_focus(monkeypatch):
    from sudoku_robot.writer import teach

    calls = []

    class FakeMc:
        def release_all_servos(self):
            calls.append("release")

        def focus_all_servos(self):
            calls.append("focus")

        def power_off(self):  # must never be used: it breaks get_coords()
            calls.append("power_off")

    monkeypatch.setattr(teach.time, "sleep", lambda _s: None)
    teach.release_servos_for_teaching(FakeMc())
    teach.lock_servos_after_teaching(FakeMc())
    assert calls == ["release", "focus"]


def test_font_lookup_never_crashes_and_env_override_wins(tmp_path, monkeypatch):
    font = fonts.load_font(40, bold=True)
    assert font is not None
    if fonts.find_font(bold=True):
        monkeypatch.setenv(fonts.FONT_ENV, fonts.find_font(bold=True))
        assert fonts.find_reference_font(bold=True) == fonts.find_font(bold=True)


def test_font_falls_back_to_pillow_builtin(monkeypatch):
    monkeypatch.delenv(fonts.FONT_ENV, raising=False)
    monkeypatch.setattr(fonts, "find_font", lambda bold=True: None)
    font = fonts.load_font(40, bold=True)
    assert font.getbbox("8")[3] > 0
