"""Guards the top-level folder layout documented in README "Project structure"."""
import os
import subprocess
import sys

from sudoku_robot import config

ROOT = config.PROJECT_ROOT

#: Every file allowed directly in the project root.
ROOT_FILES = {"README.md", "LICENSE", "requirements.txt", "pytest.ini", ".gitignore", ".gitattributes"}


def test_root_holds_only_the_expected_files():
    stray = sorted(f for f in os.listdir(ROOT) if os.path.isfile(os.path.join(ROOT, f)) and f not in ROOT_FILES)
    assert stray == [], f"files belong in config/, calib/ or scripts/, not the root: {stray}"


def test_each_folder_holds_what_it_should():
    assert set(os.listdir(config.CONFIG_DIR)) >= {"corners.json", "arm_calibration.json", "camera_config.example.json"}
    assert set(os.listdir(config.SCRIPTS_DIR)) >= {"jog_console.py", "teach_cli.py", "verify_env.py",
                                                   "setup.sh", "setup.ps1"}
    assert os.path.isdir(config.CALIB_DIR)
    for name in ("sudoku_robot", "tests", "teach_data", "printable_puzzles"):
        assert os.path.isdir(os.path.join(ROOT, name))


def test_scripts_run_from_any_working_directory(tmp_path):
    """Scripts in scripts/ must find the sudoku_robot package without being run from the root."""
    for script in ("teach_cli.py", "verify_env.py"):
        proc = subprocess.run([sys.executable, os.path.join(config.SCRIPTS_DIR, script), "--help"],
                              cwd=tmp_path, capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
    code = f"import runpy; ns = runpy.run_path(r'{os.path.join(config.SCRIPTS_DIR, 'jog_console.py')}'); " \
           "assert ns['DIRS']['f'] == (0, -1, 0)"
    proc = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_camera_debug_tools_default_to_calib_dir():
    # Both modules import cv2, which may not be installed -- check their source instead.
    for name in ("capture_check.py", "detect_check.py"):
        with open(os.path.join(ROOT, "sudoku_robot", "vision", name)) as fh:
            assert "os.path.join(config.CALIB_DIR" in fh.read(), name
