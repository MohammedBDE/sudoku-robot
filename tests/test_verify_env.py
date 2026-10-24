import os
import sys

import importlib.util

from sudoku_robot import config

# verify_env.py is a standalone script in scripts/, not a package module.
_spec = importlib.util.spec_from_file_location("verify_env", os.path.join(config.SCRIPTS_DIR, "verify_env.py"))
verify_env = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(verify_env)


def test_every_requirement_is_pinned_exactly():
    """requirements.txt must pin exact versions (==), never ranges, so installs are identical."""
    with open(verify_env.REQUIREMENTS) as fh:
        specs = [line.split("#", 1)[0].split(";", 1)[0].strip() for line in fh]
    specs = [s for s in specs if s]
    assert specs, "requirements.txt is empty"
    for spec in specs:
        assert "==" in spec and not any(op in spec for op in (">", "<", "~", "!")), spec


def test_read_pins_parses_names_and_platform_markers():
    pins = verify_env.read_pins()
    for name in ("numpy", "pillow", "opencv-python-headless", "pymycobot", "pytest"):
        assert name in pins
    assert ("colorama" in pins) == (sys.platform == "win32")


def test_verifier_runs_and_reports(capsys):
    code = verify_env.main([])
    out = capsys.readouterr().out
    assert code in (0, 1)
    assert "numpy==" in out and "arm_calibration.json" in out and "corners.json" in out
    assert ("READY" in out) or ("NOT READY" in out)


def test_verifier_finds_the_project_root_from_scripts_dir():
    assert verify_env.ROOT == config.PROJECT_ROOT
    assert verify_env.REQUIREMENTS == os.path.join(config.PROJECT_ROOT, "requirements.txt")


def test_setup_scripts_exist_and_call_the_verifier():
    for script in ("setup.sh", "setup.ps1"):
        with open(os.path.join(config.SCRIPTS_DIR, script)) as fh:
            body = fh.read()
        assert "requirements.txt" in body and "verify_env.py" in body
        assert "scripts" in body  # it calls scripts/verify_env.py from the project root
