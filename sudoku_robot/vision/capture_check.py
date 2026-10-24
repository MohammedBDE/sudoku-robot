"""
Quick connectivity/quality check for the iPhone RTSP camera -- run
this BEFORE trying any grid-detection pipeline on it, so a bad IP,
closed app, or wrong WiFi network shows up as a clear message here
rather than a confusing failure two layers deeper.

Run with:

    python -m sudoku_robot.vision.capture_check
    python -m sudoku_robot.vision.capture_check --rtsp-url rtsp://192.168.1.42:8554/live
    python -m sudoku_robot.vision.capture_check --out my_test.jpg

The frame is saved to calib/camera_test_frame.jpg by default, next to
the other generated calibration/debug images.
"""
import argparse
import os
import sys

from .. import config
from .camera_config import CameraConfigError, resolve_rtsp_url
from .camera_source import CameraCaptureError, capture_frame, save_frame_jpg

DEFAULT_OUT = os.path.join(config.CALIB_DIR, "camera_test_frame.jpg")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Grab one frame from the iPhone RTSP camera and save it as a JPG."
    )
    parser.add_argument(
        "--rtsp-url", default=None,
        help="Override the configured RTSP URL for this run only "
             "(otherwise uses SUDOKU_ROBOT_RTSP_URL or config/camera_config.json).",
    )
    parser.add_argument(
        "--out", default=DEFAULT_OUT,
        help=f"Where to save the captured frame (default: {DEFAULT_OUT}).",
    )
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    try:
        rtsp_url = resolve_rtsp_url(args.rtsp_url)
    except CameraConfigError as e:
        print(f"Configuration error:\n{e}", file=sys.stderr)
        return 1

    print(f"Connecting to {rtsp_url} ...", flush=True)
    try:
        frame = capture_frame(rtsp_url)
    except CameraCaptureError as e:
        print(f"Capture failed:\n{e}", file=sys.stderr)
        return 1

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    save_frame_jpg(frame, args.out)
    height, width = frame.shape[:2]
    print(f"Success: captured a {width}x{height} frame and saved it to {args.out}")
    print("Check that file: is the whole grid visible, in focus, and evenly lit, "
          "with the phone held roughly parallel to the paper?")
    return 0


if __name__ == "__main__":
    sys.exit(main())
