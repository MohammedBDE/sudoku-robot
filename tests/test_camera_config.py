import json

import pytest

from sudoku_robot.vision.camera_config import CameraConfigError, ENV_VAR, resolve_rtsp_url


def test_explicit_url_wins_over_everything(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_VAR, "rtsp://from-env/live")
    config_path = tmp_path / "camera_config.json"
    config_path.write_text(json.dumps({"rtsp_url": "rtsp://from-file/live"}))

    url = resolve_rtsp_url("rtsp://from-arg/live", config_path=str(config_path))
    assert url == "rtsp://from-arg/live"


def test_env_var_used_when_no_explicit_url(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_VAR, "rtsp://from-env/live")
    config_path = tmp_path / "camera_config.json"
    config_path.write_text(json.dumps({"rtsp_url": "rtsp://from-file/live"}))

    url = resolve_rtsp_url(None, config_path=str(config_path))
    assert url == "rtsp://from-env/live"


def test_config_file_used_when_no_explicit_or_env(tmp_path, monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    config_path = tmp_path / "camera_config.json"
    config_path.write_text(json.dumps({"rtsp_url": "rtsp://from-file/live"}))

    url = resolve_rtsp_url(None, config_path=str(config_path))
    assert url == "rtsp://from-file/live"


def test_raises_helpful_error_when_nothing_configured(tmp_path, monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    missing_config_path = tmp_path / "does_not_exist.json"

    with pytest.raises(CameraConfigError) as exc_info:
        resolve_rtsp_url(None, config_path=str(missing_config_path))

    message = str(exc_info.value)
    assert ENV_VAR in message
    assert str(missing_config_path) in message
