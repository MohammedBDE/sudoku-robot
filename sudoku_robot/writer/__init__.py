"""
Physical writing: given a solved Sudoku grid (from either solving
strategy), drive a pen mounted on the mycobot 280 to write the solved
digits onto paper.

Where cells are on the table comes from a `GridLayout`:
`TaughtCornersGridLayout` (from the hand-taught config/corners.json, validated
by `corner_check.py`) for the real arm, `PlaceholderGridLayout` (an
idealised in-reach grid) for simulated runs. Pen heights/orientation
for the real arm come from config/arm_calibration.json (see config.py), and
digit shapes from `digit_strokes.py`. `teach.py` is a separate,
optional hand-teaching tool that nothing here depends on.

Typical usage:

    from sudoku_robot.writer import (
        PlaceholderGridLayout, SimulatedArmController, write_solution,
    )

    solved = get_solver("backtracking").solve(puzzle.grid)
    write_solution(puzzle.grid, solved, SimulatedArmController(), PlaceholderGridLayout())
"""
from .arm_controller import ArmController, ArmMotionError, MyCobotArmController, SimulatedArmController
from .grid_layout import GridLayout, PlaceholderGridLayout, TaughtCornersGridLayout
from .pen_writer import mark_cell, write_digit
from .pipeline import write_solution

__all__ = [
    "ArmController",
    "ArmMotionError",
    "SimulatedArmController",
    "MyCobotArmController",
    "GridLayout",
    "PlaceholderGridLayout",
    "TaughtCornersGridLayout",
    "write_digit",
    "mark_cell",
    "write_solution",
]
