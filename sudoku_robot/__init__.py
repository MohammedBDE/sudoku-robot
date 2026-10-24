"""
sudoku_robot: read a printed Sudoku with a camera, solve it, and write
the answer onto the paper with a pen held by a mycobot 280 Pi arm.

Subpackages / modules:
    solver     - pluggable solving strategies (backtracking, RL-guided backtracking, humanizer)
    puzzles    - sample puzzle bank, generator, printable PNG renderer
    benchmark  - strategy comparison harness
    vision     - iPhone RTSP capture, grid detection, digit recognition
    writer     - arm control (simulated + real mycobot 280), grid layouts,
                 digit strokes, corner validation, optional hand-teaching tool
    config     - file locations, serial settings, reach limits, pen calibration,
                 and the arm coordinate convention
    fonts      - font lookup shared by the renderer and the digit recognizer
"""
__version__ = "0.2.0"

