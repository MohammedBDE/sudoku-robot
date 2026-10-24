"""
Runs every registered solving strategy against every sample puzzle and
reports success rate + timing, so the strategies can be compared
directly on identical inputs. Run with:

    python -m sudoku_robot.benchmark.compare
"""
from dataclasses import dataclass
from time import perf_counter
from typing import List, Optional

from ..puzzles.samples import PUZZLES, Puzzle
from ..solver import AVAILABLE_STRATEGIES, get_solver
from ..utils import is_valid_solution


@dataclass
class Result:
    strategy: str
    puzzle: str
    difficulty: str
    solved: bool
    valid: bool
    elapsed_ms: float
    nodes_expanded: int
    backtracks: int


def run_one(strategy: str, puzzle: Puzzle) -> Result:
    solver = get_solver(strategy)

    start = perf_counter()
    solution = solver.solve(puzzle.grid)
    elapsed_ms = (perf_counter() - start) * 1000

    solved = solution is not None
    valid = solved and is_valid_solution(solution, given=puzzle.grid)

    return Result(
        strategy=strategy,
        puzzle=puzzle.name,
        difficulty=puzzle.difficulty,
        solved=solved,
        valid=valid,
        elapsed_ms=elapsed_ms,
        nodes_expanded=solver.stats.get("nodes_expanded", 0),
        backtracks=solver.stats.get("backtracks", 0),
    )


def run_all(strategies: Optional[List[str]] = None, puzzles: Optional[List[Puzzle]] = None) -> List[Result]:
    strategies = strategies or list(AVAILABLE_STRATEGIES)
    puzzles = puzzles or PUZZLES
    return [run_one(strategy, puzzle) for puzzle in puzzles for strategy in strategies]


def print_report(results: List[Result]) -> None:
    header = (
        f"{'puzzle':<16}{'difficulty':<11}{'strategy':<13}{'ok':<5}"
        f"{'time (ms)':<11}{'nodes':<8}{'backtracks':<11}"
    )
    print(header)
    print("-" * len(header))
    for r in results:
        ok = "yes" if r.valid else "NO"
        print(
            f"{r.puzzle:<16}{r.difficulty:<11}{r.strategy:<13}{ok:<5}"
            f"{r.elapsed_ms:<11.2f}{r.nodes_expanded:<8}{r.backtracks:<11}"
        )

    print()
    for strategy in sorted({r.strategy for r in results}):
        subset = [r for r in results if r.strategy == strategy]
        successes = sum(r.valid for r in subset)
        avg_ms = sum(r.elapsed_ms for r in subset) / len(subset)
        avg_nodes = sum(r.nodes_expanded for r in subset) / len(subset)
        print(f"{strategy:<13} success {successes}/{len(subset)}   avg time {avg_ms:7.2f} ms   avg nodes {avg_nodes:7.1f}")


if __name__ == "__main__":
    print_report(run_all())
