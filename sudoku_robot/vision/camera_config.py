"""
Resolves the RTSP URL for the iPhone camera, so it never has to be
hardcoded -- the phone's IP address on the WiFi network can (and will)
change.

Checked in this order, first match wins:

    1. an explicit argument (e.g. --rtsp-url on the CLI)
    2. the SUDOKU_ROBOT_RTSP_URL environment variable
    3. config/camera_config.json: {"rtsp_url": "rtsp://..."}
       (copy config/camera_config.example.json to start)

That's the same "explicit > env > config file" precedence a lot of
tools use (e.g. how a CLI flag overrides an env var, which overrides a
config default), which keeps day-to-day use simple (edit one JSON
file once) while still letting a one-off run point somewhere else
without touching that file.
"""
import json
import os
from typing import Optional

from .. import config

ENV_VAR = "SUDOKU_ROBOT_RTSP_URL"

DEFAULT_CONFIG_PATH = config.CAMERA_CONFIG_PATH


class CameraConfigError(Exception):
    """Raised when no RTSP URL could be found anywhere."""


def _read_config_file(path: str) -> Optional[str]:
    if not os.path.exists(path):
        return None
    with open(path) as f:
        data = json.load(f)
    return data.get("rtsp_url")


def resolve_rtsp_url(explicit_url: Optional[str] = None, config_path: str = DEFAULT_CONFIG_PATH) -> str:
    """Find the RTSP URL to use, or raise CameraConfigError with next steps."""
    if explicit_url:
        return explicit_url

    env_url = os.environ.get(ENV_VAR)
    if env_url:
        return env_url

    config_url = _read_config_file(config_path)
    if config_url:
        return config_url

    raise CameraConfigError(
        "No RTSP URL configured. Set one of, in order of precedence:\n"
        "  1. pass it explicitly (e.g. --rtsp-url rtsp://<phone-ip>:PORT/PATH)\n"
        f"  2. export {ENV_VAR}=rtsp://<phone-ip>:PORT/PATH\n"
        f"  3. create {config_path} (start from camera_config.example.json in the same folder) containing: "
        '{"rtsp_url": "rtsp://<phone-ip>:PORT/PATH"}\n'
        "The exact port/path depends on your RTSP camera app -- it "
        "should display the full rtsp:// URL on its own screen."
        + config.legacy_location_hint(config_path)
    )
