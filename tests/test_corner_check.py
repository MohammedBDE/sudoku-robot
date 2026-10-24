import json

import pytest

from sudoku_robot import config
from sudoku_robot.writer.corner_check import check_corners, check_corners_file, format_report, main


def _corners(tl, tr, bl):
    return {"TL": list(tl) + [100.0], "TR": list(tr) + [100.0], "BL": list(bl) + [100.0]}


GOOD = _corners((80.0, -250.0), (-80.0, -250.0), (80.0, -90.0))


def test_well_taught_corners_pass():
    report = check_corners(GOOD)
    assert report.top_edge_mm == pytest.approx(160.0)
    assert report.left_edge_mm == pytest.approx(160.0)
    assert report.corner_angle_deg == pytest.approx(90.0)
    assert report.unreachable_cells == []
    assert report.ok
    assert "All checks passed" in format_report(report)


def test_small_errors_within_tolerance_pass():
    report = check_corners(_corners((80.0, -250.0), (-78.0, -252.0), (81.0, -93.0)))
    assert report.ok


def test_short_edge_fails():
    report = check_corners(_corners((80.0, -250.0), (30.0, -250.0), (80.0, -90.0)))
    assert not report.top_edge_ok
    assert report.left_edge_ok
    assert not report.ok


def test_skewed_corner_fails():
    # TL->BL leans 20mm sideways over 160mm: ~97 degrees.
    report = check_corners(_corners((80.0, -250.0), (-80.0, -250.0), (100.0, -90.0)))
    assert not report.angle_ok
    assert report.corner_angle_deg == pytest.approx(97.1, abs=0.1)


def test_out_of_reach_cells_are_flagged():
    # A correctly shaped grid, but pushed too far from the base.
    report = check_corners(_corners((80.0, -330.0), (-80.0, -330.0), (80.0, -170.0)))
    assert report.top_edge_ok and report.left_edge_ok and report.angle_ok
    assert not report.reach_ok
    flagged = {(r, c) for r, c, *_ in report.unreachable_cells}
    assert (0, 0) in flagged       # far row: out of reach
    assert (8, 4) not in flagged   # near-centre cell: fine


def test_missing_corner_raises():
    with pytest.raises(ValueError):
        check_corners({"TL": [0, 0], "TR": [1, 0]})


#: The hand-taught corners this robot originally had (Sep 2026): 49.6mm / 134.7mm
#: edges, a 135.5-degree corner, 21 cells out of reach. Kept as a real-world failure case.
OLD_HAND_TAUGHT = {
    "TL": [34.9, -272.6, 99.0, 172.7, 15.04, 131.12],
    "TR": [-12.4, -287.6, 95.5, -171.75, 1.79, 91.16],
    "BL": [98.0, -153.6, 102.2, 174.28, -5.88, 52.53],
}


def test_the_old_hand_taught_corners_are_rejected(tmp_path):
    path = tmp_path / "corners.json"
    path.write_text(json.dumps(OLD_HAND_TAUGHT))
    report = check_corners_file(str(path))
    assert not report.ok
    assert report.top_edge_mm == pytest.approx(49.6, abs=0.1)
    assert report.corner_angle_deg == pytest.approx(135.5, abs=0.1)
    assert len(report.unreachable_cells) == 21
    assert "RE-TEACH NEEDED" in format_report(report)


def test_missing_corners_file_names_the_fix(tmp_path):
    with pytest.raises(FileNotFoundError, match="jog_console"):
        check_corners_file(str(tmp_path / "nope.json"))


def test_main_exit_codes(tmp_path, capsys):
    good = tmp_path / "good.json"
    good.write_text(json.dumps(GOOD))
    assert main(["--corners-file", str(good)]) == 0
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(_corners((80.0, -250.0), (30.0, -250.0), (80.0, -90.0))))
    assert main(["--corners-file", str(bad)]) == 1
    assert "FAIL" in capsys.readouterr().out
