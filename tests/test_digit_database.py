import json
import os

from sudoku_robot.writer import digit_database
from sudoku_robot.writer.digit_database import ANCHORS, build_database, format_database
from sudoku_robot.writer.digit_strokes import _DIGIT_SEGMENTS, _SEGMENTS


def test_json_file_matches_the_code_exactly():
    """teach_data/digits.json must be regenerated (scripts/export_digits.py) whenever digit_strokes.py changes."""
    with open(digit_database.DIGITS_JSON_PATH, encoding="utf-8") as fh:
        on_disk = fh.read()
    assert on_disk == format_database(build_database()), "run: python scripts/export_digits.py"
    assert json.loads(on_disk) == json.loads(json.dumps(build_database()))


def test_every_digit_one_to_nine_is_present():
    digits = build_database()["digits"]
    assert sorted(digits) == [str(d) for d in range(1, 10)]


def test_each_path_draws_exactly_the_segments_of_its_digit():
    name_of = {frozenset(ANCHORS[p] for p in ends): n for n, ends in _SEGMENTS.items()}
    for digit, rec in build_database()["digits"].items():
        path = rec["path"]
        walked = {name_of[frozenset(pair)] for pair in zip(path, path[1:])}
        assert walked == set(_DIGIT_SEGMENTS[int(digit)]), digit
        assert rec["line_count"] == len(path) - 1
        assert rec["pen_moves"] == len(path) + 2          # travel, pen down, len-1 draws, pen up


def test_only_three_and_four_retrace_a_segment():
    retraced = {d: r["retraced_segments"] for d, r in build_database()["digits"].items() if r["retraced_segments"]}
    assert set(retraced) == {"3", "4"}


def test_sheet_image_is_rendered(tmp_path):
    out = digit_database.render_sheet(str(tmp_path / "sheet.png"))
    assert os.path.getsize(out) > 5000
