"""
通用检测适配层：统一输出结构，便于在不同环境/后端（Ultralytics / ONNXRuntime）间切换。

当前实现：Ultralytics YOLO 直推（需要 ultralytics + torch 环境）。
如需 ORT，请后续扩展 _OrtBackend。
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any, Tuple, Optional
import time

import numpy as np
import cv2
import os

try:
    from ultralytics import YOLO  # type: ignore
except Exception:  # pragma: no cover
    YOLO = None  # type: ignore

from .labels_behavior import resolve_labels

# Optional: ONNX Runtime backend
try:
    import onnxruntime as ort  # type: ignore
except Exception:  # pragma: no cover
    ort = None  # type: ignore


@dataclass
class DetResult:
    image_size: Tuple[int, int]
    detections: List[Dict[str, Any]]
    counts: Dict[str, int]
    backend: str
    model_name: str
    time: Dict[str, float]


class Detector:
    def __init__(self, weights_path: str, kind: Optional[str] = None, backend: str = "ultralytics"):
        self.backend = backend
        self.labels = resolve_labels(kind)
        self.model_name = weights_path
        # Auto-select backend by file extension if not explicitly set
        if backend.lower().startswith('onnx') or weights_path.lower().endswith('.onnx'):
            if ort is None:
                raise RuntimeError("ONNX Runtime 未安装，请先 pip install onnxruntime")
            self.backend = 'onnxruntime'
            self._ort_session = ort.InferenceSession(weights_path, providers=[
                'CPUExecutionProvider'
            ])
            # Cache IO names
            self._ort_inputs = [i.name for i in self._ort_session.get_inputs()]
            self._ort_outputs = [o.name for o in self._ort_session.get_outputs()]
        elif backend == "ultralytics":
            if YOLO is None:
                raise RuntimeError("Ultralytics 未安装或不可用，请安装 `ultralytics` 以及匹配的 torch 版本")
            self.model = YOLO(weights_path)
        else:
            raise NotImplementedError(f"不支持的后端: {backend}")

    def predict_image(self, img: np.ndarray | str, conf: float = 0.5, save_vis_path: Optional[str] = None) -> DetResult:
        """对单张图片进行检测。

        img: 支持文件路径或 RGB/BGR ndarray；若是 ndarray，内部不强制转色，交给模型处理。
        conf: 置信度阈值
        save_vis_path: 若提供，将保存绘制结果到此路径（使用 Ultralytics 的 plot）。
        """
        t0 = time.time()
        if self.backend == "ultralytics":
            results = self.model.predict(source=img, conf=conf, imgsz=640, show=False, save_conf=True)
            infer_t = time.time()
            dets: List[Dict[str, Any]] = []
            W, H = 0, 0
            if results:
                r0 = results[0]
                try:
                    W, H = int(r0.orig_shape[1]), int(r0.orig_shape[0])
                except Exception:
                    pass
                # 优先使用模型自带的类别名映射
                names = None
                try:
                    names = getattr(self.model, 'names', None)
                    if names is None:
                        names = getattr(self.model, 'model', None)
                        names = getattr(names, 'names', None)
                except Exception:
                    names = None
                # 解析 boxes
                try:
                    xyxy = r0.boxes.xyxy.cpu().numpy() if hasattr(r0.boxes, 'xyxy') else np.zeros((0, 4), dtype=float)
                except Exception:
                    xyxy = np.zeros((0, 4), dtype=float)
                try:
                    confs = r0.boxes.conf.cpu().numpy() if hasattr(r0.boxes, 'conf') else np.zeros((0,), dtype=float)
                except Exception:
                    confs = np.zeros((0,), dtype=float)
                try:
                    clss = r0.boxes.cls.cpu().numpy().astype(int) if hasattr(r0.boxes, 'cls') else np.zeros((0,), dtype=int)
                except Exception:
                    clss = np.zeros((0,), dtype=int)
                for i in range(min(len(xyxy), len(confs), len(clss))):
                    cls_idx = int(clss[i])
                    label = None
                    if isinstance(names, dict) and cls_idx in names:
                        label = str(names[cls_idx]).strip()
                    elif 0 <= cls_idx < len(self.labels):
                        label = self.labels[cls_idx]
                    else:
                        label = str(cls_idx)
                    x1, y1, x2, y2 = map(float, xyxy[i].tolist())
                    dets.append({
                        "bbox": [x1, y1, x2, y2],
                        "score": float(confs[i]),
                        "cls": cls_idx,
                        "label": label,
                    })
                # 可视化保存
                if save_vis_path:
                    try:
                        r0.save(filename=save_vis_path)
                    except Exception:
                        pass
            post_t = time.time()
            # 汇总 counts
            counts: Dict[str, int] = {}
            for d in dets:
                lbl = d.get("label", "object")
                counts[lbl] = counts.get(lbl, 0) + 1
            return DetResult(
                image_size=(W, H),
                detections=dets,
                counts=counts,
                backend=self.backend,
                model_name=self.model_name,
                time={
                    "infer": round(infer_t - t0, 4),
                    "post": round(post_t - infer_t, 4),
                    "total": round(post_t - t0, 4),
                },
            )
        elif self.backend == 'onnxruntime':
            # Preprocess
            if isinstance(img, str):
                frame = cv2.imread(img)
                if frame is None:
                    raise FileNotFoundError(f"无法读取图片: {img}")
            else:
                frame = img
            H, W = int(frame.shape[0]), int(frame.shape[1])
            inp = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            inp = cv2.resize(inp, (640, 640), interpolation=cv2.INTER_LINEAR)
            inp = inp.astype(np.float32) / 255.0
            inp = np.transpose(inp, (2, 0, 1))[None, ...]  # NCHW

            # Run ORT
            ort_inputs = {self._ort_inputs[0]: inp}
            ort_outs = self._ort_session.run(self._ort_outputs, ort_inputs)
            infer_t = time.time()

            # Postprocess: try to support common YOLO ONNX export outputs
            dets: List[Dict[str, Any]] = []
            out = None
            # Case 1: end2end outputs with named tensors
            names = {n: i for i, n in enumerate(self._ort_outputs)}
            if 'det_boxes' in names and 'det_scores' in names and 'det_classes' in names:
                boxes = ort_outs[names['det_boxes']]  # [N,4]
                scores = ort_outs[names['det_scores']]  # [N]
                clses = ort_outs[names['det_classes']]  # [N]
                out = np.concatenate([
                    boxes, scores.reshape(-1, 1), clses.reshape(-1, 1)
                ], axis=1)
            else:
                # Case 2: single array [N,6 or 7] or [1,N,6]
                for arr in ort_outs:
                    a = np.squeeze(arr)
                    if a.ndim == 2 and a.shape[1] >= 6:
                        out = a
                        break
            if out is None:
                out = np.zeros((0, 6), dtype=np.float32)

            # Filter by conf and build dets
            for row in out:
                x1, y1, x2, y2, score, cls_idx = float(row[0]), float(row[1]), float(row[2]), float(row[3]), float(row[4]), int(row[5])
                if score < conf:
                    continue
                label = self.labels[cls_idx] if 0 <= cls_idx < len(self.labels) else str(cls_idx)
                dets.append({
                    'bbox': [x1, y1, x2, y2],
                    'score': score,
                    'cls': cls_idx,
                    'label': label,
                })

            # Visualization
            if save_vis_path:
                vis = frame.copy()
                for d in dets:
                    x1, y1, x2, y2 = map(int, d['bbox'])
                    cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(vis, f"{d['label']} {d['score']:.2f}", (x1, max(0, y1-5)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 1)
                os.makedirs(os.path.dirname(save_vis_path) or '.', exist_ok=True)
                cv2.imwrite(save_vis_path, vis)

            post_t = time.time()
            counts: Dict[str, int] = {}
            for d in dets:
                lbl = d.get('label', 'object')
                counts[lbl] = counts.get(lbl, 0) + 1
            return DetResult(
                image_size=(W, H),
                detections=dets,
                counts=counts,
                backend=self.backend,
                model_name=self.model_name,
                time={
                    'infer': round(infer_t - t0, 4),
                    'post': round(post_t - infer_t, 4),
                    'total': round(post_t - t0, 4),
                },
            )
        else:
            raise NotImplementedError
