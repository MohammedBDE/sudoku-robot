import numpy as np
import pytest
from PIL import Image

from sudoku_robot import config
from sudoku_robot.puzzles.render import _mm_to_px, main, render_all, render_puzzle_png
from sudoku_robot.puzzles.samples import get_puzzle

DPI = 300


def _render(tmp_path, name="physical_demo", **kwargs):
    path = tmp_path / f"{name}.png"
    render_puzzle_png(get_puzzle(name), str(path), dpi=DPI, **kwargs)
    return path


def test_sidebar_text_stays_clear_of_the_grid(tmp_path):
    """The info text lives in the left column; none of it may run into the grid's left border."""
    with Image.open(_render(tmp_path)) as img:
        gray = np.array(img.convert("L"))
    grid_x0 = _mm_to_px(15 + 80 + 7, DPI)             # default margin + sidebar + gap
    strip = gray[:, grid_x0 - 60:grid_x0 - 15]         # just left of the thick border line
    assert strip.min() > 200, "printed text reaches the grid border"


def test_renders_a4_landscape_with_embedded_dpi(tmp_path):
    path = _render(tmp_path)
    with Image.open(path) as img:
        assert img.size == (_mm_to_px(297, DPI), _mm_to_px(210, DPI))
        assert img.info["dpi"] == pytest.approx((DPI, DPI), abs=0.01)


def test_grid_lines_are_exactly_one_cell_size_apart(tmp_path):
    """Grid lines must land every 20mm -- the scale the arm-side geometry assumes."""
    path = _render(tmp_path)
    with Image.open(path) as img:
        gray = np.array(img.convert("L"))

    # Columns that are dark along the full grid height are the vertical grid lines.
    grid_px = _mm_to_px(9 * config.CELL_SIZE_MM, DPI)
    grid_y0 = (gray.shape[0] - grid_px) // 2
    column_darkness = (gray[grid_y0: grid_y0 + grid_px, :] < 128).mean(axis=0)
    line_columns = np.where(column_darkness > 0.95)[0]

    # Group adjacent dark columns into lines and take each line's centre.
    groups = np.split(line_columns, np.where(np.diff(line_columns) > 1)[0] + 1)
    centres = [g.mean() for g in groups]
    assert len(centres) == 10
    spacing_mm = np.diff(centres) / DPI * 25.4
    assert spacing_mm == pytest.approx([config.CELL_SIZE_MM] * 9, abs=0.1)


def test_blank_cells_stay_blank_and_clues_are_drawn(tmp_path):
    path = _render(tmp_path)
    with Image.open(path) as img:
        gray = np.array(img.convert("L"))
    grid_px = _mm_to_px(180, DPI)
    cell_px = grid_px / 9
    x0 = _mm_to_px(15 + 80 + 7, DPI)
    y0 = (gray.shape[0] - grid_px) // 2

    def cell_ink(r, c):
        inset = cell_px * 0.2
        crop = gray[int(y0 + r * cell_px + inset): int(y0 + (r + 1) * cell_px - inset),
                    int(x0 + c * cell_px + inset): int(x0 + (c + 1) * cell_px - inset)]
        return (crop < 128).mean()

    grid = get_puzzle("physical_demo").grid
    assert grid[0][0] == 5 and cell_ink(0, 0) > 0.02
    assert grid[0][2] == 0 and cell_ink(0, 2) == 0.0


def test_grid_that_does_not_fit_is_an_error_not_a_rescale(tmp_path):
    with pytest.raises(ValueError):
        _render(tmp_path, cell_mm=25.0)


def test_solution_digits_fill_the_empty_cells(tmp_path):
    from sudoku_robot.solver import get_solver

    puzzle = get_puzzle("physical_demo")
    solved = get_solver("backtracking").solve(puzzle.grid)
    plain = _render(tmp_path, name="physical_demo")
    filled = tmp_path / "filled.png"
    render_puzzle_png(puzzle, str(filled), dpi=DPI, solution_grid=solved)
    with Image.open(plain) as a, Image.open(filled) as b:
        assert np.array(b).sum() < np.array(a).sum()  # more ink


def test_render_all_and_cli_select_puzzles(tmp_path, capsys):
    paths = render_all(str(tmp_path), [get_puzzle("easy_1")])
    assert [p.endswith("easy_1.png") for p in paths] == [True]
    main(["--puzzle", "physical_demo", "--out-dir", str(tmp_path / "out")])
    assert (tmp_path / "out" / "physical_demo.png").exists()
    assert "wrote" in capsys.readouterr().out
