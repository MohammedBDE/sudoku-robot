"""
Regenerates the digit "database" from the stroke definitions in the code:

    python scripts/export_digits.py            # writes teach_data/digits.json and calib/digits_sheet.png
    python scripts/export_digits.py --print    # also prints a table of all nine digits

Run it again after changing sudoku_robot/writer/digit_strokes.py. The test
suite fails while teach_data/digits.json is out of date.
"""
import argparse
import os
import sys

# scripts/export_digits.py -> scripts -> project root: put the folder containing
# the sudoku_robot package on the import path, so this works from any directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sudoku_robot.writer import digit_database  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Export how the robot writes digits 1-9.")
    parser.add_argument("--print", action="store_true", help="also print a table of all nine digits")
    parser.add_argument("--no-image", action="store_true", help="only write the JSON file")
    args = parser.parse_args(argv)

    print("wrote", digit_database.save_database())
    if not args.no_image:
        print("wrote", digit_database.render_sheet())
    if args.print:
        db = digit_database.build_database()
        print(f"\n{'digit':<6}{'lines':<7}{'pen moves':<11}path")
        for digit, rec in db["digits"].items():
            extra = f"   (retraces {', '.join(rec['retraced_segments'])})" if rec["retraced_segments"] else ""
            print(f"{digit:<6}{rec['line_count']:<7}{rec['pen_moves']:<11}{' > '.join(rec['path'])}{extra}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
