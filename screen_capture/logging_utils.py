"""Lightweight logging helper for screen_capture package.

Provides a module-level logger configured once. Users can further configure
logging in their application if needed. Default level=INFO.
"""
from __future__ import annotations
import logging, os

_LOG_NAME = "screen_capture"
_logger = logging.getLogger(_LOG_NAME)

if not _logger.handlers:
    # Basic configuration only once; allow override by user
    level = os.environ.get("SC_LOG_LEVEL", "INFO").upper()
    handler = logging.StreamHandler()
    fmt = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    handler.setFormatter(logging.Formatter(fmt))
    _logger.addHandler(handler)
    try:
        _logger.setLevel(level)
    except Exception:
        _logger.setLevel(logging.INFO)
    # 避免重复日志：阻止向 root logger 传播（否则会出现第二种格式的重复输出）
    _logger.propagate = False

get_logger = lambda: _logger  # simple accessor

__all__ = ["get_logger"]
