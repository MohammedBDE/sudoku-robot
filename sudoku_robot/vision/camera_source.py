"""
Grabs a single still frame from an iPhone acting as an RTSP camera
source on the local WiFi network.

Assumed setup (confirm/correct this -- see the project README's vision
section): a generic RTSP-camera-server app on the iPhone (the kind
that turns the phone into an IP camera for the LAN and shows the
resulting rtsp:// URL directly on its own screen, e.g. something like
`rtsp://192.168.1.42:8554/live`). The exact port and path differ by
app, which is exactly why the URL is never hardcoded here -- see
`camera_config.py`. Two things matter regardless of which app it is:

    - the iPhone must be on the same WiFi network as this Pi (not
      cellular data, not a different WiFi band/VLAN), and
    - the app must be in the foreground and actively broadcasting --
      most of these apps stop streaming as soon as they're backgrounded
      or the phone locks.

This module intentionally only captures ONE frame per call (that's
all a "photograph the finished puzzle" pipeline needs) rather than
holding the stream open, which keeps it simple and means a stale/dead
connection can't silently linger between capture attempts.
"""
import threading
import time
from typing import Callable, Optional, TypeVar

import cv2
import numpy as np

T = TypeVar("T")

#: How long to wait for the RTSP handshake / TCP connection itself.
DEFAULT_OPEN_TIMEOUT_S = 5.0
#: How long to wait for each individual frame read.
DEFAULT_READ_TIMEOUT_S = 5.0
#: A fresh RTSP connection's first few frames are sometimes stale or
#: fail outright while the decoder syncs up; retrying a handful of
#: reads before giving up is standard practice for RTSP capture.
DEFAULT_READ_RETRIES = 5


class CameraCaptureError(Exception):
    """
    Raised when a frame could not be captured. The message is written
    to be read directly by a human debugging a flaky WiFi/phone setup,
    not just logged -- see the checklist it prints.
    """


def _run_with_timeout(fn: Callable[[], T], timeout_s: float) -> T:
    """
    Run a blocking call with a hard wall-clock timeout.

    This exists because cv2's own timeout knobs --
    CAP_PROP_OPEN_TIMEOUT_MSEC/CAP_PROP_READ_TIMEOUT_MSEC and the
    OPENCV_FFMPEG_CAPTURE_OPTIONS env var trick -- turned out NOT to
    be honoured reliably by this OpenCV build's bundled FFmpeg backend
    when tested against an unreachable address: the process blocked
    for FFmpeg's own internal ~30s default regardless of what we set.
    Running the call in a daemon thread and giving up on OUR OWN
    schedule is the only way to bound it from the outside.

    Trade-off: if `fn` really does hang, its thread is simply
    abandoned (daemon=True means it won't block process exit) rather
    than forcibly killed -- Python has no safe way to kill a thread
    stuck inside a C extension call. That's fine here since each
    capture_frame() call is short-lived and this is a best-effort
    bound, not a resource guarantee.
    """
    result: dict = {}

    def _target():
        try:
            result["value"] = fn()
        except Exception as exc:  # re-raised on the caller's thread below
            result["error"] = exc

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    thread.join(timeout_s)

    if thread.is_alive():
        raise TimeoutError(f"operation did not complete within {timeout_s:.0f}s")
    if "error" in result:
        raise result["error"]
    return result["value"]


def _open_timeout_checklist(rtsp_url: str) -> str:
    return (
        f"Could not connect to the RTSP stream at:\n    {rtsp_url}\n\n"
        "Things to check:\n"
        "  1. Is the RTSP camera app open and actively broadcasting on "
        "the iPhone right now? (most of these apps stop as soon as the "
        "phone locks or the app goes to the background)\n"
        "  2. Is the iPhone connected to the SAME WiFi network as this "
        "Pi -- not cellular data, and not a guest/different WiFi band?\n"
        "  3. Does the IP address in the URL still match the iPhone's "
        "current IP? (Settings > WiFi > (i) next to the network -- "
        "phones commonly get a new DHCP address after reconnecting)\n"
        "  4. Does the port/path match what the app itself displays? "
        "(different apps use different defaults, e.g. :8554/live vs "
        ":554/ vs :8080/h264.sdp)\n"
        "  5. Are the Pi and iPhone able to reach each other at all, "
        "e.g. does `ping <phone-ip>` from this Pi succeed?"
    )


def capture_frame(
    rtsp_url: str,
    open_timeout_s: float = DEFAULT_OPEN_TIMEOUT_S,
    read_timeout_s: float = DEFAULT_READ_TIMEOUT_S,
    read_retries: int = DEFAULT_READ_RETRIES,
) -> np.ndarray:
    """
    Connect to `rtsp_url`, grab one frame, and disconnect.

    Returns the frame as a BGR numpy array (OpenCV's usual format).
    Raises CameraCaptureError, with a checklist of things to check on
    the phone/network side, if the connection or every read attempt
    fails or times out.
    """
    try:
        cap = _run_with_timeout(lambda: cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG), open_timeout_s)
    except TimeoutError:
        raise CameraCaptureError(
            f"Connection attempt did not respond within {open_timeout_s:.0f}s.\n\n"
            + _open_timeout_checklist(rtsp_url)
        )

    try:
        if not cap.isOpened():
            raise CameraCaptureError(_open_timeout_checklist(rtsp_url))

        last_error: Optional[str] = None
        for attempt in range(1, read_retries + 1):
            try:
                ok, frame = _run_with_timeout(cap.read, read_timeout_s)
            except TimeoutError:
                last_error = f"read attempt {attempt}/{read_retries} timed out after {read_timeout_s:.0f}s"
                continue
            if ok and frame is not None:
                return frame
            last_error = f"read attempt {attempt}/{read_retries} returned no frame"
            time.sleep(0.2)

        raise CameraCaptureError(
            f"Connected to the stream but never got a usable frame ({last_error}).\n\n"
            + _open_timeout_checklist(rtsp_url)
        )
    finally:
        cap.release()


def save_frame_jpg(frame: np.ndarray, path: str, quality: int = 95) -> None:
    """Save a captured frame (as returned by capture_frame) to a .jpg file."""
    ok = cv2.imwrite(path, frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise IOError(f"cv2.imwrite failed to write {path}")
