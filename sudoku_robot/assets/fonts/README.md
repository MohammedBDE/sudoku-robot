# Bundled fonts (optional)

Drop `DejaVuSans-Bold.ttf` and `DejaVuSans.ttf` here to make any machine
render puzzles and read digits with exactly the same font as the robot's Pi.
`sudoku_robot/fonts.py` checks this folder first (after the
`SUDOKU_ROBOT_FONT` env var), before the system font folders.

On the Pi they're already installed at `/usr/share/fonts/truetype/dejavu/` 
(`sudo apt install fonts-dejavu-core`); copy them from there.
DejaVu fonts are free to redistribute (Bitstream Vera license).
