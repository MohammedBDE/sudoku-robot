# config/

Settings that describe **this particular robot setup**: this arm, this pen, this table
and where the paper lies. Nothing here is about the algorithms. Re-do them (see the main
README, "Robot-specific files") if you move the robot or the paper.

| File | What it holds | Who writes it | Who reads it |
|---|---|---|---|
| `arm_calibration.json` | `pen_down_z` (height in mm at which the pen touches the paper), `pen_up_z` (travel height) and `orientation` (the pen's tilt `rx, ry, rz` in degrees). | Measured by hand (`scripts/jog_console.py`) or `scripts/teach_cli.py capture-surface`. | Every real-arm move: the CLI, `scripts/place_paper.py`. |
| `corners.json` | Three arm poses: `TL`, `TR`, `BL` = the centres of the top-left, top-right and bottom-left cells, as `[x, y, z, rx, ry, rz]` in mm (only x and y are used). The `_note` key says how the file was made. | `scripts/place_paper.py` (plans a square grid that is fully in reach) or `scripts/jog_console.py` (teach by hand). | `writer/grid_layout.py` builds all 81 cell centres from these 3 points; `writer/corner_check.py` validates them before any real write. |
| `camera_config.json` | `rtsp_url`: the address of the iPhone's video stream. Private to your network, so it is **gitignored**. | You (copy the example and edit). | `vision/camera_config.py` (only for `--from-camera`). |
| `camera_config.example.json` | The same file with a placeholder address. | - | Template for the one above. |

Coordinates are the arm's own frame in mm, seen from behind the base: **-Y is forward**
(towards the top of the paper), **+X is left**, **+Z is up**. Row 0 of the grid is the one
farthest from the base. The arm reaches at most 280 mm.

To show that the current setup is valid:

```bash
python -m sudoku_robot --check-corners
```

It prints the two edge lengths (should be 160 mm = 8 cells of 20 mm), the corner angle
(90 degrees) and how many of the 81 cells are inside the arm's reach, and exits non-zero
if any check fails. A real-arm write is refused while it fails.
