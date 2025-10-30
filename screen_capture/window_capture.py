"""Entry point for the refactored screen capture & monitor tool.

The original large ``window_capture.py`` has been split into:
  - constants.py  (shared constants & DPI awareness)
  - capture.py    (CapturePreviewDuoEnhanced class)
  - monitor.py    (MousePositionMonitor class / main UI)

This file is intentionally minimal and kept only for backward compatibility.
"""

from __future__ import annotations

try:  # 优先包内相对导入
  from .monitor import MousePositionMonitor  # type: ignore
except Exception:  # 允许直接脚本运行：python screen_capture/window_capture.py
  import os, sys
  here = os.path.abspath(os.path.dirname(__file__))
  parent = os.path.dirname(here)
  if parent not in sys.path:
    sys.path.insert(0, parent)
  from screen_capture.monitor import MousePositionMonitor  # type: ignore


def main() -> None:  # pragma: no cover - thin wrapper
    """Launch the mouse position & capture monitor UI."""
    MousePositionMonitor().run()


if __name__ == "__main__":  # pragma: no cover
    main()