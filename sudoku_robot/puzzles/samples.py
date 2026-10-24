"""
A small bank of sample puzzles used for manual testing and for the
solver comparison in benchmark/compare.py.

Puzzles are stored as 81-character strings (row-major, '0' = empty)
and parsed with utils.parse_grid so they're easy to paste in from
anywhere (most online Sudoku sources use this exact format).

Apart from physical_demo and inkala_hardest (well-known published puzzles),
these were produced with this project's own generator
(puzzles/generator.py) using fixed random seeds, at decreasing clue
counts -- so they're reproducible, guaranteed to have at least one
valid solution, and get progressively sparser (more search work).

They are NOT guaranteed to have a unique solution, and most don't:
the generator removes clues at random without checking uniqueness
(see solver.backtracking.count_solutions). Checked counts:

    easy_1         40 clues   10 solutions
    easy_2         38 clues   12 solutions
    physical_demo  30 clues   unique
    medium_1       30 clues   1000+ solutions
    hard_1         24 clues   1000+ solutions
    near_empty_17  19 clues   1000+ solutions
    inkala_hardest 21 clues   unique (a well-known extreme puzzle, not generated)

So the difficulty labels mean "how sparse / how much search", not
human difficulty, and any valid completion counts as solved. The name
`near_empty_17` is historical: the puzzle actually has 19 givens, and
unlike a true 17-clue Sudoku (17 is the proven minimum for a UNIQUE
solution) it has many solutions. The name is kept so existing
commands, benchmark output, and printable_puzzles/near_empty_17.png
stay valid. Use generator.make_puzzle(..., unique=True) for puzzles
that do have exactly one solution.
"""
from dataclasses import dataclass
from typing import List

from ..utils import Grid, parse_grid


@dataclass(frozen=True)
class Puzzle:
    name: str
    difficulty: str
    text: str

    @property
    def grid(self) -> Grid:
        return parse_grid(self.text)


PUZZLES: List[Puzzle] = [
    Puzzle(
        name="easy_1",
        difficulty="easy",
        text=(
            "083295417"
            "001800059"
            "095000862"
            "070000900"
            "000070000"
            "309682500"
            "108400705"
            "964750031"
            "000010008"
        ),
    ),
    Puzzle(
        name="easy_2",
        difficulty="easy",
        text=(
            "006000003"
            "150294780"
            "082300014"
            "300500109"
            "820609007"
            "900100008"
            "270403690"
            "500060000"
            "619005000"
        ),
    ),
    Puzzle(
        # The exact puzzle printed on the physical paper used for the
        # real-arm demo -- the classic example puzzle (widely used in
        # Sudoku tutorials), so `--puzzle physical_demo` matches what's
        # actually taped in front of the arm without needing the camera.
        name="physical_demo",
        difficulty="easy",
        text=(
            "530070000"
            "600195000"
            "098000060"
            "800060003"
            "400803001"
            "700020006"
            "060000280"
            "000419005"
            "000080079"
        ),
    ),
    Puzzle(
        name="medium_1",
        difficulty="medium",
        text=(
            "000000000"
            "069001005"
            "000095000"
            "020907000"
            "030000907"
            "790510482"
            "007000000"
            "043006298"
            "002089700"
        ),
    ),
    Puzzle(
        name="hard_1",
        difficulty="hard",
        text=(
            "260007104"
            "001400000"
            "504000008"
            "700000000"
            "000000005"
            "690324000"
            "080200006"
            "000000850"
            "050030000"
        ),
    ),
    Puzzle(
        name="near_empty_17",
        difficulty="hard",
        text=(
            "060000000"
            "041006075"
            "000000000"
            "070600100"
            "000230000"
            "000000700"
            "000400090"
            "007900080"
            "000003040"
        ),
    ),
    Puzzle(
        # Arto Inkala's widely published "world's hardest Sudoku" (2012):
        # 21 clues, exactly one solution, and no progress at all from
        # singles/pairs/pointing/box-line -- the Humanizer solver's
        # showcase for when a person has to fall back on guessing.
        name="inkala_hardest",
        difficulty="extreme",
        text=(
            "800000000"
            "003600000"
            "070090200"
            "050007000"
            "000045700"
            "000100030"
            "001000068"
            "008500010"
            "090000400"
        ),
    ),
]


def get_puzzle(name: str) -> Puzzle:
    for p in PUZZLES:
        if p.name == name:
            return p
    raise ValueError(f"Unknown puzzle '{name}'. Available: {[p.name for p in PUZZLES]}")
