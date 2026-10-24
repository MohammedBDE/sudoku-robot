"""
Font lookup shared by puzzles/render.py (printing puzzles) and
vision/digit_recognizer.py (reading them back).

The two MUST agree: the recognizer matches camera cells against digits
rendered in the same font the puzzle was printed in. DejaVu Sans Bold
is the reference font. It's found, in order, at:

    1. the SUDOKU_ROBOT_FONT / SUDOKU_ROBOT_FONT_REGULAR env var (explicit override)
    2. sudoku_robot/assets/fonts/ (bundled copy -- drop DejaVuSans-Bold.ttf /
       DejaVuSans.ttf there to make any machine match the Pi exactly)
    3. the usual system locations on Linux (the Pi), macOS, and Windows

If DejaVu isn't found anywhere, a platform fallback (Arial on Windows)
and finally Pillow's own built-in font are used, so nothing crashes on
a machine without it -- but `is_reference_font()` is then False, and
callers warn that printed and recognized digits may not match.
"""
import os
from typing import List, Optional

from PIL import ImageFont

FONT_ENV = "SUDOKU_ROBOT_FONT"
FONT_REGULAR_ENV = "SUDOKU_ROBOT_FONT_REGULAR"

BUNDLED_FONT_DIR = os.path.join(os.path.dirname(__file__), "assets", "fonts")

_BOLD_NAME = "DejaVuSans-Bold.ttf"
_REGULAR_NAME = "DejaVuSans.ttf"


def _system_font_dirs() -> List[str]:
    dirs = [
        "/usr/share/fonts/truetype/dejavu",
        "/usr/share/fonts/TTF",
        "/usr/share/fonts/dejavu",
        "/Library/Fonts",
        os.path.expanduser("~/Library/Fonts"),
    ]
    windir = os.environ.get("WINDIR")
    if windir:
        dirs.append(os.path.join(windir, "Fonts"))
    local = os.environ.get("LOCALAPPDATA")
    if local:
        dirs.append(os.path.join(local, "Microsoft", "Windows", "Fonts"))
    return dirs


def _fallback_candidates(bold: bool) -> List[str]:
    paths = []
    windir = os.environ.get("WINDIR")
    if windir:
        paths.append(os.path.join(windir, "Fonts", "arialbd.ttf" if bold else "arial.ttf"))
    paths.append("/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold
                 else "/System/Library/Fonts/Supplemental/Arial.ttf")
    return paths


def find_reference_font(bold: bool = True) -> Optional[str]:
    """Path to DejaVu Sans (Bold), or None if it isn't available anywhere."""
    override = os.environ.get(FONT_ENV if bold else FONT_REGULAR_ENV)
    if override and os.path.exists(override):
        return override
    name = _BOLD_NAME if bold else _REGULAR_NAME
    for directory in [BUNDLED_FONT_DIR] + _system_font_dirs():
        path = os.path.join(directory, name)
        if os.path.exists(path):
            return path
    return None


def find_font(bold: bool = True) -> Optional[str]:
    """Best available TrueType font path: DejaVu first, then a platform fallback. None = Pillow built-in."""
    path = find_reference_font(bold)
    if path:
        return path
    for candidate in _fallback_candidates(bold):
        if os.path.exists(candidate):
            return candidate
    return None


def is_reference_font(bold: bool = True) -> bool:
    return find_reference_font(bold) is not None


def describe_font(bold: bool = True) -> str:
    path = find_font(bold)
    return os.path.basename(path) if path else "Pillow built-in font"


def load_font(size_px: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    path = find_font(bold)
    if path:
        return ImageFont.truetype(path, size_px)
    return ImageFont.load_default(size=size_px)
