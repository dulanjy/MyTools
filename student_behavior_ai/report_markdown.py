from __future__ import annotations
from typing import Any, Dict, List


def _val(x: Any, default: str = "-") -> str:
    if x is None:
        return default
    return str(x)


def _pct(x: Any) -> str:
    try:
        v = int(x)
        if v < 0:
            v = 0
        if v > 100:
            v = 100
        return f"{v}%"
    except Exception:
        return "-"


def markdown_from_ai_json(data: Dict[str, Any], title: str = "课堂行为分析") -> str:
    """将 AI 严格 JSON（schema v1.1）渲染为简版 Markdown：仅展示 observations 与 limitations。

    注意：根据产品需求，前端只关注两个板块，避免分心信息；其余内容（metrics/risks/suggestions/spatial 等）不在此处渲染。
    """
    observations = data.get("observations") or []
    if not isinstance(observations, list):
        observations = []
    limitations = data.get("limitations") or []
    if not isinstance(limitations, list):
        limitations = []

    parts: List[str] = []
    parts.append(f"# {title}")
    parts.append("")

    # 关键观察要点（仅渲染）
    parts.append("## 关键观察要点")
    if observations:
        for it in observations[:8]:
            parts.append(f"- {str(it)}")
    else:
        parts.append("- (未提供)")
    parts.append("")

    # 局限性（仅渲染）
    parts.append("## 局限性")
    if limitations:
        for it in limitations[:8]:
            parts.append(f"- {str(it)}")
    else:
        parts.append("- (未提供)")
    parts.append("")

    return "\n".join(parts)
