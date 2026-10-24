"""
"Humanizer": solves a Sudoku the way a person does -- by pencil-marking
candidates and applying named logical techniques, simplest first --
and records a step-by-step explanation of every deduction.

This is a separate engine, not a variant of BacktrackingSolver: it
never imports or calls the other solvers, keeps explicit candidate
sets per cell, and only guesses when no technique below can make
progress. On every step it re-scans the WHOLE grid and applies the
simplest technique that currently works anywhere, in this order (the
order most human solvers learn and reach for them):

    1. naked single      a cell with only one candidate left
    2. hidden single     a digit that fits in only one cell of a box/row/column
    3. naked pair        two cells in a unit with the same two candidates
                         -> those digits leave the rest of the unit
    4. hidden pair       two digits confined to the same two cells of a unit
                         -> those cells lose every other candidate
    5. pointing pair     a digit confined, inside a box, to one row/column
                         -> it leaves that row/column outside the box
    6. box-line reduction  a digit confined, inside a row/column, to one box
                         -> it leaves the rest of that box
    7. guess (fallback)  pick a cell with the fewest candidates, try a
                         digit, keep solving by logic; undo on contradiction

Techniques 3-6 only remove pencil marks; after any of them the solver
goes straight back to looking for singles, as a person would.

Which cell gets filled next is decided by the techniques, never by
position: when several deductions of the same technique are available,
the one in the most-filled unit (the most "obvious" one, which a person
scanning the grid notices first) wins. The resulting fill order jumps
around the grid rather than running row by row.

Output: `solver.steps` (every placement and elimination, with a
plain-English reason), `solver.placement_order` (cells in the order
they were filled), `solver.cell_techniques` ({cell: technique}), and
`solver.format_steps()` for printing. Cells filled by a guess are
technique "guess"; cells deduced by logic only after a guess are
flagged `after_guess=True` (logic, but conditional on that guess).
"""
from dataclasses import dataclass, field
from itertools import combinations
from typing import Dict, List, Optional, Set, Tuple

from .base import SudokuSolver
from ..utils import Grid, copy_grid

Cell = Tuple[int, int]

NAKED_SINGLE = "naked single"
HIDDEN_SINGLE = "hidden single"
NAKED_PAIR = "naked pair"
HIDDEN_PAIR = "hidden pair"
POINTING_PAIR = "pointing pair"
BOX_LINE_REDUCTION = "box-line reduction"
GUESS = "guess"

#: In the order the solver tries them.
TECHNIQUES = (NAKED_SINGLE, HIDDEN_SINGLE, NAKED_PAIR, HIDDEN_PAIR, POINTING_PAIR, BOX_LINE_REDUCTION)
LOGIC_TECHNIQUES = frozenset(TECHNIQUES)


def _box_of(r: int, c: int) -> int:
    return (r // 3) * 3 + c // 3


# A "unit" is a box, row or column: (label, cells). Boxes come first,
# because cross-hatching a box is how most people find digits.
_BOXES = [[(br * 3 + i, bc * 3 + j) for i in range(3) for j in range(3)] for br in range(3) for bc in range(3)]
_ROWS = [[(r, c) for c in range(9)] for r in range(9)]
_COLS = [[(r, c) for r in range(9)] for c in range(9)]
UNITS: List[Tuple[str, List[Cell]]] = (
    [(f"box {b + 1}", cells) for b, cells in enumerate(_BOXES)]
    + [(f"row {r + 1}", cells) for r, cells in enumerate(_ROWS)]
    + [(f"column {c + 1}", cells) for c, cells in enumerate(_COLS)]
)
_PEERS: Dict[Cell, Set[Cell]] = {
    (r, c): (set(_ROWS[r]) | set(_COLS[c]) | set(_BOXES[_box_of(r, c)])) - {(r, c)}
    for r in range(9) for c in range(9)
}


def cell_name(cell: Cell) -> str:
    """1-based, as a person reads a grid: r1c1 is the top-left cell."""
    return f"r{cell[0] + 1}c{cell[1] + 1}"


@dataclass
class Step:
    technique: str
    #: Placements set cell+digit; eliminations list the removed (cell, digit) pencil marks.
    cell: Optional[Cell] = None
    digit: Optional[int] = None
    eliminations: Tuple[Tuple[Cell, int], ...] = ()
    reason: str = ""
    #: True once any guess is active: this deduction depends on that guess.
    after_guess: bool = False

    @property
    def is_placement(self) -> bool:
        return self.cell is not None

    def describe(self) -> str:
        tag = "GUESS" if self.technique == GUESS else self.technique
        if self.after_guess and self.technique != GUESS:
            tag += " (after guess)"
        if self.is_placement:
            return f"{cell_name(self.cell)} = {self.digit}  [{tag}]  {self.reason}"
        removed = ", ".join(f"{d}@{cell_name(c)}" for c, d in self.eliminations)
        return f"eliminate {removed}  [{tag}]  {self.reason}"


class _State:
    """The grid plus a pencil-mark candidate set for every empty cell."""

    def __init__(self, grid: Grid, cands: List[List[Set[int]]]):
        self.grid = grid
        self.cands = cands

    @classmethod
    def from_grid(cls, grid: Grid) -> Optional["_State"]:
        state = cls([[0] * 9 for _ in range(9)], [[set(range(1, 10)) for _ in range(9)] for _ in range(9)])
        for r in range(9):
            for c in range(9):
                d = grid[r][c]
                if d:
                    if d not in state.cands[r][c]:
                        return None  # two equal givens in one unit
                    state.place((r, c), d)
        return state

    def copy(self) -> "_State":
        return _State(copy_grid(self.grid), [[set(s) for s in row] for row in self.cands])

    def place(self, cell: Cell, digit: int) -> None:
        r, c = cell
        self.grid[r][c] = digit
        self.cands[r][c] = set()
        for pr, pc in _PEERS[cell]:
            self.cands[pr][pc].discard(digit)

    def empty_cells(self) -> List[Cell]:
        return [(r, c) for r in range(9) for c in range(9) if self.grid[r][c] == 0]

    def is_complete(self) -> bool:
        return all(v for row in self.grid for v in row)

    def has_contradiction(self) -> bool:
        for r, c in self.empty_cells():
            if not self.cands[r][c]:
                return True
        for _label, cells in UNITS:
            placed = {self.grid[r][c] for r, c in cells}
            possible = set().union(*(self.cands[r][c] for r, c in cells))
            if (set(range(1, 10)) - placed) - possible:
                return True  # some digit has nowhere left to go in this unit
        return False

    def filled_in(self, cells: List[Cell]) -> int:
        return sum(1 for r, c in cells if self.grid[r][c])

    def obviousness(self, cell: Cell) -> int:
        """How full the fullest unit through `cell` is -- what makes a single jump out at a person."""
        r, c = cell
        return max(self.filled_in(_ROWS[r]), self.filled_in(_COLS[c]), self.filled_in(_BOXES[_box_of(r, c)]))


# -- Techniques: each returns the Step it would take, or None ---------------

def find_naked_single(state: _State) -> Optional[Step]:
    found = [cell for cell in state.empty_cells() if len(state.cands[cell[0]][cell[1]]) == 1]
    if not found:
        return None
    cell = max(found, key=state.obviousness)
    (digit,) = state.cands[cell[0]][cell[1]]
    return Step(NAKED_SINGLE, cell, digit, reason=f"{digit} is the only candidate left in {cell_name(cell)}")


def find_hidden_single(state: _State) -> Optional[Step]:
    best = None  # (filled count, step)
    for label, cells in UNITS:
        filled = state.filled_in(cells)
        for digit in range(1, 10):
            spots = [(r, c) for r, c in cells if digit in state.cands[r][c]]
            if len(spots) == 1 and (best is None or filled > best[0]):
                best = (filled, Step(HIDDEN_SINGLE, spots[0], digit,
                                     reason=f"{cell_name(spots[0])} is the only place for {digit} in {label}"))
    return best[1] if best else None


def find_naked_pair(state: _State) -> Optional[Step]:
    for label, cells in UNITS:
        bivalue = [(r, c) for r, c in cells if len(state.cands[r][c]) == 2]
        for a, b in combinations(bivalue, 2):
            pair = state.cands[a[0]][a[1]]
            if pair != state.cands[b[0]][b[1]]:
                continue
            removed = tuple(((r, c), d) for r, c in cells if (r, c) not in (a, b)
                            for d in sorted(pair & state.cands[r][c]))
            if removed:
                digits = "/".join(map(str, sorted(pair)))
                return Step(NAKED_PAIR, eliminations=removed,
                            reason=f"{cell_name(a)} and {cell_name(b)} can only be {digits}, "
                                   f"so no other cell in {label} can be")
    return None


def find_hidden_pair(state: _State) -> Optional[Step]:
    for label, cells in UNITS:
        spots = {d: frozenset((r, c) for r, c in cells if d in state.cands[r][c]) for d in range(1, 10)}
        two_spot = [d for d in range(1, 10) if len(spots[d]) == 2]
        for d1, d2 in combinations(two_spot, 2):
            if spots[d1] != spots[d2]:
                continue
            keep = {d1, d2}
            removed = tuple(((r, c), d) for r, c in sorted(spots[d1])
                            for d in sorted(state.cands[r][c] - keep))
            if removed:
                a, b = sorted(spots[d1])
                return Step(HIDDEN_PAIR, eliminations=removed,
                            reason=f"{d1} and {d2} only fit in {cell_name(a)} and {cell_name(b)} "
                                   f"within {label}, so those cells can't hold anything else")
    return None


def find_pointing_pair(state: _State) -> Optional[Step]:
    for b, box in enumerate(_BOXES):
        for digit in range(1, 10):
            spots = [(r, c) for r, c in box if digit in state.cands[r][c]]
            if len(spots) < 2:
                continue
            for axis, line_name, lines in ((0, "row", _ROWS), (1, "column", _COLS)):
                indices = {cell[axis] for cell in spots}
                if len(indices) != 1:
                    continue
                (i,) = indices
                removed = tuple(((r, c), digit) for r, c in lines[i]
                                if (r, c) not in box and digit in state.cands[r][c])
                if removed:
                    return Step(POINTING_PAIR, eliminations=removed,
                                reason=f"in box {b + 1}, {digit} must be in {line_name} {i + 1}, "
                                       f"so it can't be elsewhere in {line_name} {i + 1}")
    return None


def find_box_line_reduction(state: _State) -> Optional[Step]:
    for line_name, lines in (("row", _ROWS), ("column", _COLS)):
        for i, line in enumerate(lines):
            for digit in range(1, 10):
                spots = [(r, c) for r, c in line if digit in state.cands[r][c]]
                if len(spots) < 2:
                    continue
                boxes = {_box_of(r, c) for r, c in spots}
                if len(boxes) != 1:
                    continue
                (b,) = boxes
                removed = tuple(((r, c), digit) for r, c in _BOXES[b]
                                if (r, c) not in line and digit in state.cands[r][c])
                if removed:
                    return Step(BOX_LINE_REDUCTION, eliminations=removed,
                                reason=f"in {line_name} {i + 1}, {digit} must be in box {b + 1}, "
                                       f"so it can't be elsewhere in box {b + 1}")
    return None


_FINDERS = (
    find_naked_single,
    find_hidden_single,
    find_naked_pair,
    find_hidden_pair,
    find_pointing_pair,
    find_box_line_reduction,
)


def apply_step(state: _State, step: Step) -> None:
    if step.is_placement:
        state.place(step.cell, step.digit)
    for (r, c), d in step.eliminations:
        state.cands[r][c].discard(d)


class HumanizerSolver(SudokuSolver):
    name = "humanizer"

    def __init__(self, max_guesses: int = 10_000):
        super().__init__()
        self.max_guesses = max_guesses
        self.steps: List[Step] = []

    # -- SudokuSolver interface ----------------------------------------------

    def solve(self, grid: Grid) -> Optional[Grid]:
        self.steps = []
        self._guesses = 0
        self._backtracks = 0
        state = _State.from_grid(grid)
        solved = None
        if state is not None:
            solved = self._solve(state, depth=0)
        self._finish_stats(solved is not None)
        return copy_grid(solved.grid) if solved else None

    # -- Explanation helpers ---------------------------------------------------

    @property
    def placements(self) -> List[Step]:
        return [s for s in self.steps if s.is_placement]

    @property
    def placement_order(self) -> List[Cell]:
        """Cells in the order they were filled -- the order a person would write them."""
        return [s.cell for s in self.placements]

    @property
    def cell_techniques(self) -> Dict[Cell, str]:
        return {s.cell: s.technique for s in self.placements}

    def format_steps(self, include_eliminations: bool = True) -> str:
        lines = []
        n = 0
        for step in self.steps:
            if step.is_placement:
                n += 1
                lines.append(f"{n:3d}. {step.describe()}")
            elif include_eliminations:
                lines.append(f"     {step.describe()}")
        s = self.stats
        lines.append("")
        lines.append(
            f"{s['logic_placements']} cell(s) by logic "
            f"({s['logic_after_guess']} of them after a guess), "
            f"{s['guess_placements']} by guessing; {s['backtracks']} guess(es) undone."
        )
        lines.append("placements by technique: "
                     + ", ".join(f"{k}: {v}" for k, v in s["placements_by_technique"].items() if v))
        return "\n".join(lines)

    # -- The search ----------------------------------------------------------------

    def _solve(self, state: _State, depth: int) -> Optional[_State]:
        while True:
            if state.has_contradiction():
                return None
            if state.is_complete():
                return state
            step = next((s for s in (find(state) for find in _FINDERS) if s is not None), None)
            if step is None:
                break  # no technique applies anywhere: time to guess
            step.after_guess = depth > 0
            apply_step(state, step)
            self.steps.append(step)

        if self._guesses >= self.max_guesses:
            return None
        # A person guesses on the most constrained cell (ideally a two-way choice).
        cell = min(state.empty_cells(),
                   key=lambda rc: (len(state.cands[rc[0]][rc[1]]), -state.obviousness(rc)))
        options = sorted(state.cands[cell[0]][cell[1]])
        for digit in options:
            self._guesses += 1
            trial = state.copy()
            mark = len(self.steps)
            others = ", ".join(str(d) for d in options if d != digit)
            self.steps.append(Step(GUESS, cell, digit, after_guess=True,
                                   reason=f"no logical step applies; trying {digit} "
                                          f"(other options: {others})"))
            trial.place(cell, digit)
            result = self._solve(trial, depth + 1)
            if result is not None:
                return result
            del self.steps[mark:]  # this guess led to a contradiction: forget its whole branch
            self._backtracks += 1
        return None

    def _finish_stats(self, solved: bool) -> None:
        placements = self.placements if solved else []
        by_technique = {t: 0 for t in TECHNIQUES + (GUESS,)}
        for s in placements:
            by_technique[s.technique] += 1
        eliminations = {t: 0 for t in TECHNIQUES}
        for s in self.steps if solved else []:
            if not s.is_placement:
                eliminations[s.technique] += len(s.eliminations)
        self.stats = {
            # nodes_expanded/backtracks keep the benchmark's columns meaningful:
            # for this solver a "node" is a guess, since logic steps never branch.
            "nodes_expanded": self._guesses,
            "backtracks": self._backtracks,
            "guesses": self._guesses,
            "logic_placements": sum(1 for s in placements if s.technique != GUESS),
            "logic_after_guess": sum(1 for s in placements if s.technique != GUESS and s.after_guess),
            "guess_placements": by_technique[GUESS],
            "placements_by_technique": by_technique,
            "eliminations_by_technique": eliminations,
        }
