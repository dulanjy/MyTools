"""Flask service for student behavior detection + AI analysis (refactored)."""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Any
import shutil

import cv2
import requests
from flask import Flask, Response, request, jsonify
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename
from flask import send_from_directory
import uuid

# Add project root (the folder that contains 'screen_capture') to sys.path to reuse project modules
try:
    here = Path(__file__).resolve()
    for up in here.parents:
        # Heuristic: stop when we find the top-level project folder that contains 'screen_capture'
        if (up / 'screen_capture').exists():
            if str(up) not in sys.path:
                sys.path.append(str(up))
            break
except Exception:
    pass

# Detection adapters
from predict.detector import Detector
from predict.dual_detector import run_dual_on_image

# Optional: YOLO for legacy video/camera streaming
try:
    from ultralytics import YOLO  # type: ignore
except Exception:
    YOLO = None  # type: ignore

# Reuse AI client and analysis helpers if available
try:
    from screen_capture.ai_client import AIClient  # type: ignore
except Exception:
    AIClient = None  # type: ignore
try:
    from student_behavior_ai.analyze import (
        build_prompt,
        build_json_only_prompt,
        spatial_summary,
        rule_based_summary,
        derive_metrics,
        normalize_counts,
    )  # type: ignore
except Exception:
    build_prompt = None
    build_json_only_prompt = None
    spatial_summary = None
    rule_based_summary = None
    derive_metrics = None
    normalize_counts = None
try:
    from student_behavior_ai.report_markdown import markdown_from_ai_json  # type: ignore
except Exception:
    markdown_from_ai_json = None  # type: ignore
try:
    from student_behavior_ai.postprocess import enrich_consistency  # type: ignore
except Exception:
    enrich_consistency = None  # type: ignore
try:
    from student_behavior_ai.visualize import render_report_image  # type: ignore
except Exception:
    render_report_image = None  # type: ignore


class VideoProcessingApp:
    def __init__(self, host: str = '0.0.0.0', port: int = 5000) -> None:
        self.app = Flask(__name__)
        self.socketio = SocketIO(self.app, cors_allowed_origins="*")
        self.host = host
        self.port = port
        self.data: Dict[str, Any] = {}
        self.paths = {
            'download': './runs/video/download.mp4',
            'output': './runs/video/output.mp4',
            'camera_output': './runs/video/camera_output.avi',
            'video_output': './runs/video/camera_output.avi',
        }
        self.recording = False
        self.setup_routes()

    def _localize_image_path(self, path_or_url: str) -> str:
        """If input is an http(s) URL, download to a temp file and return the local path; otherwise return as-is."""
        if not path_or_url:
            return path_or_url
        if isinstance(path_or_url, str) and path_or_url.lower().startswith(('http://', 'https://')):
            os.makedirs('./runs/tmp', exist_ok=True)
            local_path = os.path.join('./runs/tmp', 'input.jpg')
            try:
                self.download(path_or_url, local_path)
                return local_path
            except Exception:
                return path_or_url
        return path_or_url

    def setup_routes(self) -> None:
        self.app.add_url_rule('/file_names', 'file_names', self.file_names, methods=['GET'])
        self.app.add_url_rule('/predictImg', 'predictImg', self.predictImg, methods=['POST'])
        self.app.add_url_rule('/analyze', 'analyze', self.analyze, methods=['POST'])
        self.app.add_url_rule('/dualDetect', 'dualDetect', self.dualDetect, methods=['POST'])
        # AI readiness diagnostic
        self.app.add_url_rule('/ai/status', 'ai_status', self.ai_status, methods=['GET'])
        # Alias for when accessing Flask directly with a '/flask' prefix by mistake
        self.app.add_url_rule('/flask/ai/status', 'ai_status_alias', self.ai_status, methods=['GET'])
        # Common aliases so cURL can call /flask/* directly without frontend proxy
        self.app.add_url_rule('/flask/file_names', 'file_names_alias', self.file_names, methods=['GET'])
        self.app.add_url_rule('/flask/predictImg', 'predictImg_alias', self.predictImg, methods=['POST'])
        self.app.add_url_rule('/flask/analyze', 'analyze_alias', self.analyze, methods=['POST'])
        self.app.add_url_rule('/flask/dualDetect', 'dualDetect_alias', self.dualDetect, methods=['POST'])
        self.app.add_url_rule('/flask/files/upload', 'files_upload_alias', self.files_upload, methods=['POST'])
        self.app.add_url_rule('/flask/files/<path:filename>', 'files_get_alias', self.files_get, methods=['GET'])
        self.app.add_url_rule('/predictVideo', 'predictVideo', self.predictVideo)
        self.app.add_url_rule('/predictCamera', 'predictCamera', self.predictCamera)
        self.app.add_url_rule('/stopCamera', 'stopCamera', self.stopCamera, methods=['GET'])
        # Simple file upload and serve, as a fallback when Spring is unavailable
        self.app.add_url_rule('/files/upload', 'files_upload', self.files_upload, methods=['POST'])
        self.app.add_url_rule('/files/<path:filename>', 'files_get', self.files_get, methods=['GET'])

        @self.socketio.on('connect')
        def handle_connect():
            print('WebSocket connected!')
            emit('message', {'data': 'Connected to WebSocket server!'})

        @self.socketio.on('disconnect')
        def handle_disconnect():
            print('WebSocket disconnected!')

    def run(self) -> None:
        self.socketio.run(self.app, host=self.host, port=self.port, allow_unsafe_werkzeug=True)

    # ---------- AI diagnostics ----------
    def ai_status(self):
        try:
            info = {
                'has_ai_client': AIClient is not None,
            }
            # If import failed at module load, try dynamic import once for diagnostics
            if AIClient is None:
                try:
                    import importlib
                    _m = importlib.import_module('screen_capture.ai_client')
                    info['dyn_import_ai_client'] = True
                    try:
                        info['ai_client_class'] = bool(getattr(_m, 'AIClient', None))
                    except Exception:
                        pass
                except Exception as e:
                    info['dyn_import_ai_client'] = False
                    info['dyn_import_error'] = str(e)
                try:
                    import sys as _sys
                    # Provide a small sample of sys.path for debugging
                    info['sys_path_head'] = _sys.path[:5]
                except Exception:
                    pass
            if AIClient is not None:
                client = AIClient()
                info.update({
                    'ready': bool(client.ready),
                    'model_text': getattr(client, 'model_text', ''),
                    'model_vision': getattr(client, 'model_vision', ''),
                })
                # Detect API key presence (env or keyring)
                try:
                    import os as _os
                    key_env = bool(_os.getenv('ZHIPU_API_KEY'))
                except Exception:
                    key_env = False
                key_keyring = False
                try:
                    import keyring as _keyring  # type: ignore
                    if _keyring:
                        key_keyring = bool(_keyring.get_password('zhipu', 'api_key'))
                except Exception:
                    key_keyring = False
                info['has_key_env'] = key_env
                info['has_key_keyring'] = key_keyring
                # SDK presence hint
                info['has_sdk'] = hasattr(client, '_client') and (client._client is not None)
            return jsonify({'status': 200, 'data': info})
        except Exception as e:
            return jsonify({'status': 500, 'message': str(e)})

    # ---------- File upload fallback (Flask) ----------
    def files_upload(self):
        """Accept file upload and return a URL similar to Spring's API response shape."""
        f = request.files.get('file')
        if not f:
            return jsonify({'status': 400, 'message': '缺少文件参数 file'})
        os.makedirs('./files', exist_ok=True)
        orig = secure_filename(f.filename or 'upload.bin')
        name = f"{uuid.uuid4().hex}_{orig}"
        save_path = os.path.join('./files', name)
        f.save(save_path)
        url = f"http://localhost:{self.port}/files/{name}"
        # 前端只读取 data 字段
        return jsonify({'data': url})

    def files_get(self, filename: str):
        return send_from_directory('./files', filename, as_attachment=False)

    # -------- Endpoints --------
    def file_names(self):
        weight_items = [{'value': name, 'label': name} for name in self.get_file_names('./weights')]
        return json.dumps({'weight_items': weight_items}, ensure_ascii=False)

    def predictImg(self):
        data = request.get_json(force=True, silent=True) or {}
        self.data.clear()
        self.data.update({
            'username': data.get('username', ''),
            'weight': data.get('weight', ''),
            'conf': data.get('conf', 0.5),
            'startTime': data.get('startTime', ''),
            'inputImg': data.get('inputImg', ''),
            'kind': data.get('kind', 'student'),
        })
        img_path = self._localize_image_path(self.data['inputImg'])
        weight = self.data['weight']
        kind = self.data['kind']
        conf = float(self.data['conf'] or 0.5)
        backend = (data.get('backend') or '').lower().strip() if isinstance(data, dict) else ''
        if not backend:
            backend = 'onnxruntime' if str(weight).lower().endswith('.onnx') else 'ultralytics'

        try:
            det = Detector(weights_path=f'./weights/{weight}', kind=kind, backend=backend)
            os.makedirs('./runs', exist_ok=True)
            vis_path = './runs/result.jpg'
            res = det.predict_image(img_path, conf=conf, save_vis_path=vis_path)
        except Exception as e:
            return jsonify({'status': 400, 'message': f'预测失败: {e}'})

        uploadedUrl = None
        try:
            uploadedUrl = self.upload('./runs/result.jpg')
        except Exception:
            pass

        # Build schema-compatible payload (objects/boxes/size)
        objects = []
        boxes_map: Dict[str, List[Dict[str, Any]]] = {}
        for d in res.detections:
            obj = {
                'label': d.get('label'),
                'bbox_xyxy': d.get('bbox'),
                'confidence': d.get('score'),
            }
            objects.append(obj)
            lbl = obj['label'] or 'object'
            boxes_map.setdefault(lbl, []).append({'bbox_xyxy': obj['bbox_xyxy'], 'confidence': obj['confidence']})

        out = {
            'status': 200,
            'message': '预测成功',
            'outImg': uploadedUrl or os.path.abspath('./runs/result.jpg'),
            'allTime': f"{res.time.get('total', 0):.3f}s",
            'detections': res.detections,
            'counts': res.counts,
            'objects': objects,
            'boxes': boxes_map,
            'image': str(Path(img_path).resolve()) if isinstance(img_path, str) else None,
            'size': {'width': int(res.image_size[0] or 0), 'height': int(res.image_size[1] or 0)} if res.image_size else None,
            'backend': res.backend,
            'model': res.model_name,
            'image_size': list(res.image_size),
        }
    # 异步/同步保存识别记录到 Spring（便于前端历史查看）
        try:
            try:
                labels = [str(o.get('label') or '') for o in out.get('objects', [])]
                confidences = [o.get('confidence') for o in out.get('objects', [])]
            except Exception:
                labels = []
                confidences = []
            # fallback: 若没有 objects，则用 counts 的键作为 labels
            if not labels and isinstance(out.get('counts'), dict):
                try:
                    labels = list(out.get('counts').keys())
                    confidences = [int(v) for v in out.get('counts').values()]
                except Exception:
                    labels = []
                    confidences = []

            record = {
                'username': self.data.get('username'),
                'inputImg': self.data.get('inputImg'),
                'outImg': out.get('outImg'),
                'weight': self.data.get('weight'),
                'allTime': out.get('allTime'),
                'conf': self.data.get('conf'),
                'startTime': self.data.get('startTime'),
                # 后端期望 label/confidence 为 JSON 字符串
                'label': json.dumps(labels, ensure_ascii=False),
                'confidence': json.dumps(confidences, ensure_ascii=False),
            }
            # 发送到 Spring 的 imgRecords 接口：优先尝试环境配置的路径（默认 /imgRecords），失败再试备选路径
            base_url = os.environ.get('SPRING_BASE_URL', f'http://localhost:{self.port + 4999}').rstrip('/') if False else os.environ.get('SPRING_BASE_URL', 'http://localhost:9999').rstrip('/')
            primary_path = os.environ.get('SPRING_IMGRECORDS_PATH', '/imgRecords')
            alt_path = '/api/imgRecords' if primary_path != '/api/imgRecords' else '/imgRecords'
            candidates = [f"{base_url}{primary_path}", f"{base_url}{alt_path}"]

            attempted = []
            last_status = None
            for url in candidates:
                attempted.append(url)
                try:
                    last_status = self.save_data(json.dumps(record, ensure_ascii=False), url)
                except Exception:
                    last_status = None
                # 成功即停止重试
                if last_status == 200:
                    break
            # 在返回体中附加一次简短的上传结果，便于前端/调用方调试
            try:
                out['record_upload'] = {
                    'attempted_urls': attempted,
                    'last_status_code': last_status,
                    'debug_dir': './runs/debug_img_records' if (last_status is None or last_status != 200) else None
                }
            except Exception:
                pass
        except Exception:
            pass

        return jsonify(out)

    def analyze(self):
        """一体化：检测 + AI 分析。

        入参 JSON：
        {
        "inputImg": "./some.jpg",          # 可选；若缺省且提供 counts，则仅文本分析
        "weight": "yolov8n-student.pt",    # 可选；提供图片时需要
        "kind": "student",                 # 可选
        "conf": 0.5,                        # 可选
        "json_only": true,                  # 可选；默认 true，期望严格 JSON 输出
        "prompt": "...",                   # 可选；覆盖默认提示
        "counts": { ... }                   # 可选；若提供，将与检测汇总合并
        }
        """
        data = request.get_json(force=True, silent=True) or {}
        img_path = self._localize_image_path(data.get('inputImg'))
        weight = data.get('weight')
        kind = data.get('kind', 'student')
        conf = float(data.get('conf', 0.5))
        json_only = bool(data.get('json_only', True))
        two_stage = bool(data.get('two_stage', True))  # 默认 true：先取严格 JSON，再本地生成 Markdown
        strict_pipeline = bool(data.get('strict_pipeline', True))  # 默认强制双模型后再 AI 化
        custom_prompt = data.get('prompt')
        counts_in = data.get('counts') or {}
        behavior_json_path = data.get('behavior_json_path')
        behavior_json_raw = data.get('behavior_json')
        analysis_json_path = data.get('analysis_json_path')  # 新增：若已存在AI化后的JSON，可直接使用
        save_reference = bool(data.get('save_reference', True))  # 额外保存参考JSON与提示词
        save_json_out = bool(data.get('save_json_out', False))
        out_dir_req = data.get('out_dir') or None
        out_stem_req = data.get('out_stem') or None
        title_req = data.get('title') or '课堂行为分析'
        aiize_mode = False
        backend = (data.get('backend') or '').lower().strip()
        if not backend and weight:
            backend = 'onnxruntime' if str(weight).lower().endswith('.onnx') else 'ultralytics'

        # 记录本次模式与用于模型的最终提示文本，便于保存参考
        mode_name = None
        last_prompt_text = None

        # 若传入 analysis_json_path，直接使用 AI 化后的 JSON 进行渲染与可视化
        if analysis_json_path:
            # 支持三种来源：
            # 1) 本地文件绝对/相对路径
            # 2) HTTP/HTTPS URL（例如先通过 /flask/files/upload 上传返回的 URL）
            # 3) /files/ 前缀的相对路径（自动补 http://localhost:{port}）
            try:
                path_or_url = str(analysis_json_path).strip()
                use_url = False
                if path_or_url.lower().startswith(('http://', 'https://')):
                    use_url = True
                elif path_or_url.startswith('/files/'):
                    path_or_url = f"http://localhost:{self.port}{path_or_url}"
                    use_url = True

                if use_url:
                    try:
                        resp = requests.get(path_or_url, timeout=10)
                        resp.raise_for_status()
                        result_json = resp.json()
                    except Exception as e:
                        return jsonify({'status': 400, 'message': f'下载 analysis_json_path 失败: {e}'})
                else:
                    with open(path_or_url, 'r', encoding='utf-8') as f:
                        result_json = json.load(f)
            except Exception as e:
                return jsonify({'status': 400, 'message': f'读取 analysis_json_path 失败: {e}'})
            mode_name = 'reuse'
            # 富化与可视化
            try:
                if enrich_consistency and isinstance(result_json, dict):
                    result_json = enrich_consistency(result_json)
            except Exception:
                pass
            # 若仍缺少 observations，做一次兜底填充
            try:
                def _ensure_observations(js):
                    try:
                        obs = js.get('observations')
                        if not isinstance(obs, list) or len(obs) == 0:
                            mt = js.get('metrics') or {}
                            sp = (js.get('spatial') or {}).get('grid3x3') or None
                            head_v = js.get('head') or js.get('人数')
                            bullets = []
                            if isinstance(head_v, int) and head_v > 0:
                                bullets.append(f'人数 {head_v}')
                            try:
                                if isinstance(mt.get('head_down_rate'), int):
                                    bullets.append(f'低头率约 {mt.get("head_down_rate")}%' )
                            except Exception:
                                pass
                            try:
                                if isinstance(mt.get('phone_usage_rate'), int):
                                    bullets.append(f'看手机约 {mt.get("phone_usage_rate")}%' )
                            except Exception:
                                pass
                            try:
                                if isinstance(mt.get('sleeping_rate'), int):
                                    bullets.append(f'打瞌睡约 {mt.get("sleeping_rate")}%' )
                            except Exception:
                                pass
                            if isinstance(sp, list) and len(sp) == 3 and all(isinstance(r, list) and len(r) == 3 for r in sp):
                                maxv = -1; maxi = (0,0)
                                for rr in range(3):
                                    for cc in range(3):
                                        v = sp[rr][cc] or 0
                                        if v > maxv:
                                            maxv = v; maxi = (rr, cc)
                                if maxv > 0:
                                    row_lab = ['前排','中排','后排'][maxi[0]]; col_lab = ['左侧','中间','右侧'][maxi[1]]
                                    bullets.append(f'{row_lab}{col_lab}人数较多（{maxv}）')
                            if bullets:
                                js['observations'] = bullets[:6]
                    except Exception:
                        pass
                    return js
                if isinstance(result_json, dict):
                    result_json = _ensure_observations(result_json)
            except Exception:
                pass
            # 生成可视化 PNG
            result_image_url = None
            try:
                if render_report_image and isinstance(result_json, dict):
                    os.makedirs('./files', exist_ok=True)
                    img_name = f"analysis_{uuid.uuid4().hex}.png"
                    out_path = os.path.join('./files', img_name)
                    render_report_image(result_json, out_path, title=title_req)
                    result_image_url = f"http://localhost:{self.port}/files/{img_name}"
            except Exception:
                result_image_url = None
            # 渲染 Markdown（仅展示关键观察要点与局限性）
            result_markdown = None
            try:
                if markdown_from_ai_json is not None and isinstance(result_json, dict):
                    result_markdown = markdown_from_ai_json(result_json, title='课堂行为分析')
            except Exception:
                pass
            # 保存参考 JSON（基于复用）
            saved_reference_json_path = None
            if save_reference:
                try:
                    base_dir = out_dir_req or os.path.dirname(os.path.abspath(analysis_json_path))
                    os.makedirs(base_dir, exist_ok=True)
                    stem = os.path.splitext(os.path.basename(analysis_json_path))[0]
                    ref_path = os.path.join(base_dir, f"{stem}_reference.json")
                    import time as _time
                    ref_payload = {
                        'mode': 'reuse',
                        'analysis_json_path': os.path.abspath(analysis_json_path),
                        'timestamp': _time.strftime('%Y-%m-%d %H:%M:%S')
                    }
                    with open(ref_path, 'w', encoding='utf-8') as rf:
                        rf.write(json.dumps(ref_payload, ensure_ascii=False, indent=2))
                    saved_reference_json_path = ref_path
                except Exception:
                    saved_reference_json_path = None
            return jsonify({
                'status': 200,
                'message': '分析完成(复用已AI化JSON)',
                'counts': None,
                'detections': None,
                'image_size': None,
                'analysis_markdown': result_markdown,
                'analysis_json': result_json,
                'analysis_image_url': result_image_url,
                'saved_analysis_json_path': os.path.abspath(analysis_json_path),
                'saved_analysis_png_path': None,
                'saved_reference_json_path': saved_reference_json_path,
            })

        # 若传入 behavior_json_path/behavior_json，则走“AI 化已有 JSON 再分析”的流程
        behavior_obj = None
        if behavior_json_path:
            try:
                with open(behavior_json_path, 'r', encoding='utf-8') as f:
                    behavior_obj = json.load(f)
                    aiize_mode = True
            except Exception as e:
                return jsonify({'status': 400, 'message': f'读取 behavior_json_path 失败: {e}'})
        elif behavior_json_raw is not None:
            try:
                behavior_obj = behavior_json_raw if isinstance(behavior_json_raw, dict) else json.loads(str(behavior_json_raw))
                aiize_mode = True
            except Exception as e:
                return jsonify({'status': 400, 'message': f'解析 behavior_json 失败: {e}'})

        # 强制流程：未提供行为 JSON 且未显式给 counts 时，拒绝直接图片分析（避免与实际场景无关的输出）
        if strict_pipeline and (not aiize_mode) and (not (isinstance(counts_in, dict) and counts_in)):
            return jsonify({'status': 400, 'message': '严格流程：请先调用 /flask/dualDetect 生成 *_behavior.json，随后使用 behavior_json_path 调用 /flask/analyze。若要放宽为图片直出，请设置 strict_pipeline=false。'})

        # 先检测（如提供图片；若 aiize_mode 则跳过检测）
        counts = dict(counts_in) if isinstance(counts_in, dict) else {}
        boxes: List[Dict[str, Any]] = []
        img_size = None
        if not aiize_mode and img_path and weight:
            try:
                det = Detector(weights_path=f'./weights/{weight}', kind=kind, backend=backend)
                res = det.predict_image(img_path, conf=conf, save_vis_path=None)
                img_size = res.image_size
                boxes = res.detections
                for k, v in res.counts.items():
                    counts[k] = counts.get(k, 0) + int(v)
            except Exception as e:
                return jsonify({'status': 400, 'message': f'检测失败: {e}'})

        # 若处于 AI 化现有 JSON 模式（behavior_json_path/behavior_json），则将其中的 counts/boxes/size 注入，
        # 以便后续富化/兜底（否则会出现 metrics=0、per_class 为空等问题）。
        if aiize_mode and isinstance(behavior_obj, dict):
            try:
                # 合并 counts（保持原键名，后续会统一 normalize）
                bc = behavior_obj.get('counts') or {}
                if isinstance(bc, dict):
                    for k, v in bc.items():
                        try:
                            counts[k] = counts.get(k, 0) + int(v)
                        except Exception:
                            pass
            except Exception:
                pass
            try:
                # 解析图片尺寸
                if isinstance(behavior_obj.get('size'), dict):
                    W = int(behavior_obj['size'].get('width') or 0)
                    H = int(behavior_obj['size'].get('height') or 0)
                    if W > 0 and H > 0:
                        img_size = (W, H)
                elif isinstance(behavior_obj.get('image_size'), dict):
                    W = int(behavior_obj['image_size'].get('width') or 0)
                    H = int(behavior_obj['image_size'].get('height') or 0)
                    if W > 0 and H > 0:
                        img_size = (W, H)
            except Exception:
                pass
            try:
                # 构造 boxes 列表（用于 spatial_summary）
                boxes2: List[Dict[str, Any]] = []
                # 优先 objects 列表
                if isinstance(behavior_obj.get('objects'), list):
                    for it in behavior_obj['objects']:
                        try:
                            lbl = (it.get('label') or 'object')
                            bb = it.get('bbox') or it.get('bbox_xyxy') or it.get('xyxy') or it.get('xywh')
                            if isinstance(bb, (list, tuple)) and len(bb) == 4:
                                boxes2.append({'label': lbl, 'bbox': [float(bb[0]), float(bb[1]), float(bb[2]), float(bb[3])]})
                        except Exception:
                            pass
                # 其次 boxes 映射 {label: [ {...}, ... ]}
                if isinstance(behavior_obj.get('boxes'), dict):
                    for k, arr in behavior_obj['boxes'].items():
                        if isinstance(arr, list):
                            for it in arr:
                                try:
                                    bb = it.get('bbox') or it.get('bbox_xyxy') or it.get('xyxy') or it.get('xywh')
                                    if isinstance(bb, (list, tuple)) and len(bb) == 4:
                                        boxes2.append({'label': k, 'bbox': [float(bb[0]), float(bb[1]), float(bb[2]), float(bb[3])]})
                                except Exception:
                                    pass
                if boxes2:
                    boxes = boxes2
            except Exception:
                pass

        # 规则摘要
        rb_text = None
        if rule_based_summary:
            try:
                rb_text = rule_based_summary(counts)
            except Exception:
                rb_text = None

        result_markdown = None
        result_json = None
        result_image_url = None
        if AIClient is not None and (build_prompt or build_json_only_prompt):
            try:
                from PIL import Image
                client = AIClient()
                if client.ready:
                    # 若为 AI 化模式：直接对传入的 behavior JSON 做严格 JSON 规整，再本地渲染
                    if aiize_mode:
                        try:
                            # 构建严格 JSON 提示词 + 注入原始 JSON（前置 AI 角色与JSON优先声明）
                            head_prompt = build_json_only_prompt(custom_prompt) if build_json_only_prompt else (custom_prompt or '')
                            preface = (
                                "你是一名教学观察与课堂行为分析助手。\n"
                                "- 使用简体中文；仅可基于提供的结构化 JSON（检测/统计/已有分析）进行推断；不得编造与教育场景无关的内容，也不要复述网络百科/问答列表。\n"
                                "- 若图片与 JSON 冲突，优先保留 JSON 结论，并在 limitations 指出冲突与依据；避免臆测与空泛表述。\n"
                                "- 输出必须是严格的 JSON 对象，符合 schema_version=1.1，包含 summary/metrics/per_class/spatial/limitations/confidence 等字段；如可确定，请补充 head 与 人数。\n"
                                "- 注意：前端仅展示 observations 与 limitations 两个板块，请务必完整、客观、简明地填充它们（observations 4-8条、每条≤30字，包含位置/行为/比例信息；limitations 2-8条）。"
                            )
                            head_prompt = preface + "\n\n" + head_prompt
                            import json as _json
                            head_prompt += "\n以下为原始 JSON：\n" + _json.dumps(behavior_obj, ensure_ascii=False) + "\n"
                            last_prompt_text = head_prompt
                            mode_name = 'aiize'
                        except Exception:
                            head_prompt = custom_prompt or ''

                        # 发送到 AI，获取严格 JSON
                        messages = [{"role": "user", "content": [{"type": "text", "text": head_prompt}]}]
                        ai_res = client.chat(messages, response_format={"type": "json_object"})
                        content = ai_res.get('content') or ''
                        try:
                            result_json = json.loads(content)
                        except Exception:
                            result_json = None

                        # 丰富与一致性处理：确保 head/人数、一致的 provenance
                        try:
                            if result_json is not None and isinstance(result_json, dict):
                                # 若缺少 head，则尝试从原 JSON 推断
                                if 'head' not in result_json:
                                    try:
                                        # 优先顶层 head；其次 counts 汇总
                                        h = None
                                        if isinstance(behavior_obj, dict):
                                            if isinstance(behavior_obj.get('head'), int):
                                                h = int(behavior_obj['head'])
                                            else:
                                                bc = behavior_obj.get('counts') or {}
                                                if isinstance(bc, dict):
                                                    s = sum(int(v) for v in bc.values() if isinstance(v, int))
                                                    h = s if s > 0 else None
                                        if h is not None:
                                            result_json['head'] = h
                                    except Exception:
                                        pass
                                # 人数别名
                                try:
                                    if 'head' in result_json:
                                        result_json['人数'] = int(result_json['head'])
                                except Exception:
                                    pass
                                # provenance
                                try:
                                    prov = result_json.get('provenance')
                                    if not isinstance(prov, dict):
                                        prov = {}
                                    prov.setdefault('generated_by', 'ai')
                                    prov.setdefault('head_source', 'behavior_json')
                                    result_json['provenance'] = prov
                                except Exception:
                                    pass
                        except Exception:
                            pass

                        # 一致性与可视化
                        if result_json is not None and isinstance(result_json, dict):
                            try:
                                if enrich_consistency:
                                    result_json = enrich_consistency(result_json)
                            except Exception:
                                pass
                            # 生成可视化 PNG
                            try:
                                if render_report_image:
                                    os.makedirs('./files', exist_ok=True)
                                    img_name = f"analysis_{uuid.uuid4().hex}.png"
                                    out_path = os.path.join('./files', img_name)
                                    render_report_image(result_json, out_path, title='课堂行为分析')
                                    result_image_url = f"http://localhost:{self.port}/files/{img_name}"
                            except Exception:
                                result_image_url = None

                        # 渲染 Markdown（若可行）
                        if result_json is not None and markdown_from_ai_json is not None:
                            # 使用本地模板渲染简洁标题
                            result_markdown = markdown_from_ai_json(result_json, title='课堂行为分析')
                        else:
                            # 严格模式：不直接采用 AI 原始文本；先尝试从文本中提取 JSON，否则生成本地回退 JSON
                            result_markdown = None
                            # 尝试从文本中提取 JSON 并可视化
                            try:
                                parsed = None
                                import re as _re
                                m = _re.search(r"```json\s*(\{[\s\S]*?\})\s*```", content, _re.IGNORECASE)
                                if not m:
                                    m = _re.search(r"```\s*(\{[\s\S]*?\})\s*```", content, _re.IGNORECASE)
                                if m:
                                    parsed = json.loads(m.group(1))
                                else:
                                    # 最大平衡花括号块
                                    t = content
                                    first = t.find('{')
                                    while first != -1 and parsed is None:
                                        depth = 0; in_str = False; esc = False
                                        for i in range(first, len(t)):
                                            ch = t[i]
                                            if in_str:
                                                if esc:
                                                    esc = False
                                                elif ch == '\\':
                                                    esc = True
                                                elif ch == '"':
                                                    in_str = False
                                            else:
                                                if ch == '"':
                                                    in_str = True
                                                elif ch == '{':
                                                    depth += 1
                                                elif ch == '}':
                                                    depth -= 1
                                                    if depth == 0:
                                                        cand = t[first:i+1]
                                                        try:
                                                            parsed = json.loads(cand)
                                                        except Exception:
                                                            pass
                                                        break
                                        first = t.find('{', first + 1)
                                if isinstance(parsed, dict):
                                    if enrich_consistency:
                                        try:
                                            parsed = enrich_consistency(parsed)
                                        except Exception:
                                            pass
                                    if render_report_image:
                                        try:
                                            os.makedirs('./files', exist_ok=True)
                                            img_name = f"analysis_{uuid.uuid4().hex}.png"
                                            out_path = os.path.join('./files', img_name)
                                            render_report_image(parsed, out_path, title='课堂行为分析')
                                            result_image_url = f"http://localhost:{self.port}/files/{img_name}"
                                            result_json = parsed
                                        except Exception:
                                            pass
                                    # 渲染 Markdown（若模板可用）
                                    try:
                                        if markdown_from_ai_json is not None:
                                            result_markdown = markdown_from_ai_json(parsed, title='课堂行为分析')
                                    except Exception:
                                        pass
                                # 若仍无 JSON，生成基于 counts 的回退可视化
                                if (result_image_url is None) and render_report_image:
                                    try:
                                        sp = spatial_summary(boxes, img_size) if spatial_summary else {}
                                        # 估算 head
                                        head_est = None
                                        try:
                                            c_norm = normalize_counts(counts) if normalize_counts else (counts or {})
                                            if isinstance(c_norm, dict):
                                                if 'head' in c_norm and isinstance(c_norm.get('head'), int):
                                                    head_est = int(c_norm['head'])
                                                else:
                                                    s = sum(int(v) for v in c_norm.values() if isinstance(v, int))
                                                    head_est = s if s > 0 else None
                                        except Exception:
                                            head_est = None
                                        fallback = {
                                            'schema_version': '1.1',
                                            'summary': '基于计数与空间分布的概览',
                                            'observations': [],
                                            'metrics': derive_metrics(c_norm, head_est) if derive_metrics else {},
                                            'per_class': {k: {'count': int(v)} for k, v in (c_norm or {}).items()},
                                            'spatial': sp or {},
                                            'limitations': ['基于输入计数与空间分布的自动整理，可能与实际存在偏差'],
                                            'confidence': 'low',
                                            'source': {'image_path': img_path or '', 'image_size': {'width': int((img_size or [0,0])[0] or 0), 'height': int((img_size or [0,0])[1] or 0)}},
                                            'provenance': {'generated_by': 'local_postprocess'}
                                        }
                                        # 注入 head/人数 并进行富化，尽量填充 observations/limitations
                                        try:
                                            if head_est is not None:
                                                fallback['head'] = int(head_est)
                                                fallback['人数'] = int(head_est)
                                        except Exception:
                                            pass
                                        try:
                                            if enrich_consistency:
                                                fallback = enrich_consistency(fallback)
                                        except Exception:
                                            pass
                                        os.makedirs('./files', exist_ok=True)
                                        img_name = f"analysis_{uuid.uuid4().hex}.png"
                                        out_path = os.path.join('./files', img_name)
                                        render_report_image(fallback, out_path, title='课堂行为分析')
                                        result_image_url = f"http://localhost:{self.port}/files/{img_name}"
                                        result_json = fallback
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                            # 若未能使用模板渲染，则以 JSON 文本作为 Markdown 兜底，避免引入与场景无关的模型文本
                            if result_markdown is None:
                                if result_json is not None and isinstance(result_json, dict):
                                    try:
                                        if markdown_from_ai_json is not None:
                                            result_markdown = markdown_from_ai_json(result_json, title='课堂行为分析')
                                        else:
                                            result_markdown = json.dumps(result_json, ensure_ascii=False, indent=2)
                                    except Exception:
                                        result_markdown = json.dumps(result_json, ensure_ascii=False, indent=2)

                    # 两阶段（先 JSON，再报告）或严格 JSON 模式（非 aiize 模式）
                    elif two_stage or json_only:
                        # 1) 构建严格 JSON 提示词，并注入 counts、head 估计与空间分布
                        if build_json_only_prompt:
                            head = build_json_only_prompt(custom_prompt)
                        else:
                            head = (custom_prompt or '')
                        # 前置 AI 角色与 JSON 优先声明
                        try:
                            preface = (
                                "你是一名教学观察与课堂行为分析助手。\n"
                                "- 使用简体中文；仅可基于提供的结构化 JSON（检测/统计/已有分析）进行推断；不得编造与教育场景无关的内容，也不要复述网络百科/问答列表。\n"
                                "- 若图片与 JSON 冲突，优先保留 JSON 结论，并在 limitations 指出冲突与依据；避免臆测与空泛表述。\n"
                                "- 输出必须是严格的 JSON 对象，符合 schema_version=1.1，包含 summary/metrics/per_class/spatial/limitations/confidence 等字段；如可确定，请补充 head 与 人数。\n"
                                "- 注意：前端仅展示 observations 与 limitations 两个板块，请务必完整、客观、简明地填充它们（observations 4-8条、每条≤30字，包含位置/行为/比例信息；limitations 2-8条）。"
                            )
                            head = preface + "\n\n" + head
                        except Exception:
                            pass
                        # 注入 counts JSON
                        try:
                            import json as _json
                            if isinstance(counts, dict) and counts:
                                head += "\n\n以下为检测/统计 JSON：\n" + _json.dumps(counts, ensure_ascii=False) + "\n"
                        except Exception:
                            pass
                        # 注入 head 估计
                        try:
                            c_norm2 = normalize_counts(counts) if normalize_counts else (counts or {})
                            head_est2 = None
                            if isinstance(c_norm2, dict):
                                if 'head' in c_norm2 and isinstance(c_norm2.get('head'), int):
                                    head_est2 = int(c_norm2['head'])
                                else:
                                    s2 = sum(int(v) for v in c_norm2.values() if isinstance(v, int))
                                    head_est2 = s2 if s2 > 0 else None
                            if head_est2 is not None:
                                head += f"\n学生总数 (head): {head_est2}\n"
                        except Exception:
                            pass

                        # 严格 JSON：统一走文本聊天并要求 JSON 对象输出
                        messages = [{"role": "user", "content": [{"type": "text", "text": head}]}]
                        ai_res = client.chat(messages, response_format={"type": "json_object"})
                        last_prompt_text = head
                        mode_name = 'two_stage'

                        content = ai_res.get('content') or ''
                        try:
                            result_json = json.loads(content)
                        except Exception:
                            result_json = None

                        # 丰富/补全 JSON：基于 counts/head 计算缺失指标与 per_class
                        try:
                            if result_json is not None and isinstance(result_json, dict):
                                # 归一化输入计数
                                c_norm = normalize_counts(counts) if normalize_counts else (counts or {})
                                # 估算 head
                                head_est = None
                                try:
                                    if isinstance(c_norm, dict):
                                        if 'head' in c_norm and isinstance(c_norm.get('head'), int):
                                            head_est = int(c_norm['head'])
                                        else:
                                            s = 0
                                            for v in c_norm.values():
                                                if isinstance(v, int):
                                                    s += int(v)
                                            head_est = s if s > 0 else None
                                except Exception:
                                    head_est = None
                                # metrics
                                if derive_metrics and (not isinstance(result_json.get('metrics'), dict) or not result_json.get('metrics')):
                                    result_json['metrics'] = derive_metrics(c_norm, head_est)
                                # per_class
                                if 'per_class' not in result_json or not isinstance(result_json.get('per_class'), dict):
                                    per_class = {}
                                    denom = head_est if isinstance(head_est, int) and head_est > 0 else 0
                                    if denom <= 0:
                                        denom = sum(int(v) for v in c_norm.values() if isinstance(v, int)) or 1
                                    for k, v in (c_norm or {}).items():
                                        try:
                                            vi = int(v)
                                            rate = int(round(vi / max(1, denom) * 100))
                                            per_class[k] = {'count': vi, 'rate': rate}
                                        except Exception:
                                            pass
                                    result_json['per_class'] = per_class
                                # head
                                try:
                                    if 'head' not in result_json and head_est is not None:
                                        result_json['head'] = int(head_est)
                                except Exception:
                                    pass
                                # 默认置信度/局限性
                                if 'confidence' not in result_json:
                                    result_json['confidence'] = 'medium'
                                if 'limitations' not in result_json or not isinstance(result_json.get('limitations'), list):
                                    result_json['limitations'] = ['基于检测计数与空间分布推断，可能存在遮挡/分辨率限制导致的不确定性']
                                # provenance
                                try:
                                    prov = result_json.get('provenance')
                                    if not isinstance(prov, dict):
                                        prov = {}
                                    prov.setdefault('generated_by', 'ai')
                                    prov.setdefault('model', getattr(client, 'model_vision', '') if (img_path and os.path.exists(img_path)) else getattr(client, 'model_text', ''))
                                    result_json['provenance'] = prov
                                except Exception:
                                    pass
                        except Exception:
                            pass

                        # 3) 一致性增强与可视化
                        if result_json is not None and isinstance(result_json, dict):
                            try:
                                if enrich_consistency:
                                    result_json = enrich_consistency(result_json)
                            except Exception:
                                pass
                            # 兜底补齐 observations
                            try:
                                def _ensure_observations(js):
                                    try:
                                        obs = js.get('observations')
                                        if not isinstance(obs, list) or len(obs) == 0:
                                            mt = js.get('metrics') or {}
                                            sp = (js.get('spatial') or {}).get('grid3x3') or None
                                            head_v = js.get('head') or js.get('人数')
                                            bullets = []
                                            if isinstance(head_v, int) and head_v > 0:
                                                bullets.append(f'人数 {head_v}')
                                            try:
                                                if isinstance(mt.get('head_down_rate'), int):
                                                    bullets.append(f'低头率约 {mt.get("head_down_rate")}%' )
                                            except Exception:
                                                pass
                                            try:
                                                if isinstance(mt.get('phone_usage_rate'), int):
                                                    bullets.append(f'看手机约 {mt.get("phone_usage_rate")}%' )
                                            except Exception:
                                                pass
                                            try:
                                                if isinstance(mt.get('sleeping_rate'), int):
                                                    bullets.append(f'打瞌睡约 {mt.get("sleeping_rate")}%' )
                                            except Exception:
                                                pass
                                            if isinstance(sp, list) and len(sp) == 3 and all(isinstance(r, list) and len(r) == 3 for r in sp):
                                                maxv = -1; maxi = (0,0)
                                                for rr in range(3):
                                                    for cc in range(3):
                                                        v = sp[rr][cc] or 0
                                                        if v > maxv:
                                                            maxv = v; maxi = (rr, cc)
                                                if maxv > 0:
                                                    row_lab = ['前排','中排','后排'][maxi[0]]; col_lab = ['左侧','中间','右侧'][maxi[1]]
                                                    bullets.append(f'{row_lab}{col_lab}人数较多（{maxv}）')
                                            if bullets:
                                                js['observations'] = bullets[:6]
                                    except Exception:
                                        pass
                                    return js
                                result_json = _ensure_observations(result_json)
                            except Exception:
                                pass
                            try:
                                if render_report_image:
                                    os.makedirs('./files', exist_ok=True)
                                    img_name = f"analysis_{uuid.uuid4().hex}.png"
                                    out_path = os.path.join('./files', img_name)
                                    render_report_image(result_json, out_path, title='课堂行为分析')
                                    result_image_url = f"http://localhost:{self.port}/files/{img_name}"
                            except Exception:
                                result_image_url = None

                        # 4) 本地模板渲染 Markdown（若可用）；严格模式下不直接返回 AI 文本
                        if result_json is not None and markdown_from_ai_json is not None:
                            result_markdown = markdown_from_ai_json(result_json, title='课堂行为分析')
                        elif result_json is not None:
                            # 退回为 JSON 文本
                            try:
                                result_markdown = json.dumps(result_json, ensure_ascii=False, indent=2)
                            except Exception:
                                result_markdown = str(result_json)
                        else:
                            # 仍未拿到 JSON，维持空，后续兜底逻辑会填充
                            result_markdown = None
                    else:
                        # 直接构建报告型提示词并调用（保持兼容）
                        if build_prompt:
                            head = build_prompt(counts, custom_prompt)
                        else:
                            head = (custom_prompt or '')
                        # 注入空间分布
                        if spatial_summary and boxes:
                            try:
                                sp = spatial_summary(boxes, img_size)
                                import json as _json
                                head += "\n\n以下为检测框的空间分布（3x3 区域计数）JSON：\n" + _json.dumps(sp, ensure_ascii=False) + "\n"
                            except Exception:
                                pass

                        if img_path and os.path.exists(img_path):
                            img = Image.open(img_path).convert('RGB')
                            ai_res = client.analyze_image(img, head)
                        else:
                            messages = [{"role": "user", "content": [{"type": "text", "text": head}]}]
                            ai_res = client.chat(messages)

                        meta = ai_res.get('meta') or {}
                        content = ai_res.get('content') or ''
                        # 严格模式：不直接返回 AI 文本，等待后续解析/回退
                        result_markdown = None
                        # 同样尝试可视化（提取 JSON 或生成回退）
                        try:
                            parsed = None
                            import re as _re
                            m = _re.search(r"```json\s*(\{[\s\S]*?\})\s*```", content, _re.IGNORECASE)
                            if not m:
                                m = _re.search(r"```\s*(\{[\s\S]*?\})\s*```", content, _re.IGNORECASE)
                            if m:
                                parsed = json.loads(m.group(1))
                            else:
                                t = content
                                first = t.find('{')
                                while first != -1 and parsed is None:
                                    depth = 0; in_str = False; esc = False
                                    for i in range(first, len(t)):
                                        ch = t[i]
                                        if in_str:
                                            if esc:
                                                esc = False
                                            elif ch == '\\':
                                                esc = True
                                            elif ch == '"':
                                                in_str = False
                                        else:
                                            if ch == '"':
                                                in_str = True
                                            elif ch == '{':
                                                depth += 1
                                            elif ch == '}':
                                                depth -= 1
                                                if depth == 0:
                                                    cand = t[first:i+1]
                                                    try:
                                                        parsed = json.loads(cand)
                                                    except Exception:
                                                        pass
                                                    break
                                    first = t.find('{', first + 1)
                            if isinstance(parsed, dict):
                                if enrich_consistency:
                                    try:
                                        parsed = enrich_consistency(parsed)
                                    except Exception:
                                        pass
                                if render_report_image:
                                    try:
                                        os.makedirs('./files', exist_ok=True)
                                        img_name = f"analysis_{uuid.uuid4().hex}.png"
                                        out_path = os.path.join('./files', img_name)
                                        render_report_image(parsed, out_path, title='课堂行为分析')
                                        result_image_url = f"http://localhost:{self.port}/files/{img_name}"
                                        result_json = parsed
                                    except Exception:
                                        pass
                            if (result_image_url is None) and render_report_image:
                                try:
                                    sp = spatial_summary(boxes, img_size) if spatial_summary else {}
                                    # 估算 head
                                    head_est = None
                                    try:
                                        c_norm = normalize_counts(counts) if normalize_counts else (counts or {})
                                        if isinstance(c_norm, dict):
                                            if 'head' in c_norm and isinstance(c_norm.get('head'), int):
                                                head_est = int(c_norm['head'])
                                            else:
                                                s = sum(int(v) for v in c_norm.values() if isinstance(v, int))
                                                head_est = s if s > 0 else None
                                    except Exception:
                                        head_est = None
                                    fallback = {
                                        'schema_version': '1.1',
                                        'summary': '基于计数与空间分布的概览',
                                        'observations': [],
                                        'metrics': derive_metrics(c_norm, head_est) if derive_metrics else {},
                                        'per_class': {k: {'count': int(v)} for k, v in (c_norm or {}).items()},
                                        'spatial': sp or {},
                                        'limitations': ['基于输入计数与空间分布的自动整理，可能与实际存在偏差'],
                                        'confidence': 'low',
                                        'source': {'image_path': img_path or '', 'image_size': {'width': int((img_size or [0,0])[0] or 0), 'height': int((img_size or [0,0])[1] or 0)}},
                                        'provenance': {'generated_by': 'local_postprocess'}
                                    }
                                    # 注入 head/人数 并进行富化，尽量填充 observations/limitations
                                    try:
                                        if head_est is not None:
                                            fallback['head'] = int(head_est)
                                            fallback['人数'] = int(head_est)
                                    except Exception:
                                        pass
                                    try:
                                        if enrich_consistency:
                                            fallback = enrich_consistency(fallback)
                                    except Exception:
                                        pass
                                    os.makedirs('./files', exist_ok=True)
                                    img_name = f"analysis_{uuid.uuid4().hex}.png"
                                    out_path = os.path.join('./files', img_name)
                                    render_report_image(fallback, out_path, title='课堂行为分析')
                                    result_image_url = f"http://localhost:{self.port}/files/{img_name}"
                                    result_json = fallback
                                except Exception:
                                    pass
                        except Exception:
                            pass
                        # 若解析/回退后有 JSON，则渲染 Markdown；否则兜底为 JSON 文本或提示
                        if result_markdown is None:
                            if result_json is not None and isinstance(result_json, dict):
                                try:
                                    if markdown_from_ai_json is not None:
                                        result_markdown = markdown_from_ai_json(result_json, title='课堂行为分析')
                                    else:
                                        result_markdown = json.dumps(result_json, ensure_ascii=False, indent=2)
                                except Exception:
                                    result_markdown = json.dumps(result_json, ensure_ascii=False, indent=2)
                            else:
                                result_markdown = "本次分析基于结构化结果已生成可视化，详见图片与 JSON。"
                else:
                    # 统一回退文案：明确非 AI 结果并给出诊断指引
                    notice = "### 回退：AI 不可用\n\n已使用本地规则估算（非 AI 结果）。请在浏览器打开 /flask/ai/status 检查 ready/has_sdk/has_key_env/has_key_keyring，再配置 ZHIPU_API_KEY 或安装依赖。"
                    result_markdown = f"{notice}\n\n{rb_text or ''}"
            except Exception as e:
                result_markdown = (rb_text or "") + f"\n\n[AI 错误] {e}"
        else:
            # 统一回退文案：明确非 AI 结果并给出诊断指引
            notice = "### 回退：AI 不可用\n\n已使用本地规则估算（非 AI 结果）。请在浏览器打开 /flask/ai/status 检查 ready/has_sdk/has_key_env/has_key_keyring，再配置 ZHIPU_API_KEY 或安装依赖。"
            result_markdown = f"{notice}\n\n{rb_text or ''}"

        # 可选：将 AI JSON 与 PNG 保存到本地文件（便于后续复用/审计）
        saved_analysis_json_path = None
        saved_analysis_png_path = None
        saved_reference_json_path = None
        if save_json_out and (result_json is not None and isinstance(result_json, dict)):
            try:
                # 基于行为 JSON 路径或图片路径确定输出位置
                base_dir = None
                stem = None
                if behavior_json_path and os.path.exists(behavior_json_path):
                    base_dir = os.path.dirname(os.path.abspath(behavior_json_path))
                    stem = os.path.splitext(os.path.basename(behavior_json_path))[0].replace('_behavior', '')
                elif img_path and os.path.exists(img_path):
                    base_dir = os.path.dirname(os.path.abspath(img_path))
                    stem = os.path.splitext(os.path.basename(img_path))[0]
                if out_dir_req:
                    base_dir = os.path.abspath(out_dir_req)
                if not base_dir:
                    base_dir = os.path.abspath('./runs/analysis')
                os.makedirs(base_dir, exist_ok=True)
                if not stem:
                    stem = f"analysis_{uuid.uuid4().hex}"
                # 输出文件名可被 out_stem_req 覆盖（支持带 .json 的完整名或不带后缀的 stem）
                if out_stem_req:
                    custom_json_name = out_stem_req if str(out_stem_req).lower().endswith('.json') else f"{out_stem_req}.json"
                    json_path = os.path.join(base_dir, custom_json_name)
                    png_stem = custom_json_name[:-5] if custom_json_name.lower().endswith('.json') else custom_json_name
                else:
                    json_path = os.path.join(base_dir, f"{stem}_analysis.json")
                    png_stem = f"{stem}"
                # 写入 JSON
                saved_analysis_json_path = json_path
                with open(saved_analysis_json_path, 'w', encoding='utf-8') as f:
                    f.write(json.dumps(result_json, ensure_ascii=False, indent=2))
                # 生成 PNG（存放在同目录）
                if render_report_image:
                    saved_analysis_png_path = os.path.join(base_dir, f"{png_stem}_summary.png")
                    try:
                        render_report_image(result_json, saved_analysis_png_path, title=title_req)
                    except Exception:
                        saved_analysis_png_path = None
                # 保存参考 JSON（模式、提示词、输入等）
                if save_reference:
                    try:
                        import time as _time
                        ref_path = os.path.join(base_dir, f"{png_stem}_reference.json")
                        ref_payload = {
                            'mode': mode_name or 'unknown',
                            'behavior_json_path': os.path.abspath(behavior_json_path) if behavior_json_path else None,
                            'analysis_json_path': os.path.abspath(saved_analysis_json_path) if saved_analysis_json_path else None,
                            'counts_input': counts,
                            'prompt': last_prompt_text,
                            'timestamp': _time.strftime('%Y-%m-%d %H:%M:%S')
                        }
                        with open(ref_path, 'w', encoding='utf-8') as rf:
                            rf.write(json.dumps(ref_payload, ensure_ascii=False, indent=2))
                        saved_reference_json_path = ref_path
                    except Exception:
                        saved_reference_json_path = None
                # 若尚未提供对外 URL，则复制一份到 ./files 提供访问
                if (result_image_url is None) and saved_analysis_png_path and os.path.exists(saved_analysis_png_path):
                    try:
                        os.makedirs('./files', exist_ok=True)
                        copy_name = f"analysis_{uuid.uuid4().hex}.png"
                        copy_path = os.path.join('./files', copy_name)
                        shutil.copyfile(saved_analysis_png_path, copy_path)
                        result_image_url = f"http://localhost:{self.port}/files/{copy_name}"
                    except Exception:
                        pass
            except Exception:
                saved_analysis_json_path = None
                saved_analysis_png_path = None
                saved_reference_json_path = None

        return jsonify({
            'status': 200,
            'message': '分析完成',
            'counts': counts,
            'detections': boxes,
            'image_size': list(img_size) if img_size else None,
            'analysis_markdown': result_markdown,
            'analysis_json': result_json,
            'analysis_image_url': result_image_url,
            'saved_analysis_json_path': saved_analysis_json_path,
            'saved_analysis_png_path': saved_analysis_png_path,
            'saved_reference_json_path': saved_reference_json_path,
        })

    def dualDetect(self):
        """双模型检测：行为检测 + 人头计数。

        入参 JSON：
        {
        "inputImg": "./some.jpg",
        "behavior_weight": "./weights/best_student.pt",
        "counts_weight": "./weights/best_per_counts.pt",
        "conf": 0.25,
        "imgsz": 640,
        "save_json": false,
        "out_dir": "runs/dual_detect"
        }
    返回：merged JSON。若 save_json=true，仅写入 *_behavior.json（其中 counts 已含 head 人数）。
        """
        data = request.get_json(force=True, silent=True) or {}
        img_path = self._localize_image_path(data.get('inputImg'))
        behavior_weight = data.get('behavior_weight') or './weights/best_student.pt'
        counts_weight = data.get('counts_weight') or './weights/best_per_counts.pt'
        conf = float(data.get('conf', 0.25))
        imgsz = int(data.get('imgsz', 640))
        save_json = bool(data.get('save_json', False))
        out_dir = data.get('out_dir') or 'runs/dual_detect'
        backend = (data.get('backend') or '').lower().strip()

        if not img_path:
            return jsonify({"status": 400, "message": "缺少 inputImg"})
        try:
            # 如果显式要求 onnxruntime 或权重为 .onnx，则用通用 Detector 路径，避免依赖 torch
            use_onnx_for_behavior = behavior_weight.lower().endswith('.onnx') or backend == 'onnxruntime'
            use_onnx_for_counts = counts_weight.lower().endswith('.onnx') or backend == 'onnxruntime'

            if (not use_onnx_for_behavior and not use_onnx_for_counts) and YOLO is not None:
                # 纯 Ultralytics 路径，沿用原有实现
                merged = run_dual_on_image(img_path, behavior_weight, counts_weight, conf=conf, imgsz=imgsz)
            else:
                # 使用通用 Detector 分别跑两个模型，并合并结果
                b_backend = 'onnxruntime' if use_onnx_for_behavior else 'ultralytics'
                c_backend = 'onnxruntime' if use_onnx_for_counts else 'ultralytics'
                b_det = Detector(weights_path=behavior_weight, kind='student', backend=b_backend)
                c_det = Detector(weights_path=counts_weight, kind='student', backend=c_backend)
                b_res = b_det.predict_image(img_path, conf=conf, save_vis_path=None)
                c_res = c_det.predict_image(img_path, conf=conf, save_vis_path=None)

                # 尺寸
                W, H = 0, 0
                if b_res and b_res.image_size:
                    W, H = int(b_res.image_size[0] or 0), int(b_res.image_size[1] or 0)

                # boxes map 与 counts
                boxes_map: Dict[str, List[Dict[str, Any]]] = {}
                counts_map: Dict[str, int] = {}
                for d in b_res.detections:
                    label = str(d.get('label', '')).strip() or 'object'
                    boxes_map.setdefault(label, []).append({
                        'bbox_xyxy': d.get('bbox'),
                        'confidence': d.get('score'),
                    })
                    counts_map[label] = counts_map.get(label, 0) + 1

                head_count = len(c_res.detections or [])
                merged = {
                    'image': str(Path(img_path).resolve()),
                    'size': {'width': W, 'height': H},
                    'detections': [
                        {
                            'label': str(d.get('label')),
                            'bbox_xyxy': d.get('bbox'),
                            'confidence': d.get('score'),
                        } for d in b_res.detections
                    ],
                    'objects': [
                        {
                            'label': str(d.get('label')),
                            'bbox_xyxy': d.get('bbox'),
                            'confidence': d.get('score'),
                        } for d in b_res.detections
                    ],
                    'boxes': boxes_map,
                    # 仅行为类别计数，去除 head，避免重复；顶层提供唯一的 head
                    'counts': {**counts_map},
                    'head': head_count,
                    '人数': head_count,
                    'backend': 'mixed' if b_backend != c_backend else b_backend,
                    'provenance': {
                        'head_source': 'counts_model'
                    },
                    'models': {
                        'behavior': behavior_weight,
                        'counts': counts_weight,
                    }
                }
        except Exception as e:
            return jsonify({"status": 400, "message": f"检测失败: {e}"})

        saved_paths = None
        if save_json:
            try:
                p = Path(img_path)
                outp = Path(out_dir)
                outp.mkdir(parents=True, exist_ok=True)
                stem = p.stem
                behavior_json = {
                    'image': merged.get('image'),
                    'size': merged.get('size'),
                    # 仅保存行为计数；人数在顶层 head/人数 字段体现
                    'counts': merged.get('counts', {}),
                    'boxes': merged.get('boxes', {}),
                    'objects': merged.get('objects') or merged.get('detections', []),
                    'head': merged.get('head'),
                    '人数': merged.get('人数'),
                }
                b_path = outp / f"{stem}_behavior.json"
                b_path.write_text(json.dumps(behavior_json, ensure_ascii=False, indent=2), encoding='utf-8')
                saved_paths = { 'behavior_json': str(b_path) }
            except Exception:
                saved_paths = None

        resp = { "status": 200, "message": "OK", **merged }
        if saved_paths:
            resp['saved_paths'] = saved_paths
        return jsonify(resp)

    def predictVideo(self):
        """视频流处理接口"""
        self.data.clear()
        self.data.update({
            "username": request.args.get('username'), "weight": request.args.get('weight'),
            "conf": request.args.get('conf'), "startTime": request.args.get('startTime'),
            "inputVideo": request.args.get('inputVideo'),
            "kind": request.args.get('kind')
        })
        self.download(self.data["inputVideo"], self.paths['download'])
        cap = cv2.VideoCapture(self.paths['download'])
        if not cap.isOpened():
            raise ValueError("无法打开视频文件")
        fps = int(cap.get(cv2.CAP_PROP_FPS))
        print(fps)

        # 视频写入器
        video_writer = cv2.VideoWriter(
            self.paths['video_output'],
            cv2.VideoWriter_fourcc(*'XVID'),
            fps,
            (640, 480)
        )
        model = YOLO(f'./weights/{self.data["weight"]}') if YOLO is not None else None

        def generate():
            try:
                while cap.isOpened():
                    ret, frame = cap.read()
                    if not ret:
                        break
                    frame = cv2.resize(frame, (640, 480))
                    if model is not None:
                        results = model.predict(source=frame, conf=float(self.data['conf'] or 0.25), show=False)
                        processed_frame = results[0].plot()
                    else:
                        processed_frame = frame
                    video_writer.write(processed_frame)
                    _, jpeg = cv2.imencode('.jpg', processed_frame)
                    yield b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n'
            finally:
                self.cleanup_resources(cap, video_writer)
                self.socketio.emit('message', {'data': '处理完成，正在保存！'})
                for progress in self.convert_avi_to_mp4(self.paths['video_output']):
                    self.socketio.emit('progress', {'data': progress})
                uploadedUrl = self.upload(self.paths['output'])
                self.data['outVideo'] = uploadedUrl
                # 记录上报到 Spring：支持环境变量配置与 /api 回退
                try:
                    base_url = os.environ.get('SPRING_BASE_URL', 'http://localhost:9999').rstrip('/')
                    primary_path = os.environ.get('SPRING_VIDEORECORDS_PATH', '/videoRecords')
                    alt_path = '/api/videoRecords' if primary_path != '/api/videoRecords' else '/videoRecords'
                    candidates = [f"{base_url}{primary_path}", f"{base_url}{alt_path}"]
                    payload = json.dumps(self.data, ensure_ascii=False)
                    last_status = None
                    for url in candidates:
                        try:
                            last_status = self.save_data(payload, url)
                        except Exception:
                            last_status = None
                        if last_status == 200:
                            break
                except Exception as _e:
                    print(f"上报 videoRecords 时发生错误: {_e}")
                self.cleanup_files([self.paths['download'], self.paths['output'], self.paths['video_output']])

        return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

    def predictCamera(self):
        """摄像头视频流处理接口"""
        self.data.clear()
        self.data.update({
            "username": request.args.get('username'), "weight": request.args.get('weight'),
            "kind": request.args.get('kind'),
            "conf": request.args.get('conf'), "startTime": request.args.get('startTime')
        })
        self.socketio.emit('message', {'data': '正在加载，请稍等！'})
        model = YOLO(f'./weights/{self.data["weight"]}') if YOLO is not None else None
        cap = cv2.VideoCapture(0)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        video_writer = cv2.VideoWriter(self.paths['camera_output'], cv2.VideoWriter_fourcc(*'XVID'), 20, (640, 480))
        self.recording = True

        def generate():
            try:
                while self.recording:
                    ret, frame = cap.read()
                    if not ret:
                        break
                    if model is not None:
                        results = model.predict(source=frame, imgsz=640, conf=float(self.data['conf'] or 0.25), show=False)
                        processed_frame = results[0].plot()
                    else:
                        processed_frame = frame
                    if self.recording and video_writer:
                        video_writer.write(processed_frame)
                    _, jpeg = cv2.imencode('.jpg', processed_frame)
                    yield b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n'
            finally:
                self.cleanup_resources(cap, video_writer)
                self.socketio.emit('message', {'data': '处理完成，正在保存！'})
                for progress in self.convert_avi_to_mp4(self.paths['camera_output']):
                    self.socketio.emit('progress', {'data': progress})
                uploadedUrl = self.upload(self.paths['output'])
                self.data["outVideo"] = uploadedUrl
                print(self.data)
                # 记录上报到 Spring：支持环境变量配置与 /api 回退
                try:
                    base_url = os.environ.get('SPRING_BASE_URL', 'http://localhost:9999').rstrip('/')
                    primary_path = os.environ.get('SPRING_CAMERARECORDS_PATH', '/cameraRecords')
                    alt_path = '/api/cameraRecords' if primary_path != '/api/cameraRecords' else '/cameraRecords'
                    candidates = [f"{base_url}{primary_path}", f"{base_url}{alt_path}"]
                    payload = json.dumps(self.data, ensure_ascii=False)
                    last_status = None
                    for url in candidates:
                        try:
                            last_status = self.save_data(payload, url)
                        except Exception:
                            last_status = None
                        if last_status == 200:
                            break
                except Exception as _e:
                    print(f"上报 cameraRecords 时发生错误: {_e}")
                self.cleanup_files([self.paths['download'], self.paths['output'], self.paths['camera_output']])

        return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

    def stopCamera(self):
        """停止摄像头预测"""
        self.recording = False
        return json.dumps({"status": 200, "message": "预测成功", "code": 0})

    def save_data(self, data, path):
        """将结果数据上传到服务器"""
        headers = {'Content-Type': 'application/json'}
        try:
            print(f"Attempting to POST img record to: {path}")
            # 打印 payload 大致信息（避免打印过大）
            try:
                _preview = data if isinstance(data, str) and len(data) < 1000 else (data[:1000] + '...') if isinstance(data, str) else str(data)
                print(f"Payload preview: {_preview}")
            except Exception:
                pass
            response = requests.post(path, data=data, headers=headers)
            if response.status_code == 200:
                print("记录上传成功！")
            else:
                # 打印并保存响应 body 以便排查 404/401 等错误原因
                resp_text = ''
                try:
                    resp_text = response.text
                except Exception:
                    resp_text = '<无法读取 response.text>'
                print(f"记录上传失败，状态码: {response.status_code}, body: {resp_text}")
                # 保存调试信息到本地，方便离线排查/重试
                try:
                    os.makedirs('./runs/debug_img_records', exist_ok=True)
                    import time as _time
                    fname = f"./runs/debug_img_records/{int(_time.time())}_{uuid.uuid4().hex}.json"
                    try:
                        parsed_payload = json.loads(data) if isinstance(data, str) else data
                    except Exception:
                        parsed_payload = data
                    dbg = {
                        'url': path,
                        'status_code': response.status_code,
                        'response_text': resp_text,
                        'payload': parsed_payload,
                    }
                    with open(fname, 'w', encoding='utf-8') as _f:
                        _f.write(json.dumps(dbg, ensure_ascii=False, indent=2))
                    print(f"失败记录已保存到: {fname}")
                except Exception as _e:
                    print(f"保存失败记录时出错: {_e}")
            # 返回状态码给调用方判断是否需要重试
            try:
                return response.status_code
            except Exception:
                return None
        except requests.RequestException as e:
            print(f"上传记录时发生错误: {str(e)}")
            # 保存 payload 以便后续重试
            try:
                os.makedirs('./runs/debug_img_records', exist_ok=True)
                import time as _time
                fname = f"./runs/debug_img_records/{int(_time.time())}_{uuid.uuid4().hex}_error.json"
                try:
                    parsed_payload = json.loads(data) if isinstance(data, str) else data
                except Exception:
                    parsed_payload = data
                dbg = {'url': path, 'error': str(e), 'payload': parsed_payload}
                with open(fname, 'w', encoding='utf-8') as _f:
                    _f.write(json.dumps(dbg, ensure_ascii=False, indent=2))
                print(f"错误记录已保存到: {fname}")
            except Exception as _e:
                print(f"保存错误记录时出错: {_e}")
            return None

    def convert_avi_to_mp4(self, temp_output):
        """使用 FFmpeg 将 AVI 格式转换为 MP4 格式，并显示转换进度。"""
        ffmpeg_command = f"ffmpeg -i {temp_output} -vcodec libx264 {self.paths['output']} -y"
        process = subprocess.Popen(ffmpeg_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True)
        total_duration = self.get_video_duration(temp_output)

        for line in process.stderr:
            if "time=" in line:
                try:
                    time_str = line.split("time=")[1].split(" ")[0]
                    h, m, s = map(float, time_str.split(":"))
                    processed_time = h * 3600 + m * 60 + s
                    if total_duration > 0:
                        progress = (processed_time / total_duration) * 100
                        yield progress
                except Exception as e:
                    print(f"解析进度时发生错误: {e}")

        process.wait()
        yield 100

    def get_video_duration(self, path):
        """获取视频总时长（秒）"""
        try:
            cap = cv2.VideoCapture(path)
            if not cap.isOpened():
                return 0
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            cap.release()
            return total_frames / fps if fps > 0 else 0
        except Exception:
            return 0

    def get_file_names(self, directory):
        """获取指定文件夹中的所有文件名"""
        try:
            return [file for file in os.listdir(directory) if os.path.isfile(os.path.join(directory, file))]
        except Exception as e:
            print(f"发生错误: {e}")
            return []

    def upload(self, out_path):
        """上传处理后的图片或视频文件到远程服务器"""
        upload_url = "http://localhost:9999/files/upload"
        try:
            with open(out_path, 'rb') as file:
                files = {'file': (os.path.basename(out_path), file)}
                response = requests.post(upload_url, files=files)
                if response.status_code == 200:
                    print("文件上传成功！")
                    return response.json()['data']
                else:
                    print("文件上传失败！")
        except Exception as e:
            print(f"上传文件时发生错误: {str(e)}")

    def download(self, url, save_path):
        """下载文件并保存到指定路径"""
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        try:
            with requests.get(url, stream=True) as response:
                response.raise_for_status()
                with open(save_path, 'wb') as file:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            file.write(chunk)
            print(f"文件已成功下载并保存到 {save_path}")
        except requests.RequestException as e:
            print(f"下载失败: {e}")

    def cleanup_files(self, file_paths):
        """清理文件"""
        for path in file_paths:
            if os.path.exists(path):
                os.remove(path)

    def cleanup_resources(self, cap, video_writer):
        """释放资源"""
        if cap.isOpened():
            cap.release()
        if video_writer is not None:
            video_writer.release()
        cv2.destroyAllWindows()


# 启动应用
if __name__ == '__main__':
    try:
        env_port = int(os.environ.get('FLASK_PORT') or os.environ.get('PORT') or 5000)
    except Exception:
        env_port = 5000
    video_app = VideoProcessingApp(port=env_port)
    video_app.run()
