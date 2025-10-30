"""OCR 引擎抽象层。
- 负责懒加载 PaddleOCR 或 RapidOCR
- 统一 perform(image, lang, use_local, max_side)
- 提供 parse / post_process / artifact_filter 等工具
"""
from __future__ import annotations
import os, time as _t
from typing import Any, Dict, List, Tuple
import numpy as np
from PIL import Image
from .logging_utils import get_logger
logger = get_logger()

class OCREngineManager:
    def __init__(self, lang: str = "ch", use_local_models: bool = True, local_base: str | None = None):
        self.lang = lang
        self.use_local_models = use_local_models
        self.local_base = local_base or ''
        self.backend = None  # 'paddle' | 'rapidocr'
        self.engine = None
        self.current_model = None

    # ---------- load ----------
    def ensure_loaded(self) -> bool:
        if self.engine:
            return True
        paddle_error = None
        # Try Paddle
        try:
            from paddleocr import PaddleOCR  # type: ignore
            import inspect
            params = inspect.signature(PaddleOCR.__init__).parameters
            kwargs = {"lang": self.lang}
            model_flag = 'paddle-remote'
            if self.use_local_models and self.local_base:
                try:
                    base = os.path.normpath(self.local_base)
                    det_dir = os.path.join(base, 'ch_ppocr_mobile_v2.0_det_infer')
                    rec_dir = os.path.join(base, 'ch_ppocr_mobile_v2.0_rec_infer')
                    cls_dir = os.path.join(base, 'ch_ppocr_mobile_v2.0_cls_infer')
                    if os.path.isdir(det_dir) and os.path.isdir(rec_dir):
                        if 'det_model_dir' in params: kwargs['det_model_dir'] = det_dir
                        if 'rec_model_dir' in params: kwargs['rec_model_dir'] = rec_dir
                        model_flag = 'paddle-local-mobilev2.0'
                        if 'cls_model_dir' in params and os.path.isdir(cls_dir):
                            if 'use_textline_orientation' in params or 'use_angle_cls' in params:
                                kwargs['cls_model_dir'] = cls_dir
                except Exception:
                    pass
            if 'use_textline_orientation' in params:
                kwargs['use_textline_orientation'] = True
            elif 'use_angle_cls' in params:
                kwargs['use_angle_cls'] = True
            if 'show_log' in params:
                kwargs['show_log'] = False
            self.engine = PaddleOCR(**kwargs)
            self.backend = 'paddle'
            self.current_model = model_flag
            logger.info('OCR 后端: Paddle (%s)', model_flag)
            return True
        except Exception as e:
            paddle_error = e
        # Try RapidOCR
        try:
            from rapidocr_onnxruntime import RapidOCR  # type: ignore
            self.engine = RapidOCR()
            self.backend = 'rapidocr'
            self.current_model = 'rapidocr'
            logger.info('OCR 后端: RapidOCR')
            return True
        except Exception as e2:
            logger.error('无法加载 OCR 后端. Paddle: %s RapidOCR: %s', paddle_error, e2)
            return False

    def load(self) -> bool:
        """向后兼容接口: 显式加载引擎, 返回是否成功."""
        return self.ensure_loaded()

    @property
    def is_loaded(self) -> bool:
        return self.engine is not None

    # ---------- parse ----------
    def parse_output(self, data: Any) -> List[Dict[str, Any]]:
        lines: List[Dict[str, Any]] = []
        if data is None:
            return lines
        def _to_str(x: Any) -> str:
            try:
                if x is None:
                    return ""
                if isinstance(x, bytes):
                    return x.decode('utf-8', 'ignore')
                return str(x)
            except Exception:
                return ""
        try:
            if isinstance(data, list) and data and isinstance(data[0], dict):
                for item in data:
                    lines.append({
                        'box': item.get('points') or item.get('box') or [],
                        'text': _to_str(item.get('transcription') or item.get('text') or ''),
                        'score': float(item.get('score', 0.0))
                    })
                return lines
            if len(data) == 1 and isinstance(data[0], list) and data[0] and isinstance(data[0][0], list):
                candidate = data[0]
            else:
                candidate = data
            for item in candidate:
                if not item or len(item) < 2: continue
                box = item[0]
                if isinstance(item[1], (list, tuple)) and len(item[1]) >= 2:
                    txt = _to_str(item[1][0]); score = float(item[1][1])
                elif isinstance(item[1], dict):
                    txt = _to_str(item[1].get('transcription') or item[1].get('text') or '')
                    score = float(item[1].get('score', 0.0))
                else:
                    txt = _to_str(item[1]); score = 0.0
                lines.append({'box': box, 'text': txt, 'score': score})
        except Exception as e:
            logger.warning('OCR 结果解析失败: %s', e)
        return lines

    def post_process(self, lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        try:
            import re
            def _s(x: Any) -> str:
                try:
                    if x is None:
                        return ''
                    if isinstance(x, bytes):
                        return x.decode('utf-8', 'ignore')
                    return str(x)
                except Exception:
                    return ''
            cleaned = []
            for ln in lines:
                t = _s(ln.get('text',''))
                t = re.sub(r"\s+", " ", t).strip()
                t = re.sub(r"([\u4e00-\u9fff])\s+([\u4e00-\u9fff])", r"\1\2", t)
                t = re.sub(r"\s*([,，。.!！？:：;；])\s*", r"\1", t)
                if t:
                    ln['text'] = t
                    cleaned.append(ln)
            return cleaned
        except Exception:
            return lines

    def filter_overlay(self, lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        import re
        if not lines:
            return lines
        pattern = re.compile(r"^\s*\d{2,5}x\d{2,5}\s*$")
        safe: List[Dict[str, Any]] = []
        for ln in lines:
            txt = ln.get('text','')
            if isinstance(txt, bytes):
                try:
                    txt = txt.decode('utf-8', 'ignore')
                except Exception:
                    txt = ''
            else:
                try:
                    txt = '' if txt is None else str(txt)
                except Exception:
                    txt = ''
            if not pattern.match(txt):
                safe.append(ln)
        return safe

    # ---------- perform ----------
    def perform(self, pil_img: Image.Image, use_processed: bool, max_side: int) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        if not self.ensure_loaded():
            raise RuntimeError('OCR 后端不可用')
        arr_img = pil_img.convert('RGB')
        scale = 1.0
        if max_side and max(arr_img.size) > max_side:
            scale = max_side / max(arr_img.size)
            new_size = (int(arr_img.size[0]*scale), int(arr_img.size[1]*scale))
            arr_img = arr_img.resize(new_size)
        arr = np.array(arr_img)
        t0 = _t.time()
        if self.backend == 'rapidocr':
            result, _elapsed = self.engine(arr)  # type: ignore
            data = []
            for item in result or []:
                if len(item) >= 3:
                    box, txt, score = item[0], item[1], item[2]
                    data.append([box, [txt, score]])
        else:
            if hasattr(self.engine, 'predict'):
                try:
                    data = self.engine.predict(arr)
                except Exception:
                    data = self.engine.ocr(arr, cls=True)
            else:
                data = self.engine.ocr(arr, cls=True)
        infer_end = _t.time()
        lines = self.parse_output(data)
        lines = self.post_process(lines)
        lines = self.filter_overlay(lines)
        total = _t.time() - t0
        timing = {
            'infer': infer_end - t0,
            'post': total - (infer_end - t0),
            'total': total,
            'scale_ratio': scale,
            'input_size': f"{arr_img.size[0]}x{arr_img.size[1]}",
        }
        meta = {
            'backend': self.backend,
            'model': self.current_model,
            'timing': timing
        }
        return meta, lines

    def release(self):
        if self.engine:
            self.engine = None
            self.backend = None
            self.current_model = None
            logger.info('OCR 引擎已释放')

    # 注: edges 阈值持久化逻辑在 capture.export_config/import_config 中处理，与 OCR 引擎无关。
    pass

__all__ = ['OCREngineManager']
