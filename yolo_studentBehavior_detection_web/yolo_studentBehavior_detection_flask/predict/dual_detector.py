"""
Dual-model detector: run behavior model and head-count model on the same image
and return a unified JSON-friendly dictionary.

Keeps it simple and reusable by Flask endpoints.
"""
from __future__ import annotations
from typing import Dict, Any, List, Tuple, Optional
from pathlib import Path

try:
    from ultralytics import YOLO  # type: ignore
except Exception:  # pragma: no cover
    YOLO = None  # type: ignore


# Simple in-memory cache to avoid reloading models on every request
_MODEL_CACHE: Dict[str, Any] = {}


def _get_model(weights_path: str):
    if YOLO is None:
        raise RuntimeError("Ultralytics 未安装，请先安装 `pip install ultralytics` 并准备匹配的 torch 环境")
    wp = str(Path(weights_path))
    if wp not in _MODEL_CACHE:
        _MODEL_CACHE[wp] = YOLO(wp)
    return _MODEL_CACHE[wp]


def run_dual_on_image(
    img_path: str,
    behavior_pt: str,
    counts_pt: str,
    conf: float = 0.25,
    imgsz: int = 640,
) -> Dict[str, Any]:
    """Run two YOLO models on one image and return a merged result.

    Returns dict with keys:
    - image: str absolute path
    - size: {width, height}
    - detections: [ {label, bbox_xyxy, confidence} ] (from behavior model)
    - boxes: { label: [ {bbox_xyxy, confidence} ] }
    - counts: { label: int } (aggregated from behavior detections)
    - head: int (number of boxes from counts model)
    - backend: "ultralytics"
    - models: { behavior: path, counts: path }
    """
    p = Path(img_path)
    if not p.exists():
        raise FileNotFoundError(f"图片不存在: {img_path}")

    m_behavior = _get_model(behavior_pt)
    m_counts = _get_model(counts_pt)

    b_res = m_behavior.predict(str(p), conf=conf, imgsz=imgsz, show=False, verbose=False)
    c_res = m_counts.predict(str(p), conf=conf, imgsz=imgsz, show=False, verbose=False)

    b_r = b_res[0]
    c_r = c_res[0]

    # size
    try:
        h, w = int(b_r.orig_shape[0]), int(b_r.orig_shape[1])
    except Exception:
        from PIL import Image
        w, h = Image.open(str(p)).size

    names = {}
    try:
        names = m_behavior.model.names  # type: ignore[attr-defined]
    except Exception:
        names = {}

    detections: List[Dict[str, Any]] = []
    boxes_map: Dict[str, List[Dict[str, Any]]] = {}
    counts_map: Dict[str, int] = {}

    try:
        boxes = getattr(b_r, 'boxes', None)
        if boxes is not None and len(boxes) > 0:
            xyxy = boxes.xyxy.tolist() if hasattr(boxes, 'xyxy') else []
            confs = boxes.conf.tolist() if hasattr(boxes, 'conf') else []
            cls_ids = boxes.cls.tolist() if hasattr(boxes, 'cls') else []
            for i, bb in enumerate(xyxy):
                cls_id = int(cls_ids[i]) if i < len(cls_ids) else -1
                raw_label = names.get(cls_id, str(cls_id)) if isinstance(names, dict) else str(cls_id)
                label = raw_label.strip()
                confv = float(confs[i]) if i < len(confs) else None
                det = {
                    'label': label,
                    'bbox_xyxy': [float(bb[0]), float(bb[1]), float(bb[2]), float(bb[3])],
                    'confidence': confv,
                }
                detections.append(det)
                boxes_map.setdefault(label, []).append({'bbox_xyxy': det['bbox_xyxy'], 'confidence': confv})
                counts_map[label] = counts_map.get(label, 0) + 1
    except Exception:
        pass

    # counts model => head count
    head_count = 0
    try:
        c_boxes = getattr(c_r, 'boxes', None)
        if c_boxes is not None and len(c_boxes) > 0:
            head_count = len(c_boxes.xyxy.tolist()) if hasattr(c_boxes, 'xyxy') else 0
    except Exception:
        head_count = 0

    # 统一规范：
    # - 顶层仅保留一个 head（来自人头模型），并增加中文别名“人数”便于前端展示；
    # - counts 仅包含行为类别的计数，不再重复包含 head。
    out: Dict[str, Any] = {
        'image': str(p.resolve()),
        'size': {'width': w, 'height': h},
        'detections': detections,
        'objects': [
            {
                'label': d.get('label'),
                'bbox_xyxy': d.get('bbox_xyxy'),
                'confidence': d.get('confidence'),
            } for d in detections
        ],
        'boxes': boxes_map,
        'counts': {**counts_map},
        'head': head_count,
        '人数': head_count,
        'backend': 'ultralytics',
        'provenance': {
            'head_source': 'counts_model'
        },
        'models': {
            'behavior': str(Path(behavior_pt)),
            'counts': str(Path(counts_pt)),
        }
    }
    return out
