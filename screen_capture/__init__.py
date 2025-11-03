"""Screen capture & mouse monitor package.

Modules:
    constants - Shared constants and DPI awareness
    capture   - CapturePreviewDuoEnhanced (region capture, processing, OCR)
    monitor   - MousePositionMonitor (main UI window)
    window_capture - Thin backward-compatible entry point (main)

Design note:
- Avoid importing heavy GUI/screen modules at package import time to prevent
optional dependencies (e.g., pyautogui, mss, tkinter) from blocking unrelated
consumers like `screen_capture.ai_client`.
- Expose public classes via lazy attribute resolution.

Usage:
    from screen_capture import MousePositionMonitor, CapturePreviewDuoEnhanced
"""

__version__ = "0.1.0"

# Lazy attribute loading to avoid importing heavy deps on package import
def __getattr__(name):  # PEP 562
    if name == "MousePositionMonitor":
        from .monitor import MousePositionMonitor  # type: ignore
        return MousePositionMonitor
    if name == "CapturePreviewDuoEnhanced":
        from .capture import CapturePreviewDuoEnhanced  # type: ignore
        return CapturePreviewDuoEnhanced
    raise AttributeError(f"module 'screen_capture' has no attribute {name!r}")

__all__ = ["MousePositionMonitor", "CapturePreviewDuoEnhanced"]
