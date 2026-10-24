"""
Renders sample puzzles as print-ready PNGs (A4 landscape by default).

This exists for physical testing: print a puzzle, hand-solve or feed
it to a solver, and later use it as the paper the robot arm writes
onto. The grid is printed at exactly config.CELL_SIZE_MM (20mm) per
cell -- the cell size TaughtCornersGridLayout and the corner check
assume -- and that size is stamped in the sidebar so a printout can be
verified with a ruler. Print at 100% / "actual size" (never "fit to
page"), or every cell position the arm computes will be off.

Digits are drawn in DejaVu Sans Bold (via sudoku_robot.fonts), the
same font the camera's digit recognizer uses as its templates.

Why landscape: the mycobot 280's 280mm working radius is measured
from its base joint in every direction, so its comfortable writing
area is a wide, shallow wedge in front of it -- wide because rotating
the base joint sweeps a large angle, shallow because getting too close
to the base risks singularities/self-collision and getting too close
to the full 280mm risks losing accuracy (Elephant Robotics quotes
+/-0.5mm repeatability, which is worst near full extension). A grid
oriented landscape sits within one comfortable, roughly constant
distance from the base and just sweeps sideways; a portrait grid would
make the arm write both close-in and near-max-reach within the same
puzzle. (Note: rotating the page does NOT make a square grid bigger --
it's still capped by A4's short 210mm edge either way. What landscape
buys here is putting the title/info text in a side column instead of
stacking it above the grid, which reclaims that vertical space.)

Run with:

    python -m sudoku_robot.puzzles.render
"""
import os
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from .. import config, fonts

from .samples import PUZZLES, Puzzle

MM_PER_INCH = 25.4


def _mm_to_px(mm: float, dpi: int) -> int:
    return round(mm / MM_PER_INCH * dpi)


def _load_font(size_px: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    # Shared with vision/digit_recognizer.py so printed digits and the
    # recognizer's templates come from the same font (see fonts.py).
    return fonts.load_font(size_px, bold=bold)


def render_puzzle_png(
    puzzle: Puzzle,
    path: str,
    page_mm=(297.0, 210.0),  # A4 landscape (width, height) -- see module docstring for why
    dpi: int = 300,
    margin_mm: float = 15.0,
    sidebar_mm: float = 80.0,  # left column for title/info, freeing full height for the grid
    gap_mm: float = 7.0,       # space between sidebar and grid
    solution_grid: Optional[list] = None,
    cell_mm: float = config.CELL_SIZE_MM,
) -> None:
    """
    Render one Puzzle to a print-ready landscape PNG at `path`.

    If `solution_grid` is given (a solved Grid from either solver),
    the cells that were empty in `puzzle.grid` are also filled in,
    in a different color from the original clues -- a fast, always-
    correct way to show "what the solver figured out" on paper, for
    when the physical arm's own handwriting isn't the part being
    demonstrated.
    """
    page_w = _mm_to_px(page_mm[0], dpi)
    page_h = _mm_to_px(page_mm[1], dpi)

    # The grid is always exactly 9 * cell_mm (180mm at the default
    # 20mm/cell) -- the physical cell size the arm-side geometry
    # (TaughtCornersGridLayout, corner_check) assumes. It's never
    # stretched to fill the page; if it doesn't fit, that's an error
    # rather than a silently rescaled grid.
    height_budget_mm = page_mm[1] - 2 * margin_mm
    width_budget_mm = page_mm[0] - 2 * margin_mm - sidebar_mm - gap_mm
    grid_mm = 9 * cell_mm
    if grid_mm > min(height_budget_mm, width_budget_mm) + 1e-9:
        raise ValueError(
            f"A {grid_mm:.0f}mm grid ({cell_mm}mm cells) doesn't fit the page's "
            f"{min(height_budget_mm, width_budget_mm):.0f}mm budget -- reduce margins or cell_mm."
        )

    grid_px = _mm_to_px(grid_mm, dpi)
    cell_px = grid_px / 9.0

    margin_px = _mm_to_px(margin_mm, dpi)
    sidebar_px = _mm_to_px(sidebar_mm, dpi)
    gap_px = _mm_to_px(gap_mm, dpi)

    grid_x0 = margin_px + sidebar_px + gap_px
    grid_y0 = (page_h - grid_px) // 2  # vertically centered in the page

    img = Image.new("RGB", (page_w, page_h), "white")
    draw = ImageDraw.Draw(img)

    # -- Sidebar text: title, difficulty, and the grid's real mm size
    # (so the printout's scale can be checked with a ruler) -- all stacked in the left column instead of
    # above the grid, so the grid keeps the full page height.
    title_font = _load_font(_mm_to_px(8, dpi), bold=True)
    label_font = _load_font(_mm_to_px(5, dpi))
    sidebar_x = margin_px   # text is left-aligned to the page margin, so it stays inside the sidebar column
    lines_top = grid_y0 + _mm_to_px(4, dpi)

    draw.text((sidebar_x, lines_top), "Sudoku", font=title_font, fill="black", anchor="lm")
    # Multi-line blocks are top-anchored ("la") so each grows downward
    # from a fixed start and adding a line can't make blocks overlap.
    draw.text(
        (sidebar_x, lines_top + _mm_to_px(8, dpi)),
        f"{puzzle.name}\n({puzzle.difficulty})",
        font=label_font, fill="black", anchor="la", align="left",
    )
    draw.text(
        (sidebar_x, lines_top + _mm_to_px(26, dpi)),
        f"Grid: {grid_mm:.0f}x{grid_mm:.0f}mm\n"
        f"Cell: {grid_mm / 9:.1f}mm\n"
        f"{dpi} DPI\n"
        f"Font: {fonts.describe_font(bold=True)}\n"
        "Print at 100% scale",
        font=label_font, fill="black", anchor="la", align="left",
    )
    draw.text(
        (sidebar_x, grid_y0 + grid_px - _mm_to_px(6, dpi)),
        "sudoku_robot project", font=label_font, fill="black", anchor="lm",
    )

    # -- Grid lines: thin per-cell, thick every 3 cells (box borders) --
    thin_px = max(1, _mm_to_px(0.3, dpi))
    thick_px = max(1, _mm_to_px(1.0, dpi))
    for i in range(10):
        width = thick_px if i % 3 == 0 else thin_px
        x = grid_x0 + round(i * cell_px)
        y = grid_y0 + round(i * cell_px)
        draw.line([(x, grid_y0), (x, grid_y0 + grid_px)], fill="black", width=width)
        draw.line([(grid_x0, y), (grid_x0 + grid_px, y)], fill="black", width=width)

    # -- Clue digits (blank cells stay blank -- that's what makes it a puzzle) --
    digit_font = _load_font(round(cell_px * 0.55), bold=True)
    grid = puzzle.grid
    for r in range(9):
        for c in range(9):
            v = grid[r][c]
            if v == 0:
                continue
            cx = grid_x0 + (c + 0.5) * cell_px
            cy = grid_y0 + (r + 0.5) * cell_px
            draw.text((cx, cy), str(v), font=digit_font, fill="black", anchor="mm")

    # -- Solver-filled digits, in a different color from the original clues --
    if solution_grid is not None:
        for r in range(9):
            for c in range(9):
                if grid[r][c] != 0:
                    continue  # a pre-printed clue, already drawn above
                v = solution_grid[r][c]
                cx = grid_x0 + (c + 0.5) * cell_px
                cy = grid_y0 + (r + 0.5) * cell_px
                draw.text((cx, cy), str(v), font=digit_font, fill=(30, 90, 200), anchor="mm")

    # Embedding the DPI lets a print dialog's "actual size" reproduce the true
    # millimetre scale; without it, the printer has to guess.
    img.save(path, "PNG", dpi=(dpi, dpi))


def render_all(out_dir: str, puzzles: Optional[list] = None) -> list:
    """Render every puzzle (or a given subset) into `out_dir`. Returns the file paths."""
    os.makedirs(out_dir, exist_ok=True)
    puzzles = puzzles if puzzles is not None else PUZZLES
    paths = []
    for puzzle in puzzles:
        path = os.path.join(out_dir, f"{puzzle.name}.png")
        render_puzzle_png(puzzle, path)
        paths.append(path)
    return paths


def main(argv=None) -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Render sample puzzles as print-ready PNGs.")
    parser.add_argument(
        "--puzzle", action="append", choices=[p.name for p in PUZZLES],
        help="Render only this puzzle (repeatable). Default: all of them.",
    )
    parser.add_argument("--out-dir", default=config.PRINTABLE_PUZZLES_DIR)
    args = parser.parse_args(argv)

    if not fonts.is_reference_font(bold=True):
        print(f"[warn] DejaVu Sans not found -- rendering with {fonts.describe_font(bold=True)}. "
              "The camera's digit recognizer is tuned for DejaVu Sans Bold; see sudoku_robot/fonts.py.")
    selected = [p for p in PUZZLES if p.name in args.puzzle] if args.puzzle else None
    for path in render_all(os.path.abspath(args.out_dir), selected):
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
