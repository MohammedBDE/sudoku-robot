"""
Command-line entry point for solving a single puzzle, running the
full solver benchmark (backtracking, RL, humanizer), reading a puzzle from the camera,
checking the taught grid corners, or writing a solved puzzle onto
paper. Examples:

    python -m sudoku_robot --solver backtracking --puzzle easy_1
    python -m sudoku_robot --solver rl --puzzle near_empty_17
    python -m sudoku_robot --solver humanizer --puzzle hard_1 --explain   # which technique filled each cell
    python -m sudoku_robot --benchmark
    python -m sudoku_robot --check-corners                       # validate corners.json
    python -m sudoku_robot --puzzle easy_1 --write               # simulated arm, just logs moves
    python -m sudoku_robot --puzzle physical_demo --write --real-arm   # drives the physical mycobot 280
    python -m sudoku_robot --from-camera                         # read a real puzzle via the camera
    python -m sudoku_robot --from-camera --write --real-arm      # the full loop: see, solve, write
"""
import argparse
import sys
from time import perf_counter
from typing import Optional

from . import config
from .benchmark.compare import print_report, run_all
from .puzzles.samples import PUZZLES, get_puzzle
from .solver import AVAILABLE_STRATEGIES, get_solver
from .utils import Grid, is_valid_solution, print_grid
from .writer import (
    MyCobotArmController,
    PlaceholderGridLayout,
    SimulatedArmController,
    TaughtCornersGridLayout,
    write_solution,
)
from .writer.corner_check import check_corners_file, format_report
from .writer.pipeline import DEFAULT_WRITE_MODE, WRITE_MODES


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sudoku solver (backtracking, RL or humanizer) + mycobot 280 pen writer.")
    parser.add_argument(
        "--solver", choices=list(AVAILABLE_STRATEGIES), default="backtracking",
        help="Which solving strategy to use.",
    )
    parser.add_argument(
        "--puzzle", choices=[p.name for p in PUZZLES], default="easy_1",
        help="Which sample puzzle to solve. Ignored if --from-camera is given.",
    )
    parser.add_argument(
        "--from-camera", action="store_true",
        help="Read the puzzle from the iPhone camera instead of a sample puzzle "
             "(see vision/ -- needs config/camera_config.json set up first).",
    )
    parser.add_argument(
        "--benchmark", action="store_true",
        help="Run all strategies against all sample puzzles and print a comparison table.",
    )
    parser.add_argument(
        "--check-corners", action="store_true",
        help="Validate corners.json (edge lengths, 90-degree corner, reach of all 81 cells) and exit.",
    )
    parser.add_argument(
        "--write", action="store_true",
        help="After solving, write the solution onto paper (simulated arm by default).",
    )
    parser.add_argument(
        "--real-arm", action="store_true",
        help="With --write, drive the physical mycobot 280 instead of the simulated arm. "
             "Cell positions come from the hand-taught config/corners.json (TaughtCornersGridLayout), "
             "pen height/orientation from config/arm_calibration.json. corners.json is validated "
             "first and the write is refused if it fails (see --check-corners).",
    )
    parser.add_argument(
        "--ignore-corner-check", action="store_true",
        help="With --write --real-arm, write even if corners.json fails validation. "
             "Unreachable cells are then skipped; misplaced ones are written where the corners say.",
    )
    parser.add_argument(
        "--yes", action="store_true",
        help="With --write --real-arm, skip the interactive physical-safety confirmation. "
             "Only use this once you already trust the setup.",
    )
    parser.add_argument(
        "--write-mode", choices=list(WRITE_MODES), default=DEFAULT_WRITE_MODE,
        help="With --write: 'digit' draws the full seven-segment digit shape, 'mark' just presses "
             f"the pen down once per cell (no lateral motion while down). Default: '{DEFAULT_WRITE_MODE}' "
             "-- see writer/pipeline.py for why.",
    )
    parser.add_argument(
        "--explain", action="store_true",
        help="With --solver humanizer: print the step-by-step log of which technique "
             "filled each cell (and every candidate elimination along the way).",
    )
    return parser


def solve_grid(strategy: str, original_grid: Grid, label: str, explain: bool = False):
    """Solve and print; returns (solution or None, the solver instance that produced it)."""
    solver = get_solver(strategy)

    print(f"Solving '{label}' with '{strategy}'...\n")
    print("Input:")
    print_grid(original_grid)

    start = perf_counter()
    solution = solver.solve(original_grid)
    elapsed_ms = (perf_counter() - start) * 1000

    print("\nSolution:" if solution else "\nNo solution found.")
    if solution:
        print_grid(solution)
        ok = is_valid_solution(solution, given=original_grid)                                 
        summary = {k: v for k, v in solver.stats.items() if not isinstance(v, dict)}
        print(f"\nvalid: {ok}   time: {elapsed_ms:.2f} ms   stats: {summary}")

    if explain:
        if hasattr(solver, "format_steps"):
            if solution:
                print("\nStep by step:")
                print(solver.format_steps())
        else:
            print(f"\n--explain: '{strategy}' doesn't record techniques -- use --solver humanizer.")

    return solution, solver


def read_grid_from_camera() -> Optional[Grid]:
    # Imported lazily: importing sudoku_robot.vision pulls in cv2,
    # which every other CLI path (solving a sample puzzle, running the
    # benchmark) has no reason to require.
    try:
        import cv2  # noqa: F401
    except ImportError:
        print("--from-camera needs OpenCV (opencv-python-headless): pip install -r requirements.txt",
              file=sys.stderr)
        return None
    from .vision.camera_config import CameraConfigError
    from .vision.camera_source import CameraCaptureError
    from .vision.grid_detector import GridDetectionError
    from .vision.pipeline import capture_and_read_grid

    print("Capturing a frame from the camera and reading the grid...")
    try:
        return capture_and_read_grid()
    except (CameraConfigError, CameraCaptureError, GridDetectionError) as e:
        print(f"Failed to read the puzzle from the camera:\n{e}", file=sys.stderr)
        return None


def main(argv=None) -> None:
    args = build_parser().parse_args(argv)
    if args.benchmark:
        print_report(run_all())
        return

    if args.check_corners:
        report = check_corners_file(config.CORNERS_PATH)
        print(format_report(report, config.CORNERS_PATH))
        sys.exit(0 if report.ok else 1)

    if args.from_camera:
        original_grid = read_grid_from_camera()
        if original_grid is None:
            sys.exit(1)
        solution, solver = solve_grid(args.solver, original_grid, label="camera capture", explain=args.explain)
    else:
        puzzle = get_puzzle(args.puzzle)
        original_grid = puzzle.grid
        solution, solver = solve_grid(args.solver, original_grid,
                                      label=f"{puzzle.name} ({puzzle.difficulty})", explain=args.explain)

    if args.write:
        if solution is None:
            print("\nSkipping --write: no solution to write.")
            return
        if args.real_arm:
            report = check_corners_file(config.CORNERS_PATH)
            if not report.ok:
                print("\n" + format_report(report, config.CORNERS_PATH), file=sys.stderr)
                if not args.ignore_corner_check:
                    print("\nRefusing to write with the real arm (pass --ignore-corner-check to override).",
                          file=sys.stderr)
                    sys.exit(1)
            layout = TaughtCornersGridLayout.from_corners_file(config.CORNERS_PATH)
            arm = MyCobotArmController()
            print(f"\nWriting solution with REAL arm (config/corners.json, mode={args.write_mode})...")
        else:
            layout = PlaceholderGridLayout()
            arm = SimulatedArmController()
            print(f"\nWriting solution with simulated arm (PlaceholderGridLayout, mode={args.write_mode})...")
        # The Humanizer knows the order a person would fill the cells in,
        # and the pen follows it. Other solvers: row by row.
        order = getattr(solver, "placement_order", None)
        write_solution(original_grid, solution, arm, layout, auto_confirm=args.yes,
                       mode=args.write_mode, order=order)


if __name__ == "__main__":
    main()
