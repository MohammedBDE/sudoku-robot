import importlib.util
import json
import math
import os

import pytest

from sudoku_robot import config
from sudoku_robot.writer import arm_controller, placement
from sudoku_robot.writer.arm_controller import SimulatedArmController
from sudoku_robot.writer.corner_check import check_corners, check_corners_file
from sudoku_robot.writer.grid_layout import TaughtCornersGridLayout

CAL = config.ArmCalibration(pen_down_z=98.9, pen_up_z=130.0, orientation=(-171.75, 1.79, 91.16))


def _xy(corners, key):
    return corners[key][:2]


def _layout(corners):
    return TaughtCornersGridLayout(tuple(_xy(corners, "TL")), tuple(_xy(corners, "TR")), tuple(_xy(corners, "BL")))


def test_default_plan_is_square_20mm_and_fully_reachable():
    corners = placement.plan_corners(calibration=CAL)
    report = check_corners(corners)
    assert report.ok
    assert report.top_edge_mm == pytest.approx(160.0)
    assert report.left_edge_mm == pytest.approx(160.0)
    assert report.corner_angle_deg == pytest.approx(90.0)
    assert report.unreachable_cells == []
    # Follows the convention: row 1 farther from the base (more negative Y), col 1 on the left (+X).
    assert _xy(corners, "TL") == [80.0, -250.0]
    assert _xy(corners, "TR") == [-80.0, -250.0]
    assert _xy(corners, "BL") == [80.0, -90.0]
    assert corners["TL"][2:] == [CAL.pen_down_z, *CAL.orientation]


@pytest.mark.parametrize("rotation", [-10.0, 5.0, 15.0])
def test_rotated_plans_stay_square_and_centred(rotation):
    corners = placement.plan_corners(rotation_deg=rotation, calibration=CAL)
    report = check_corners(corners)
    assert report.top_edge_mm == pytest.approx(160.0, abs=0.05)
    assert report.corner_angle_deg == pytest.approx(90.0, abs=0.05)
    assert _layout(corners).cell_center(4, 4) == pytest.approx(placement.DEFAULT_CENTER, abs=0.05)


def test_a_plan_too_far_from_the_base_fails_the_check():
    assert not check_corners(placement.plan_corners(center=(0.0, -230.0), calibration=CAL)).ok


def test_writing_a_plan_backs_up_the_old_file(tmp_path):
    path = tmp_path / "corners.json"
    path.write_text('{"TL": [1, 2], "TR": [3, 4], "BL": [5, 6]}')
    backup = placement.write_planned_corners(placement.plan_corners(calibration=CAL), str(path))
    assert backup and os.path.exists(backup)
    assert json.load(open(backup))["TL"] == [1, 2]
    written = json.load(open(path))
    assert "PLANNED" in written["_note"]
    assert check_corners_file(str(path)).ok          # the extra "_note" key doesn't break loading


def test_guided_placement_only_hovers_never_touches_the_paper():
    layout = _layout(placement.plan_corners(calibration=CAL))
    arm = SimulatedArmController(log=False)
    prompts = []
    placement.guide_paper_placement(arm, layout, clearance_mm=3.0, wait=prompts.append)

    assert not any(down for (_x, _y, down) in arm.moves)        # the pen never goes down
    expected = [layout.cell_center(r, c) for _label, (r, c) in placement.PLACEMENT_TARGETS]
    assert [h[:2] for h in arm.hovers] == expected
    assert all(h[2] == 3.0 for h in arm.hovers)
    assert len(prompts) == 4 and "r1c1" in prompts[0] and "r9c9" in prompts[3]
    assert arm.moves[0] == (*config.DEFAULT_HOME_XY, False) and arm.moves[-1] == arm.moves[0]
    assert not arm.connected


class _FakeMc:
    def __init__(self, *_a):
        self.sent = []

    def send_coords(self, coords, speed, mode):
        self.sent.append((coords, speed, mode))

    def get_error_information(self):
        return 0

    def clear_error_information(self):
        pass


def test_real_controller_hover_stops_above_the_paper(monkeypatch):
    monkeypatch.setattr(arm_controller, "MyCobot280", _FakeMc)
    arm = arm_controller.MyCobotArmController(pen_down_z=98.9, pen_up_z=130.0, orientation=(0, 0, 0),
                                              move_settle_s=0)
    arm._mc = _FakeMc()
    arm.hover(80.0, -250.0, clearance_mm=3.0)
    zs = [coords[2] for coords, _speed, _mode in arm._mc.sent]
    assert zs == [130.0, pytest.approx(101.9)]                  # travel high, then stop 3mm above the paper
    assert all(mode == 1 for _c, _s, mode in arm._mc.sent)      # straight-line (linear) moves only
    with pytest.raises(ValueError):
        arm.hover(0.0, -200.0, clearance_mm=0.0)


def _load_script():
    spec = importlib.util.spec_from_file_location("place_paper", os.path.join(config.SCRIPTS_DIR, "place_paper.py"))
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    return script


def test_place_paper_script_plan_only(tmp_path, monkeypatch, capsys):
    script = _load_script()
    target = tmp_path / "corners.json"
    monkeypatch.setattr(config, "CORNERS_PATH", str(target))
    assert script.main(["--plan-only"]) == 0
    assert check_corners_file(str(target)).ok
    assert "How to place the paper" in capsys.readouterr().out

    # An unreachable request is refused and leaves the file alone.
    before = target.read_text()
    assert script.main(["--plan-only", "--center-y", "-240"]) == 1
    assert target.read_text() == before


def test_place_paper_script_simulated_run(tmp_path, monkeypatch, capsys):
    script = _load_script()
    monkeypatch.setattr(config, "CORNERS_PATH", str(tmp_path / "corners.json"))
    assert script.main(["--simulate"]) == 0
    out = capsys.readouterr().out
    assert out.count("hover 3.0mm above") == 4
    assert "pen-down" not in out
