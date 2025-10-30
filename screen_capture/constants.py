"""Shared constants and basic environment setup for screen capture tools."""
import ctypes

# -------------------- 常量定义 --------------------
GRID = 10  # 未广泛使用，保留占位
MOVE_TH = 5
FPS_MOVE = 20
FPS_STILL = 2
MAX_HISTORY = 10
PRESET_SIZES = [
    ("HD (1280×720)", (1280, 720)),
    ("Full HD (1920×1080)", (1920, 1080)),
    ("4K (3840×2160)", (3840, 2160)),
    ("Square (800×800)", (800, 800))
]

MIN_CAPTURE_WIDTH = 100
MIN_CAPTURE_HEIGHT = 100
GRID_LINE_STEP = 50
RULER_STEP = 100
DEFAULT_RECORD_INTERVAL = 1.0

# DPI awareness (Windows only)
try:
    if hasattr(ctypes, "windll") and hasattr(ctypes.windll, "user32") and hasattr(ctypes.windll.user32, 'SetProcessDPIAware'):
        ctypes.windll.user32.SetProcessDPIAware()
except Exception:
    # Ignore DPI setting failures
    pass
