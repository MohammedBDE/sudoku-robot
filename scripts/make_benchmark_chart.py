"""
Runs every solving strategy on every sample puzzle (5 runs each, median time) and
draws the comparison as docs/benchmark_times.png, so the picture is always generated
from real measurements, never typed in by hand:

    python scripts/make_benchmark_chart.py
    python scripts/make_benchmark_chart.py --runs 10 --out some/other.png

Timings depend on the machine; the chart's footer records which one produced it.
"""
import argparse
import math
import os
import platform
import statistics
import sys

# scripts/make_benchmark_chart.py -> scripts -> project root: put the folder containing
# the sudoku_robot package on the import path, so this works from any directory.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PIL import Image, ImageDraw  # noqa: E402

from sudoku_robot.benchmark.compare import run_one  # noqa: E402
from sudoku_robot.fonts import load_font  # noqa: E402
from sudoku_robot.puzzles.samples import PUZZLES  # noqa: E402
from sudoku_robot.solver import AVAILABLE_STRATEGIES  # noqa: E402

COLORS = {"backtracking": "#2563eb", "rl": "#7c3aed", "humanizer": "#059669"}
LABELS = {"backtracking": "Backtracking", "rl": "RL-guided", "humanizer": "Humanizer"}
INK, MUTED, GRID = "#1f2937", "#6b7280", "#e5e7eb"


def measure(runs):
    """{puzzle: {strategy: (median_ms, nodes)}}; every result must be a valid solution."""
    data = {}
    for puzzle in PUZZLES:
        data[puzzle.name] = {}
        for strategy in AVAILABLE_STRATEGIES:
            results = [run_one(strategy, puzzle) for _ in range(runs)]
            assert all(r.valid for r in results), f"{strategy} failed on {puzzle.name}"
            data[puzzle.name][strategy] = (statistics.median(r.elapsed_ms for r in results),
                                           results[-1].nodes_expanded)
    return data


def fmt_ms(ms):
    return f"{ms:.1f}" if ms < 10 else f"{ms:,.0f}"


def draw_chart(data, runs, out):
    W, H = 1800, 1180
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    f = {k: load_font(s, bold=b) for k, (s, b) in {
        "title": (38, True), "h": (24, True), "t": (21, False), "tb": (21, True), "s": (18, False)}.items()}

    d.text((W // 2, 34), "Solver comparison: solve time per puzzle", font=f["title"], fill=INK, anchor="mm")
    d.text((W // 2, 76), f"Median of {runs} runs per solver and puzzle. Logarithmic time axis.",
           font=f["t"], fill=MUTED, anchor="mm")

    # legend
    lx = W // 2 - 330
    for name in AVAILABLE_STRATEGIES:
        d.rectangle((lx, 108, lx + 22, 130), fill=COLORS[name])
        d.text((lx + 32, 119), LABELS[name], font=f["t"], fill=INK, anchor="lm")
        lx += 230

    # plot area: log10(ms) from 10^-1 to 10^4
    x0, x1, y0, y1 = 150, W - 50, 170, 640
    lo, hi = -1, 4

    def y_of(ms):
        return y1 - (math.log10(max(ms, 10 ** lo)) - lo) / (hi - lo) * (y1 - y0)

    for exp in range(lo, hi + 1):
        y = y_of(10 ** exp)
        d.line((x0, y, x1, y), fill=GRID, width=2)
        label = f"{10 ** exp:g} ms" if exp < 3 else f"{10 ** exp / 1000:g} s"
        d.text((x0 - 12, y), label, font=f["s"], fill=MUTED, anchor="rm")
    d.line((x0, y0, x0, y1), fill=MUTED, width=2)
    d.line((x0, y1, x1, y1), fill=MUTED, width=2)

    names = list(data)
    group_w = (x1 - x0) / len(names)
    bar_w, gap = 56, 8
    for gi, pname in enumerate(names):
        gx = x0 + gi * group_w + group_w / 2 - (3 * bar_w + 2 * gap) / 2
        for si, strategy in enumerate(AVAILABLE_STRATEGIES):
            ms, _ = data[pname][strategy]
            bx = gx + si * (bar_w + gap)
            top = y_of(ms)
            d.rectangle((bx, top, bx + bar_w, y1), fill=COLORS[strategy])
            d.text((bx + bar_w / 2, top - 6), fmt_ms(ms), font=f["s"], fill=INK, anchor="ms")
        d.text((x0 + gi * group_w + group_w / 2, y1 + 22), pname, font=f["t"], fill=INK, anchor="mm")

    # table: time (ms) and search effort per solver
    ty = 700
    d.text((x0, ty), "Time and search effort", font=f["h"], fill=INK, anchor="lm")
    ty += 24
    cols = [x0, x0 + 300, x0 + 700, x0 + 1100]
    heads = ["Puzzle"] + [f"{LABELS[s]}: ms / steps" for s in AVAILABLE_STRATEGIES]
    d.rectangle((x0 - 10, ty, x1, ty + 40), fill="#f1f5f9")
    for cx, h in zip(cols, heads):
        d.text((cx, ty + 20), h, font=f["tb"], fill=INK, anchor="lm")
    ty += 40
    for pname in names:
        d.line((x0 - 10, ty + 38, x1, ty + 38), fill=GRID, width=1)
        d.text((cols[0], ty + 19), pname, font=f["t"], fill=INK, anchor="lm")
        for cx, strategy in zip(cols[1:], AVAILABLE_STRATEGIES):
            ms, nodes = data[pname][strategy]
            d.text((cx, ty + 19), f"{fmt_ms(ms)} ms / {nodes:,}", font=f["t"], fill=COLORS[strategy], anchor="lm")
        ty += 38

    # takeaways, computed from the numbers above
    wins = {s: sum(1 for p in names if min(data[p], key=lambda k: data[p][k][0]) == s)
            for s in AVAILABLE_STRATEGIES}
    best = max(wins, key=wins.get)
    hardest = "inkala_hardest" if "inkala_hardest" in data else names[-1]
    bt, rl, hu = (data[hardest][s] for s in ("backtracking", "rl", "humanizer"))
    notes = [
        f"Fastest by time: {LABELS[best]} on {wins[best]} of {len(names)} puzzles.",
        f"On {hardest}: Backtracking {bt[1]:,} steps, RL {rl[1]:,}, Humanizer {hu[1]:,} guesses "
        f"(a step is one search decision; for the Humanizer only guesses count, logic never branches).",
    ]
    if rl[1] < bt[1] and rl[0] > bt[0]:
        notes.append(f"On {hardest} RL needs fewer steps than Backtracking but costs more per step, "
                     "so it is slower in time.")
    ty += 16
    for line in notes:
        d.text((x0, ty), "- " + line, font=f["s"], fill=INK, anchor="lm")
        ty += 28

    d.text((W // 2, H - 22), f"Measured on {platform.system()} with Python {platform.python_version()} "
           f"by scripts/make_benchmark_chart.py. Timings vary by machine.", font=f["s"], fill=MUTED, anchor="mm")

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    img.save(out)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Draw the solver time comparison from real measurements.")
    parser.add_argument("--runs", type=int, default=5, help="runs per solver and puzzle (median is used)")
    parser.add_argument("--out", default=os.path.join(ROOT, "docs", "benchmark_times.png"))
    args = parser.parse_args(argv)
    draw_chart(measure(args.runs), args.runs, args.out)
    print("wrote", args.out)


if __name__ == "__main__":
    main()
