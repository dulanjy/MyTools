"""Screen capture & mouse monitor package.

Modules:
    constants - Shared constants and DPI awareness
    capture   - CapturePreviewDuoEnhanced (region capture, processing, OCR)
    monitor   - MousePositionMonitor (main UI window)
    window_capture - Thin backward-compatible entry point (main)

Public entry points:
    from screen_capture import MousePositionMonitor, CapturePreviewDuoEnhanced
"""
from .monitor import MousePositionMonitor  # noqa: F401
from .capture import CapturePreviewDuoEnhanced  # noqa: F401

__all__ = ["MousePositionMonitor", "CapturePreviewDuoEnhanced"]
__version__ = "0.1.0"
