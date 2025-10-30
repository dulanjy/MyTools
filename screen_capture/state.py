"""应用内部的简单状态容器定义。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class OCRPanelState:
    """保存 OCR 面板相关的可观察状态。"""

    conf_threshold: float = 0.0
    preview_visible: bool = True
    panel_visible: bool = False
    pending_preview_visible: Optional[bool] = None
    last_result: Optional[Dict[str, Any]] = None
    all_lines: List[Dict[str, Any]] = field(default_factory=list)


__all__ = ["OCRPanelState"]
