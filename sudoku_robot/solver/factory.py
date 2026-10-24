"""
Turns a strategy name (from a CLI flag, config file, etc.) into a
concrete SudokuSolver instance, so the rest of the codebase never has
to import BacktrackingSolver or RLSolver directly. Adding a third
strategy later means adding one line here -- nothing else changes.
"""
from .base import SudokuSolver
from .backtracking import BacktrackingSolver
from .humanizer import HumanizerSolver
from .rl.rl_solver import RLSolver

AVAILABLE_STRATEGIES = {
    "backtracking": BacktrackingSolver,
    "rl": RLSolver,
    "humanizer": HumanizerSolver,
}


def get_solver(strategy: str, **kwargs) -> SudokuSolver:
    try:
        cls = AVAILABLE_STRATEGIES[strategy]
    except KeyError:
        raise ValueError(
            f"Unknown solver strategy '{strategy}'. Available: {list(AVAILABLE_STRATEGIES)}"
        )
    return cls(**kwargs)
