"""Flask service for student behavior detection + AI analysis (refactored)."""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
import shutil
from urllib.parse import urlparse, unquote

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
        self.base_dir = Path(__file__).resolve().parent
        self.files_dir = self.base_dir / 'files'
        self.data: Dict[str, Any] = {}
        self.paths = {
            'download': './runs/video/download.mp4',
            'output': './runs/video/output.mp4',
            'camera_output': './runs/video/camera_output.mp4',
            'video_output': './runs/video/video_output.mp4',
        }
        self.recording = False
        self.setup_routes()

    def _localize_image_path(self, path_or_url: str) -> str:
        """Normalize input image to a local path when possible."""
        if not path_or_url:
            return path_or_url
        if not isinstance(path_or_url, str):
            return path_or_url

        raw = path_or_url.strip()
        if not raw:
            return raw

        if os.path.exists(raw):
            return raw

        if raw.startswith('/files/') or raw.startswith('/flask/files/'):
            local_name = os.path.basename(raw)
            local_file = self.files_dir / local_name
            if local_file.exists():
                return str(local_file.resolve())
            return raw

        if raw.lower().startswith(('http://', 'https://')):
            try:
                parsed = urlparse(raw)
                host = (parsed.hostname or '').lower()
                path = unquote(parsed.path or '')
                if host in {'localhost', '127.0.0.1', '0.0.0.0'} and (path.startswith('/files/') or path.startswith('/flask/files/')):
                    local_name = os.path.basename(path)
                    local_file = self.files_dir / local_name
                    if local_file.exists():
                        return str(local_file.resolve())
            except Exception:
                pass

            tmp_dir = self.base_dir / 'runs' / 'tmp'
            tmp_dir.mkdir(parents=True, exist_ok=True)
            suffix = os.path.splitext(urlparse(raw).path)[1] or '.jpg'
            local_path = str((tmp_dir / f'input_{uuid.uuid4().hex}{suffix}').resolve())
            try:
                self.download(raw, local_path)
                return local_path
            except Exception:
                return raw
        return raw

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
        # Wrapped variants to match older frontend expecting { code, data }
        self.app.add_url_rule('/flask/file_names', 'file_names_wrapped', self.file_names_wrapped, methods=['GET'])
        self.app.add_url_rule('/flask/predictImg', 'predictImg_alias', self.predictImg, methods=['POST'])
        # Legacy endpoints compatible with old UI
        self.app.add_url_rule('/predict', 'predict_legacy', self.predict_legacy, methods=['POST'])
        self.app.add_url_rule('/flask/predict', 'predict_legacy_alias', self.predict_legacy, methods=['POST'])
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
            emit('message', {'data': {'type': 'system', 'text': 'Connected to WebSocket server!'}})

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
            return jsonify({'status': 400, 'message': '缂哄皯鏂囦欢鍙傛暟 file'})
        self.files_dir.mkdir(parents=True, exist_ok=True)
        orig = secure_filename(f.filename or 'upload.bin')
        name = f"{uuid.uuid4().hex}_{orig}"
        save_path = self.files_dir / name
        f.save(str(save_path))
        url = f"http://localhost:{self.port}/files/{name}"
        # 鍓嶇鍙鍙?data 瀛楁
        return jsonify({'data': url})

    def files_get(self, filename: str):
        return send_from_directory(str(self.files_dir), filename, as_attachment=False)

    def publish_local_file(self, file_path: str) -> Optional[str]:
        """Copy local result file into ./files and return a Flask-served URL."""
        try:
            if not file_path or not os.path.exists(file_path):
                return None
            self.files_dir.mkdir(parents=True, exist_ok=True)
            src_name = os.path.basename(file_path)
            name = f"{uuid.uuid4().hex}_{src_name}"
            target = self.files_dir / name
            shutil.copyfile(file_path, str(target))
            return f"http://localhost:{self.port}/files/{name}"
        except Exception:
            return None

    def _create_video_writer(self, output_path: str, fps: float, frame_size: tuple[int, int]):
        """Create an MP4 writer, preferring browser-compatible codecs."""
        use_fps = float(fps) if fps and fps > 1 else 25.0
        for codec in ('avc1', 'H264', 'mp4v'):
            writer = cv2.VideoWriter(output_path, cv2.VideoWriter_fourcc(*codec), use_fps, frame_size)
            if writer.isOpened():
                print(f"VideoWriter initialized with codec: {codec}")
                return writer
            writer.release()
        raise ValueError(f"Failed to initialize video writer for {output_path}")

    # -------- Endpoints --------
    def file_names(self):
        weight_items = [{'value': name, 'label': name} for name in self.get_file_names('./weights')]
        return json.dumps({'weight_items': weight_items}, ensure_ascii=False)

    def file_names_wrapped(self):
        """Return { code, data } to be compatible with older frontend expectations."""
        try:
            raw = self.file_names()  # JSON string
            return jsonify({'code': 0, 'data': raw})
        except Exception as e:
            return jsonify({'code': 500, 'msg': str(e)})

    def _infer_kind(self, weight: Optional[str]) -> Optional[str]:
        try:
            if not weight:
                return None
            name = str(Path(weight).name).lower()
            # 浼樺厛鍙栦笅鍒掔嚎/杩炲瓧绗?鐐逛箣鍓嶇殑鍓嶇紑
            for sep in ['_', '-', '.']:
                if sep in name:
                    name = name.split(sep)[0]
                    break
            # 甯歌鍒悕褰掍竴
            aliases = {
                'maize': 'corn',
                'paddy': 'rice',
            }
            base = aliases.get(name, name)
            # 閽堝璁℃暟/澶撮儴妫€娴嬫ā鍨嬬殑鎺ㄦ柇
            full = str(Path(weight).name).lower()
            if any(tok in full for tok in ['head', 'count', 'counts']):
                return 'head'
            return base
        except Exception:
            return None

    def predictImg(self):
        data = request.get_json(force=True, silent=True) or {}
        self.data.clear()
        self.data.update({
            'username': data.get('username', ''),
            'weight': data.get('weight', ''),
            'conf': data.get('conf', 0.5),
            'startTime': data.get('startTime', ''),
            'inputImg': data.get('inputImg', ''),
            'kind': data.get('kind', ''),
        })
        img_path = self._localize_image_path(self.data['inputImg'])
        weight = self.data['weight']
        kind = self.data['kind'] or self._infer_kind(weight) or 'student'
        self.data['kind'] = kind
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
    # 寮傛/鍚屾淇濆瓨璇嗗埆璁板綍鍒?Spring锛堜究浜庡墠绔巻鍙叉煡鐪嬶級
        try:
            try:
                labels = [str(o.get('label') or '') for o in out.get('objects', [])]
                confidences = [o.get('confidence') for o in out.get('objects', [])]
            except Exception:
                labels = []
                confidences = []
            # fallback: 鑻ユ病鏈?objects锛屽垯鐢?counts 鐨勯敭浣滀负 labels
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
                'kind': self.data.get('kind'),
                'allTime': out.get('allTime'),
                'conf': self.data.get('conf'),
                'startTime': self.data.get('startTime'),
                # 鍚庣鏈熸湜 label/confidence 涓?JSON 瀛楃涓?
                'label': json.dumps(labels, ensure_ascii=False),
                'confidence': json.dumps(confidences, ensure_ascii=False),
            }
            # 鍙戦€佸埌 Spring 鐨?imgRecords 鎺ュ彛锛氫紭鍏堝皾璇曠幆澧冮厤缃殑璺緞锛堥粯璁?/imgRecords锛夛紝澶辫触鍐嶈瘯澶囬€夎矾寰?
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
                # 鎴愬姛鍗冲仠姝㈤噸璇?
                if last_status == 200:
                    break
            # 鍦ㄨ繑鍥炰綋涓檮鍔犱竴娆＄畝鐭殑涓婁紶缁撴灉锛屼究浜庡墠绔?璋冪敤鏂硅皟璇?
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

    def predict_legacy(self):
        """Wrap predictImg output into { code, data } for legacy UI."""
        try:
            resp = self.predictImg()
            body = None
            try:
                body = resp.get_json()  # type: ignore[attr-defined]
            except Exception:
                try:
                    body = json.loads(getattr(resp, 'data', b'').decode('utf-8'))
                except Exception:
                    body = None
            if body is None:
                return jsonify({'code': 500, 'msg': 'empty response'})
            code = 0 if int(body.get('status', 200)) == 200 else 500
            return jsonify({'code': code, 'data': json.dumps(body, ensure_ascii=False)})
        except Exception as e:
            return jsonify({'code': 500, 'msg': str(e)})

    def _build_behavior_payload_from_dual(self, merged: Dict[str, Any], classroom_id: str = 'Class-Default') -> Dict[str, Any]:
        """Build BehaviorRecord payload from dualDetect output."""
        counts = merged.get('counts') or {}
        if not isinstance(counts, dict):
            counts = {}
        student_count = int(merged.get('head') or merged.get('人数') or 0)
        if student_count <= 0:
            try:
                student_count = sum(int(v) for v in counts.values() if isinstance(v, (int, float)))
            except Exception:
                student_count = 0

        def _sum_by_keywords(keys: List[str]) -> int:
            total = 0
            for k, v in counts.items():
                ks = str(k).lower()
                if any(x in ks for x in keys):
                    try:
                        total += int(v)
                    except Exception:
                        pass
            return total

        low_focus = _sum_by_keywords(['low', 'phone', 'sleep', 'down', 'head_down', 'using_phone'])
        active = _sum_by_keywords(['raise', 'interact', 'write', 'active', 'upright', 'reading'])
        if student_count > 0:
            focus_score = max(0, min(100, int((1 - (low_focus / student_count)) * 100)))
            activity_score = max(0, min(100, int((active / student_count) * 100)))
        else:
            focus_score = 0
            activity_score = 0

        if activity_score >= 60:
            interaction_level = 'high'
        elif activity_score >= 30:
            interaction_level = 'medium'
        else:
            interaction_level = 'low'

        metrics = {
            'source': 'dualDetect',
            'student_count': student_count,
            'focus_score': focus_score,
            'activity_score': activity_score,
            'low_focus_count': low_focus,
            'active_count': active,
            'counts': counts,
            'head': student_count,
        }
        risks = []
        if student_count > 0 and low_focus / student_count >= 0.4:
            risks.append({'type': 'focus', 'level': 'medium', 'detail': 'High low-focus ratio detected'})

        suggestions = []
        if risks:
            suggestions.append('Review seating and engagement strategy for low-focus students.')
        else:
            suggestions.append('Current classroom behavior appears stable.')

        return {
            'classroomId': classroom_id or 'Class-Default',
            'studentCount': student_count,
            'focusScore': focus_score,
            'activityScore': activity_score,
            'interactionLevel': interaction_level,
            'metricsJson': json.dumps(metrics, ensure_ascii=False),
            'spatialJson': json.dumps({'boxes': merged.get('boxes') or {}}, ensure_ascii=False),
            'risksJson': json.dumps(risks, ensure_ascii=False),
            'suggestionsJson': json.dumps(suggestions, ensure_ascii=False),
        }

    def _save_behavior_payload_to_db(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """POST payload to Spring /behavior/save and return detailed status."""
        base_url = os.environ.get('SPRING_BASE_URL', 'http://localhost:9999').rstrip('/')
        save_url = f"{base_url}/behavior/save"
        try:
            response = requests.post(save_url, json=payload, timeout=8)
            if response.status_code != 200:
                detail = ''
                try:
                    detail = response.text or ''
                except Exception:
                    detail = ''
                message = f'Behavior DB save failed (HTTP {response.status_code})'
                if 'student_behavior_records' in detail and "doesn't exist" in detail:
                    message = 'Behavior DB table missing: student_behavior_records. Import yolo_studentBehavior_detection_web/db/mydb.sql first.'
                return {
                    'success': False,
                    'status_code': response.status_code,
                    'error': message,
                    'detail': detail[:500] if detail else None,
                    'url': save_url,
                }
            return {'success': True, 'status_code': response.status_code, 'url': save_url}
        except Exception as e:
            return {
                'success': False,
                'status_code': None,
                'error': f'Behavior DB save failed: {e}',
                'url': save_url,
            }

    def analyze(self):
        """涓€浣撳寲锛氭娴?+ AI 鍒嗘瀽銆?

        鍏ュ弬 JSON锛?
        {
        "inputImg": "./some.jpg",          # 鍙€夛紱鑻ョ己鐪佷笖鎻愪緵 counts锛屽垯浠呮枃鏈垎鏋?
        "weight": "yolov8n-student.pt",    # 鍙€夛紱鎻愪緵鍥剧墖鏃堕渶瑕?
        "kind": "student",                 # 鍙€?
        "conf": 0.5,                        # 鍙€?
        "json_only": true,                  # 鍙€夛紱榛樿 true锛屾湡鏈涗弗鏍?JSON 杈撳嚭
        "prompt": "...",                   # 鍙€夛紱瑕嗙洊榛樿鎻愮ず
        "counts": { ... }                   # 鍙€夛紱鑻ユ彁渚涳紝灏嗕笌妫€娴嬫眹鎬诲悎骞?
        }
        """
        data = request.get_json(force=True, silent=True) or {}
        img_path = self._localize_image_path(data.get('inputImg'))
        weight = data.get('weight')
        kind = data.get('kind', 'student')
        conf = float(data.get('conf', 0.5))
        json_only = bool(data.get('json_only', True))
        two_stage = bool(data.get('two_stage', True))  # 榛樿 true锛氬厛鍙栦弗鏍?JSON锛屽啀鏈湴鐢熸垚 Markdown
        strict_pipeline = bool(data.get('strict_pipeline', True))  # 榛樿寮哄埗鍙屾ā鍨嬪悗鍐?AI 鍖?
        custom_prompt = data.get('prompt')
        counts_in = data.get('counts') or {}
        behavior_json_path = data.get('behavior_json_path')
        behavior_json_raw = data.get('behavior_json')
        analysis_json_path = data.get('analysis_json_path')  # 鏂板锛氳嫢宸插瓨鍦ˋI鍖栧悗鐨凧SON锛屽彲鐩存帴浣跨敤
        save_reference = bool(data.get('save_reference', True))  # 棰濆淇濆瓨鍙傝€僇SON涓庢彁绀鸿瘝
        save_json_out = bool(data.get('save_json_out', False))
        out_dir_req = data.get('out_dir') or None
        out_stem_req = data.get('out_stem') or None
        title_req = data.get('title') or '课堂行为分析'
        aiize_mode = False
        backend = (data.get('backend') or '').lower().strip()
        if not backend and weight:
            backend = 'onnxruntime' if str(weight).lower().endswith('.onnx') else 'ultralytics'

        # 璁板綍鏈妯″紡涓庣敤浜庢ā鍨嬬殑鏈€缁堟彁绀烘枃鏈紝渚夸簬淇濆瓨鍙傝€?
        mode_name = None
        last_prompt_text = None

        # 鑻ヤ紶鍏?analysis_json_path锛岀洿鎺ヤ娇鐢?AI 鍖栧悗鐨?JSON 杩涜娓叉煋涓庡彲瑙嗗寲
        if analysis_json_path:
            # 鏀寔涓夌鏉ユ簮锛?
            # 1) 鏈湴鏂囦欢缁濆/鐩稿璺緞
            # 2) HTTP/HTTPS URL锛堜緥濡傚厛閫氳繃 /flask/files/upload 涓婁紶杩斿洖鐨?URL锛?
            # 3) /files/ 鍓嶇紑鐨勭浉瀵硅矾寰勶紙鑷姩琛?http://localhost:{port}锛?
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
                        return jsonify({'status': 400, 'message': f'涓嬭浇 analysis_json_path 澶辫触: {e}'})
                else:
                    with open(path_or_url, 'r', encoding='utf-8') as f:
                        result_json = json.load(f)
            except Exception as e:
                return jsonify({'status': 400, 'message': f'璇诲彇 analysis_json_path 澶辫触: {e}'})
            mode_name = 'reuse'
            # 瀵屽寲涓庡彲瑙嗗寲
            try:
                if enrich_consistency and isinstance(result_json, dict):
                    result_json = enrich_consistency(result_json)
            except Exception:
                pass
            # 鑻ヤ粛缂哄皯 observations锛屽仛涓€娆″厹搴曞～鍏?
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
                                    bullets.append(f'浣庡ご鐜囩害 {mt.get("head_down_rate")}%' )
                            except Exception:
                                pass
                            try:
                                if isinstance(mt.get('phone_usage_rate'), int):
                                    bullets.append(f'鐪嬫墜鏈虹害 {mt.get("phone_usage_rate")}%' )
                            except Exception:
                                pass
                            try:
                                if isinstance(mt.get('sleeping_rate'), int):
                                    bullets.append(f'鎵撶瀸鐫＄害 {mt.get("sleeping_rate")}%' )
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
                                    row_lab = ['front', 'middle', 'back'][maxi[0]]
                                    col_lab = ['left', 'center', 'right'][maxi[1]]
                                    bullets.append(f'{row_lab}-{col_lab} crowd level: {maxv}')
                            if bullets:
                                js['observations'] = bullets[:6]
                    except Exception:
                        pass
                    return js
                if isinstance(result_json, dict):
                    result_json = _ensure_observations(result_json)
            except Exception:
                pass
            # 鐢熸垚鍙鍖?PNG
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
            # 娓叉煋 Markdown锛堜粎灞曠ず鍏抽敭瑙傚療瑕佺偣涓庡眬闄愭€э級
            result_markdown = None
            try:
                if markdown_from_ai_json is not None and isinstance(result_json, dict):
                    result_markdown = markdown_from_ai_json(result_json, title='课堂行为分析')
            except Exception:
                pass
            # 淇濆瓨鍙傝€?JSON锛堝熀浜庡鐢級
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
                'message': '鍒嗘瀽瀹屾垚(澶嶇敤宸睞I鍖朖SON)',
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

        # 鑻ヤ紶鍏?behavior_json_path/behavior_json锛屽垯璧扳€淎I 鍖栧凡鏈?JSON 鍐嶅垎鏋愨€濈殑娴佺▼
        behavior_obj = None
        if behavior_json_path:
            try:
                with open(behavior_json_path, 'r', encoding='utf-8') as f:
                    behavior_obj = json.load(f)
                    aiize_mode = True
            except Exception as e:
                return jsonify({'status': 400, 'message': f'璇诲彇 behavior_json_path 澶辫触: {e}'})
        elif behavior_json_raw is not None:
            try:
                behavior_obj = behavior_json_raw if isinstance(behavior_json_raw, dict) else json.loads(str(behavior_json_raw))
                aiize_mode = True
            except Exception as e:
                return jsonify({'status': 400, 'message': f'瑙ｆ瀽 behavior_json 澶辫触: {e}'})

        # 寮哄埗娴佺▼锛氭湭鎻愪緵琛屼负 JSON 涓旀湭鏄惧紡缁?counts 鏃讹紝鎷掔粷鐩存帴鍥剧墖鍒嗘瀽锛堥伩鍏嶄笌瀹為檯鍦烘櫙鏃犲叧鐨勮緭鍑猴級
        if strict_pipeline and (not aiize_mode) and (not (isinstance(counts_in, dict) and counts_in)):
            return jsonify({
                'status': 400,
                'message': 'strict pipeline: call /flask/dualDetect first to create *_behavior.json, then call /flask/analyze with behavior_json_path. To allow direct image analysis, set strict_pipeline=false.'
            })

        # 鍏堟娴嬶紙濡傛彁渚涘浘鐗囷紱鑻?aiize_mode 鍒欒烦杩囨娴嬶級
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

        # 鑻ュ浜?AI 鍖栫幇鏈?JSON 妯″紡锛坆ehavior_json_path/behavior_json锛夛紝鍒欏皢鍏朵腑鐨?counts/boxes/size 娉ㄥ叆锛?
        # 浠ヤ究鍚庣画瀵屽寲/鍏滃簳锛堝惁鍒欎細鍑虹幇 metrics=0銆乸er_class 涓虹┖绛夐棶棰橈級銆?
        if aiize_mode and isinstance(behavior_obj, dict):
            try:
                # 鍚堝苟 counts锛堜繚鎸佸師閿悕锛屽悗缁細缁熶竴 normalize锛?
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
                # 瑙ｆ瀽鍥剧墖灏哄
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
                # 鏋勯€?boxes 鍒楄〃锛堢敤浜?spatial_summary锛?
                boxes2: List[Dict[str, Any]] = []
                # 浼樺厛 objects 鍒楄〃
                if isinstance(behavior_obj.get('objects'), list):
                    for it in behavior_obj['objects']:
                        try:
                            lbl = (it.get('label') or 'object')
                            bb = it.get('bbox') or it.get('bbox_xyxy') or it.get('xyxy') or it.get('xywh')
                            if isinstance(bb, (list, tuple)) and len(bb) == 4:
                                boxes2.append({'label': lbl, 'bbox': [float(bb[0]), float(bb[1]), float(bb[2]), float(bb[3])]})
                        except Exception:
                            pass
                # 鍏舵 boxes 鏄犲皠 {label: [ {...}, ... ]}
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

        # 瑙勫垯鎽樿
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
                    # 鑻ヤ负 AI 鍖栨ā寮忥細鐩存帴瀵逛紶鍏ョ殑 behavior JSON 鍋氫弗鏍?JSON 瑙勬暣锛屽啀鏈湴娓叉煋
                    if aiize_mode:
                        try:
                            # 鏋勫缓涓ユ牸 JSON 鎻愮ず璇?+ 娉ㄥ叆鍘熷 JSON锛堝墠缃?AI 瑙掕壊涓嶫SON浼樺厛澹版槑锛?
                            head_prompt = build_json_only_prompt(custom_prompt) if build_json_only_prompt else (custom_prompt or '')
                            preface = (
                                "You are a classroom behavior analysis assistant.\n"
                                "- Use only the provided JSON evidence.\n"
                                "- Output must be a strict JSON object with schema_version=1.1.\n"
                                "- Keep observations concrete (4-8 items) and limitations explicit (2-8 items).\n"
                                "- If image and JSON conflict, prefer JSON and explain conflict in limitations.\n"
                            )
                            head_prompt = preface + "\n\n" + head_prompt
                            import json as _json
                            head_prompt += "\n浠ヤ笅涓哄師濮?JSON锛歕n" + _json.dumps(behavior_obj, ensure_ascii=False) + "\n"
                            last_prompt_text = head_prompt
                            mode_name = 'aiize'
                        except Exception:
                            head_prompt = custom_prompt or ''

                        # 鍙戦€佸埌 AI锛岃幏鍙栦弗鏍?JSON
                        messages = [{"role": "user", "content": [{"type": "text", "text": head_prompt}]}]
                        ai_res = client.chat(messages, response_format={"type": "json_object"})
                        content = ai_res.get('content') or ''
                        try:
                            result_json = json.loads(content)
                        except Exception:
                            result_json = None

                        # 涓板瘜涓庝竴鑷存€у鐞嗭細纭繚 head/人数銆佷竴鑷寸殑 provenance
                        try:
                            if result_json is not None and isinstance(result_json, dict):
                                # 鑻ョ己灏?head锛屽垯灏濊瘯浠庡師 JSON 鎺ㄦ柇
                                if 'head' not in result_json:
                                    try:
                                        # 浼樺厛椤跺眰 head锛涘叾娆?counts 姹囨€?
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
                                # 人数鍒悕
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

                        # 涓€鑷存€т笌鍙鍖?
                        if result_json is not None and isinstance(result_json, dict):
                            try:
                                if enrich_consistency:
                                    result_json = enrich_consistency(result_json)
                            except Exception:
                                pass
                            # 鐢熸垚鍙鍖?PNG
                            try:
                                if render_report_image:
                                    os.makedirs('./files', exist_ok=True)
                                    img_name = f"analysis_{uuid.uuid4().hex}.png"
                                    out_path = os.path.join('./files', img_name)
                                    render_report_image(result_json, out_path, title='课堂行为分析')
                                    result_image_url = f"http://localhost:{self.port}/files/{img_name}"
                            except Exception:
                                result_image_url = None

                        # 娓叉煋 Markdown锛堣嫢鍙锛?
                        if result_json is not None and markdown_from_ai_json is not None:
                            # 浣跨敤鏈湴妯℃澘娓叉煋绠€娲佹爣棰?
                            result_markdown = markdown_from_ai_json(result_json, title='课堂行为分析')
                        else:
                            # 涓ユ牸妯″紡锛氫笉鐩存帴閲囩敤 AI 鍘熷鏂囨湰锛涘厛灏濊瘯浠庢枃鏈腑鎻愬彇 JSON锛屽惁鍒欑敓鎴愭湰鍦板洖閫€ JSON
                            result_markdown = None
                            # 灏濊瘯浠庢枃鏈腑鎻愬彇 JSON 骞跺彲瑙嗗寲
                            try:
                                parsed = None
                                import re as _re
                                m = _re.search(r"```json\s*(\{[\s\S]*?\})\s*```", content, _re.IGNORECASE)
                                if not m:
                                    m = _re.search(r"```\s*(\{[\s\S]*?\})\s*```", content, _re.IGNORECASE)
                                if m:
                                    parsed = json.loads(m.group(1))
                                else:
                                    # 鏈€澶у钩琛¤姳鎷彿鍧?
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
                                    # 娓叉煋 Markdown锛堣嫢妯℃澘鍙敤锛?
                                    try:
                                        if markdown_from_ai_json is not None:
                                            result_markdown = markdown_from_ai_json(parsed, title='课堂行为分析')
                                    except Exception:
                                        pass
                                # 鑻ヤ粛鏃?JSON锛岀敓鎴愬熀浜?counts 鐨勫洖閫€鍙鍖?
                                if (result_image_url is None) and render_report_image:
                                    try:
                                        sp = spatial_summary(boxes, img_size) if spatial_summary else {}
                                        # 浼扮畻 head
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
                                        # 娉ㄥ叆 head/人数 骞惰繘琛屽瘜鍖栵紝灏介噺濉厖 observations/limitations
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
                            # 鑻ユ湭鑳戒娇鐢ㄦā鏉挎覆鏌擄紝鍒欎互 JSON 鏂囨湰浣滀负 Markdown 鍏滃簳锛岄伩鍏嶅紩鍏ヤ笌鍦烘櫙鏃犲叧鐨勬ā鍨嬫枃鏈?
                            if result_markdown is None:
                                if result_json is not None and isinstance(result_json, dict):
                                    try:
                                        if markdown_from_ai_json is not None:
                                            result_markdown = markdown_from_ai_json(result_json, title='课堂行为分析')
                                        else:
                                            result_markdown = json.dumps(result_json, ensure_ascii=False, indent=2)
                                    except Exception:
                                        result_markdown = json.dumps(result_json, ensure_ascii=False, indent=2)

                    # 涓ら樁娈碉紙鍏?JSON锛屽啀鎶ュ憡锛夋垨涓ユ牸 JSON 妯″紡锛堥潪 aiize 妯″紡锛?
                    elif two_stage or json_only:
                        # 1) 鏋勫缓涓ユ牸 JSON 鎻愮ず璇嶏紝骞舵敞鍏?counts銆乭ead 浼拌涓庣┖闂村垎甯?
                        if build_json_only_prompt:
                            head = build_json_only_prompt(custom_prompt)
                        else:
                            head = (custom_prompt or '')
                        # 鍓嶇疆 AI 瑙掕壊涓?JSON 浼樺厛澹版槑
                        try:
                            preface = (
                                "You are a classroom behavior analysis assistant.\n"
                                "- Use only the provided JSON evidence.\n"
                                "- Output must be a strict JSON object with schema_version=1.1.\n"
                                "- Keep observations concrete (4-8 items) and limitations explicit (2-8 items).\n"
                                "- If image and JSON conflict, prefer JSON and explain conflict in limitations.\n"
                            )
                            head = preface + "\n\n" + head
                        except Exception:
                            pass
                        # 娉ㄥ叆 counts JSON
                        try:
                            import json as _json
                            if isinstance(counts, dict) and counts:
                                head += "\n\n浠ヤ笅涓烘娴?缁熻 JSON锛歕n" + _json.dumps(counts, ensure_ascii=False) + "\n"
                        except Exception:
                            pass
                        # 娉ㄥ叆 head 浼拌
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
                                head += f"\n瀛︾敓鎬绘暟 (head): {head_est2}\n"
                        except Exception:
                            pass

                        # 涓ユ牸 JSON锛氱粺涓€璧版枃鏈亰澶╁苟瑕佹眰 JSON 瀵硅薄杈撳嚭
                        messages = [{"role": "user", "content": [{"type": "text", "text": head}]}]
                        ai_res = client.chat(messages, response_format={"type": "json_object"})
                        last_prompt_text = head
                        mode_name = 'two_stage'

                        content = ai_res.get('content') or ''
                        try:
                            result_json = json.loads(content)
                        except Exception:
                            result_json = None

                        # 涓板瘜/琛ュ叏 JSON锛氬熀浜?counts/head 璁＄畻缂哄け鎸囨爣涓?per_class
                        try:
                            if result_json is not None and isinstance(result_json, dict):
                                # 褰掍竴鍖栬緭鍏ヨ鏁?
                                c_norm = normalize_counts(counts) if normalize_counts else (counts or {})
                                # 浼扮畻 head
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
                                # 榛樿缃俊搴?灞€闄愭€?
                                if 'confidence' not in result_json:
                                    result_json['confidence'] = 'medium'
                                if 'limitations' not in result_json or not isinstance(result_json.get('limitations'), list):
                                    result_json['limitations'] = ['Result is inferred from detections and spatial distribution, uncertainty may exist due to occlusion or resolution limits.']
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

                        # 3) 涓€鑷存€у寮轰笌鍙鍖?
                        if result_json is not None and isinstance(result_json, dict):
                            try:
                                if enrich_consistency:
                                    result_json = enrich_consistency(result_json)
                            except Exception:
                                pass
                            # 鍏滃簳琛ラ綈 observations
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
                                                    bullets.append(f'浣庡ご鐜囩害 {mt.get("head_down_rate")}%' )
                                            except Exception:
                                                pass
                                            try:
                                                if isinstance(mt.get('phone_usage_rate'), int):
                                                    bullets.append(f'鐪嬫墜鏈虹害 {mt.get("phone_usage_rate")}%' )
                                            except Exception:
                                                pass
                                            try:
                                                if isinstance(mt.get('sleeping_rate'), int):
                                                    bullets.append(f'鎵撶瀸鐫＄害 {mt.get("sleeping_rate")}%' )
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
                                                    row_lab = ['front', 'middle', 'back'][maxi[0]]
                                                    col_lab = ['left', 'center', 'right'][maxi[1]]
                                                    bullets.append(f'{row_lab}-{col_lab} crowd level: {maxv}')
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

                        # 4) 鏈湴妯℃澘娓叉煋 Markdown锛堣嫢鍙敤锛夛紱涓ユ牸妯″紡涓嬩笉鐩存帴杩斿洖 AI 鏂囨湰
                        if result_json is not None and markdown_from_ai_json is not None:
                            result_markdown = markdown_from_ai_json(result_json, title='课堂行为分析')
                        elif result_json is not None:
                            # 閫€鍥炰负 JSON 鏂囨湰
                            try:
                                result_markdown = json.dumps(result_json, ensure_ascii=False, indent=2)
                            except Exception:
                                result_markdown = str(result_json)
                        else:
                            # 浠嶆湭鎷垮埌 JSON锛岀淮鎸佺┖锛屽悗缁厹搴曢€昏緫浼氬～鍏?
                            result_markdown = None
                    else:
                        # 鐩存帴鏋勫缓鎶ュ憡鍨嬫彁绀鸿瘝骞惰皟鐢紙淇濇寔鍏煎锛?
                        if build_prompt:
                            head = build_prompt(counts, custom_prompt)
                        else:
                            head = (custom_prompt or '')
                        # 娉ㄥ叆绌洪棿鍒嗗竷
                        if spatial_summary and boxes:
                            try:
                                sp = spatial_summary(boxes, img_size)
                                import json as _json
                                head += "\n\n浠ヤ笅涓烘娴嬫鐨勭┖闂村垎甯冿紙3x3 鍖哄煙璁℃暟锛塉SON锛歕n" + _json.dumps(sp, ensure_ascii=False) + "\n"
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
                        # 涓ユ牸妯″紡锛氫笉鐩存帴杩斿洖 AI 鏂囨湰锛岀瓑寰呭悗缁В鏋?鍥為€€
                        result_markdown = None
                        # 鍚屾牱灏濊瘯鍙鍖栵紙鎻愬彇 JSON 鎴栫敓鎴愬洖閫€锛?
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
                                    # 浼扮畻 head
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
                                    # 娉ㄥ叆 head/人数 骞惰繘琛屽瘜鍖栵紝灏介噺濉厖 observations/limitations
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
                        # 鑻ヨВ鏋?鍥為€€鍚庢湁 JSON锛屽垯娓叉煋 Markdown锛涘惁鍒欏厹搴曚负 JSON 鏂囨湰鎴栨彁绀?
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
                                result_markdown = "Structured analysis JSON generated. Please check analysis image or JSON output."
                else:
                    # Unified fallback note when AI is unavailable.
                    notice = (
                        "### Fallback: AI unavailable\n\n"
                        "Rule-based estimation was used (non-AI result). "
                        "Open /flask/ai/status to check ready/has_sdk/has_key_env/has_key_keyring."
                    )
                    result_markdown = f"{notice}\n\n{rb_text or ''}"
            except Exception as e:
                result_markdown = (rb_text or "") + f"\n\n[AI 閿欒] {e}"
        else:
            # Unified fallback note when AI is unavailable.
            notice = (
                "### Fallback: AI unavailable\n\n"
                "Rule-based estimation was used (non-AI result). "
                "Open /flask/ai/status to check ready/has_sdk/has_key_env/has_key_keyring."
            )
            result_markdown = f"{notice}\n\n{rb_text or ''}"

        # 鍙€夛細灏?AI JSON 涓?PNG 淇濆瓨鍒版湰鍦版枃浠讹紙渚夸簬鍚庣画澶嶇敤/瀹¤锛?
        saved_analysis_json_path = None
        saved_analysis_png_path = None
        saved_reference_json_path = None
        if save_json_out and (result_json is not None and isinstance(result_json, dict)):
            try:
                # 鍩轰簬琛屼负 JSON 璺緞鎴栧浘鐗囪矾寰勭‘瀹氳緭鍑轰綅缃?
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
                # 杈撳嚭鏂囦欢鍚嶅彲琚?out_stem_req 瑕嗙洊锛堟敮鎸佸甫 .json 鐨勫畬鏁村悕鎴栦笉甯﹀悗缂€鐨?stem锛?
                if out_stem_req:
                    custom_json_name = out_stem_req if str(out_stem_req).lower().endswith('.json') else f"{out_stem_req}.json"
                    json_path = os.path.join(base_dir, custom_json_name)
                    png_stem = custom_json_name[:-5] if custom_json_name.lower().endswith('.json') else custom_json_name
                else:
                    json_path = os.path.join(base_dir, f"{stem}_analysis.json")
                    png_stem = f"{stem}"
                # 鍐欏叆 JSON
                saved_analysis_json_path = json_path
                with open(saved_analysis_json_path, 'w', encoding='utf-8') as f:
                    f.write(json.dumps(result_json, ensure_ascii=False, indent=2))
                # 鐢熸垚 PNG锛堝瓨鏀惧湪鍚岀洰褰曪級
                if render_report_image:
                    saved_analysis_png_path = os.path.join(base_dir, f"{png_stem}_summary.png")
                    try:
                        render_report_image(result_json, saved_analysis_png_path, title=title_req)
                    except Exception:
                        saved_analysis_png_path = None
                # 淇濆瓨鍙傝€?JSON锛堟ā寮忋€佹彁绀鸿瘝銆佽緭鍏ョ瓑锛?
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
                # 鑻ュ皻鏈彁渚涘澶?URL锛屽垯澶嶅埗涓€浠藉埌 ./files 鎻愪緵璁块棶
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

        db_save = None
        try:
            if result_json and isinstance(result_json, dict):
                metrics = result_json.get('metrics') or {}
                spatial = result_json.get('spatial') or {}
                risks = result_json.get('risks') or []
                suggestions = result_json.get('suggestions') or []

                focus_score = 0
                activity_score = 0
                try:
                    focus_score = int(metrics.get('focus_score', 0))
                    activity_score = int(metrics.get('activity_score', 0))
                except Exception:
                    pass

                student_count = 0
                try:
                    student_count = int(
                        result_json.get('head')
                        or result_json.get('person_count')
                        or result_json.get('人数')
                        or metrics.get('student_count')
                        or 0
                    )
                except Exception:
                    pass

                payload = {
                    'classroomId': str(data.get('classroomId') or 'Class-Default'),
                    'studentCount': student_count,
                    'focusScore': focus_score,
                    'activityScore': activity_score,
                    'interactionLevel': str(metrics.get('interaction_level', 'medium')),
                    'metricsJson': json.dumps(metrics, ensure_ascii=False),
                    'spatialJson': json.dumps(spatial, ensure_ascii=False),
                    'risksJson': json.dumps(risks, ensure_ascii=False),
                    'suggestionsJson': json.dumps(suggestions, ensure_ascii=False),
                }
                db_save = self._save_behavior_payload_to_db(payload)
        except Exception as e:
            db_save = {'success': False, 'error': f'Behavior DB save failed: {e}'}
            print(f"Failed to save behavior record to DB: {e}")

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
            'db_save': db_save,
        })

    def dualDetect(self):
        """鍙屾ā鍨嬫娴嬶細琛屼负妫€娴?+ 浜哄ご璁℃暟銆?

        鍏ュ弬 JSON锛?
        {
        "inputImg": "./some.jpg",
        "behavior_weight": "./weights/best_student.pt",
        "counts_weight": "./weights/best_per_counts.pt",
        "conf": 0.25,
        "imgsz": 640,
        "save_json": false,
        "out_dir": "runs/dual_detect"
        }
    杩斿洖锛歮erged JSON銆傝嫢 save_json=true锛屼粎鍐欏叆 *_behavior.json锛堝叾涓?counts 宸插惈 head 人数锛夈€?
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
            return jsonify({"status": 400, "message": "缂哄皯 inputImg"})
        try:
            # 濡傛灉鏄惧紡瑕佹眰 onnxruntime 鎴栨潈閲嶄负 .onnx锛屽垯鐢ㄩ€氱敤 Detector 璺緞锛岄伩鍏嶄緷璧?torch
            use_onnx_for_behavior = behavior_weight.lower().endswith('.onnx') or backend == 'onnxruntime'
            use_onnx_for_counts = counts_weight.lower().endswith('.onnx') or backend == 'onnxruntime'

            if (not use_onnx_for_behavior and not use_onnx_for_counts) and YOLO is not None:
                # 绾?Ultralytics 璺緞锛屾部鐢ㄥ師鏈夊疄鐜?
                merged = run_dual_on_image(img_path, behavior_weight, counts_weight, conf=conf, imgsz=imgsz)
            else:
                # 浣跨敤閫氱敤 Detector 鍒嗗埆璺戜袱涓ā鍨嬶紝骞跺悎骞剁粨鏋?
                b_backend = 'onnxruntime' if use_onnx_for_behavior else 'ultralytics'
                c_backend = 'onnxruntime' if use_onnx_for_counts else 'ultralytics'
                b_det = Detector(weights_path=behavior_weight, kind='student', backend=b_backend)
                c_det = Detector(weights_path=counts_weight, kind='student', backend=c_backend)
                b_res = b_det.predict_image(img_path, conf=conf, save_vis_path=None)
                c_res = c_det.predict_image(img_path, conf=conf, save_vis_path=None)

                # 灏哄
                W, H = 0, 0
                if b_res and b_res.image_size:
                    W, H = int(b_res.image_size[0] or 0), int(b_res.image_size[1] or 0)

                # boxes map 涓?counts
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
                    # 浠呰涓虹被鍒鏁帮紝鍘婚櫎 head锛岄伩鍏嶉噸澶嶏紱椤跺眰鎻愪緵鍞竴鐨?head
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
            return jsonify({"status": 400, "message": f"妫€娴嬪け璐? {e}"})


        # Generate boxed image preview for frontend (result.outImg / result.out_img).
        boxed_image_path = None
        boxed_image_url = None
        try:
            p = Path(img_path)
            outp = Path(out_dir)
            outp.mkdir(parents=True, exist_ok=True)
            boxed_path = outp / f"{p.stem}_boxed.jpg"

            src = cv2.imread(str(p))
            if src is not None:
                det_list = merged.get('objects') or merged.get('detections') or []
                # Use deterministic per-label colors so different classes are easy to distinguish.
                palette = [
                    (56, 56, 255),    # red
                    (255, 159, 56),   # orange
                    (255, 112, 31),   # deep orange
                    (255, 178, 29),   # amber
                    (207, 210, 49),   # olive yellow
                    (72, 249, 10),    # green
                    (146, 204, 23),   # lime
                    (61, 219, 134),   # mint
                    (26, 147, 52),    # dark green
                    (0, 212, 187),    # cyan
                    (44, 153, 168),   # teal
                    (0, 194, 255),    # sky
                    (52, 69, 147),    # navy
                    (100, 115, 255),  # indigo
                    (0, 24, 236),     # blue
                    (132, 56, 255),   # purple
                    (82, 0, 133),     # deep purple
                    (203, 56, 255),   # magenta
                    (255, 149, 200),  # pink
                    (255, 55, 199),   # hot pink
                ]
                label_color_map = {}
                if isinstance(det_list, list):
                    for det in det_list:
                        if not isinstance(det, dict):
                            continue
                        bbox = det.get('bbox_xyxy') or det.get('bbox')
                        if not isinstance(bbox, (list, tuple)) or len(bbox) < 4:
                            continue
                        try:
                            x1, y1, x2, y2 = [int(float(v)) for v in bbox[:4]]
                        except Exception:
                            continue
                        x1 = max(0, min(src.shape[1] - 1, x1))
                        x2 = max(0, min(src.shape[1] - 1, x2))
                        y1 = max(0, min(src.shape[0] - 1, y1))
                        y2 = max(0, min(src.shape[0] - 1, y2))
                        if x2 <= x1 or y2 <= y1:
                            continue
                        label = str(det.get('label') or 'object')
                        score = det.get('confidence', det.get('score'))
                        text = f"{label} {float(score):.2f}" if isinstance(score, (int, float)) else label
                        if label not in label_color_map:
                            color_idx = (sum(ord(ch) for ch in label) + len(label) * 17) % len(palette)
                            label_color_map[label] = palette[color_idx]
                        color = label_color_map[label]
                        cv2.rectangle(src, (x1, y1), (x2, y2), color, 2)
                        cv2.putText(src, text, (x1, max(20, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
                cv2.imwrite(str(boxed_path), src)
                boxed_image_path = str(boxed_path)
                boxed_image_url = self.publish_local_file(str(boxed_path))
        except Exception:
            boxed_image_path = None
            boxed_image_url = None

        if boxed_image_url:
            merged['outImg'] = boxed_image_url
            merged['out_img'] = boxed_image_url
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
                    # 浠呬繚瀛樿涓鸿鏁帮紱人数鍦ㄩ《灞?head/人数 瀛楁浣撶幇
                    'counts': merged.get('counts', {}),
                    'boxes': merged.get('boxes', {}),
                    'objects': merged.get('objects') or merged.get('detections', []),
                    'head': merged.get('head'),
                    '人数': merged.get('人数'),
                }
                b_path = outp / f"{stem}_behavior.json"
                b_path.write_text(json.dumps(behavior_json, ensure_ascii=False, indent=2), encoding='utf-8')
                saved_paths = { 'behavior_json': str(b_path) }
                if boxed_image_path:
                    saved_paths['boxed_image'] = boxed_image_path
            except Exception:
                saved_paths = None

        resp = { "status": 200, "message": "OK", **merged }
        if saved_paths:
            resp['saved_paths'] = saved_paths
        db_save = None
        try:
            classroom_id = str(data.get('classroomId') or 'Class-Default')
            payload = self._build_behavior_payload_from_dual(merged, classroom_id=classroom_id)
            db_save = self._save_behavior_payload_to_db(payload)
        except Exception as e:
            db_save = {'success': False, 'error': f'Behavior DB save failed: {e}'}
        resp['db_save'] = db_save
        return jsonify(resp)

    def predictVideo(self):
        """Video stream processing endpoint."""
        self.data.clear()
        self.data.update({
            "username": request.args.get('username'), "weight": request.args.get('weight'),
            "conf": request.args.get('conf'), "startTime": request.args.get('startTime'),
            "inputVideo": request.args.get('inputVideo'),
            "kind": request.args.get('kind'),
            "taskId": request.args.get('taskId') or uuid.uuid4().hex
        })
        # 鑻ユ湭鏄惧紡浼?kind锛屽垯鏍规嵁鏉冮噸鍚嶆帹鏂?
        if not self.data.get('kind'):
            self.data['kind'] = self._infer_kind(self.data.get('weight')) or 'student'
        self.download(self.data["inputVideo"], self.paths['download'])
        cap = cv2.VideoCapture(self.paths['download'])
        if not cap.isOpened():
            raise ValueError("鏃犳硶鎵撳紑瑙嗛鏂囦欢")
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        fps_raw = cap.get(cv2.CAP_PROP_FPS)
        fps = int(fps_raw) if fps_raw and fps_raw > 1 else 25
        print(fps)

        # 瑙嗛鍐欏叆鍣?
        video_writer = self._create_video_writer(self.paths['video_output'], fps, (640, 480))
        model = YOLO(f'./weights/{self.data["weight"]}') if YOLO is not None else None

        def generate():
            frame_idx = 0
            try:
                while cap.isOpened():
                    ret, frame = cap.read()
                    if not ret:
                        break
                    frame_idx += 1
                    frame = cv2.resize(frame, (640, 480))
                    counts: Dict[str, int] = {}
                    avg_conf = 0.0
                    if model is not None:
                        results = model.predict(source=frame, conf=float(self.data['conf'] or 0.25), show=False)
                        r0 = results[0]
                        processed_frame = r0.plot()
                        try:
                            cls_list = []
                            conf_list = []
                            names = r0.names if isinstance(getattr(r0, 'names', None), dict) else {}
                            if getattr(r0, 'boxes', None) is not None:
                                if getattr(r0.boxes, 'cls', None) is not None:
                                    cls_list = r0.boxes.cls.tolist()
                                if getattr(r0.boxes, 'conf', None) is not None:
                                    conf_list = r0.boxes.conf.tolist()
                            for i, cid in enumerate(cls_list):
                                cid_int = int(cid)
                                lbl = names.get(cid_int, str(cid_int))
                                counts[lbl] = counts.get(lbl, 0) + 1
                                if i < len(conf_list):
                                    try:
                                        avg_conf += float(conf_list[i])
                                    except Exception:
                                        pass
                            if conf_list:
                                avg_conf = avg_conf / len(conf_list)
                        except Exception:
                            counts = {}
                            avg_conf = 0.0
                    else:
                        processed_frame = frame
                    if total_frames > 0 and frame_idx % 10 == 0:
                        reading_progress = min(95, int((frame_idx / max(1, total_frames)) * 95))
                        progress_payload = {'taskId': self.data.get('taskId'), 'progress': reading_progress}
                        self.socketio.emit('progress', {'data': progress_payload, **progress_payload})
                    if frame_idx % 6 == 0:
                        stats_payload = {
                            'taskId': self.data.get('taskId'),
                            'frame': frame_idx,
                            'total': int(sum(counts.values())),
                            'avgConfidence': round(avg_conf * 100, 2),
                            'counts': counts,
                        }
                        self.socketio.emit('stats', {'data': stats_payload, **stats_payload})
                    video_writer.write(processed_frame)
                    _, jpeg = cv2.imencode('.jpg', processed_frame)
                    yield b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n'
            finally:
                self.cleanup_resources(cap, video_writer)
                self.socketio.emit('message', {'data': {'taskId': self.data.get('taskId'), 'type': 'info', 'text': '处理完成，正在保存，请稍候'}})
                for progress in self.convert_avi_to_mp4(self.paths['video_output']):
                    try:
                        final_progress = 95 + int(float(progress) * 0.05)
                    except Exception:
                        final_progress = 100
                    progress_payload = {'taskId': self.data.get('taskId'), 'progress': min(100, max(95, final_progress))}
                    self.socketio.emit('progress', {'data': progress_payload, **progress_payload})
                upload_path = self.paths['output'] if os.path.exists(self.paths['output']) else self.paths['video_output']
                uploadedUrl = self.upload(upload_path)
                if not uploadedUrl:
                    uploadedUrl = self.publish_local_file(upload_path)
                self.data['outVideo'] = uploadedUrl or ''
                # 璁板綍涓婃姤鍒?Spring锛氭敮鎸佺幆澧冨彉閲忛厤缃笌 /api 鍥為€€
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
                    print(f"涓婃姤 videoRecords 鏃跺彂鐢熼敊璇? {_e}")
                self.socketio.emit('message', {'data': {'taskId': self.data.get('taskId'), 'type': 'success', 'text': '视频处理完成'}})
                self.cleanup_files([self.paths['download'], self.paths['output'], self.paths['video_output']])

        return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

    def predictCamera(self):
        """鎽勫儚澶磋棰戞祦澶勭悊鎺ュ彛"""
        self.data.clear()
        self.data.update({
            "username": request.args.get('username'), "weight": request.args.get('weight'),
            "kind": request.args.get('kind'),
            "conf": request.args.get('conf'), "startTime": request.args.get('startTime'),
            "taskId": request.args.get('taskId') or uuid.uuid4().hex
        })
        if not self.data.get('kind'):
            self.data['kind'] = self._infer_kind(self.data.get('weight')) or 'student'
        self.socketio.emit('message', {'data': {'taskId': self.data.get('taskId'), 'type': 'info', 'text': '处理中，请稍候'}})
        model = YOLO(f'./weights/{self.data["weight"]}') if YOLO is not None else None
        cap = cv2.VideoCapture(0)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        video_writer = self._create_video_writer(self.paths['camera_output'], 20, (640, 480))
        self.recording = True

        def generate():
            frame_idx = 0
            try:
                while self.recording:
                    ret, frame = cap.read()
                    if not ret:
                        break
                    frame_idx += 1
                    counts: Dict[str, int] = {}
                    avg_conf = 0.0
                    if model is not None:
                        results = model.predict(source=frame, imgsz=640, conf=float(self.data['conf'] or 0.25), show=False)
                        r0 = results[0]
                        processed_frame = r0.plot()
                        try:
                            cls_list = []
                            conf_list = []
                            names = r0.names if isinstance(getattr(r0, 'names', None), dict) else {}
                            if getattr(r0, 'boxes', None) is not None:
                                if getattr(r0.boxes, 'cls', None) is not None:
                                    cls_list = r0.boxes.cls.tolist()
                                if getattr(r0.boxes, 'conf', None) is not None:
                                    conf_list = r0.boxes.conf.tolist()
                            for i, cid in enumerate(cls_list):
                                cid_int = int(cid)
                                lbl = names.get(cid_int, str(cid_int))
                                counts[lbl] = counts.get(lbl, 0) + 1
                                if i < len(conf_list):
                                    try:
                                        avg_conf += float(conf_list[i])
                                    except Exception:
                                        pass
                            if conf_list:
                                avg_conf = avg_conf / len(conf_list)
                        except Exception:
                            counts = {}
                            avg_conf = 0.0
                    else:
                        processed_frame = frame
                    if frame_idx % 6 == 0:
                        stats_payload = {
                            'taskId': self.data.get('taskId'),
                            'frame': frame_idx,
                            'total': int(sum(counts.values())),
                            'avgConfidence': round(avg_conf * 100, 2),
                            'counts': counts,
                        }
                        self.socketio.emit('stats', {'data': stats_payload, **stats_payload})
                    if self.recording and video_writer:
                        video_writer.write(processed_frame)
                    _, jpeg = cv2.imencode('.jpg', processed_frame)
                    yield b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n'
            finally:
                self.cleanup_resources(cap, video_writer)
                self.socketio.emit('message', {'data': {'taskId': self.data.get('taskId'), 'type': 'info', 'text': '处理完成，正在保存，请稍候'}})
                for progress in self.convert_avi_to_mp4(self.paths['camera_output']):
                    try:
                        final_progress = 95 + int(float(progress) * 0.05)
                    except Exception:
                        final_progress = 100
                    progress_payload = {'taskId': self.data.get('taskId'), 'progress': min(100, max(95, final_progress))}
                    self.socketio.emit('progress', {'data': progress_payload, **progress_payload})
                upload_path = self.paths['output'] if os.path.exists(self.paths['output']) else self.paths['camera_output']
                uploadedUrl = self.upload(upload_path)
                if not uploadedUrl:
                    uploadedUrl = self.publish_local_file(upload_path)
                self.data["outVideo"] = uploadedUrl or ''
                print(self.data)
                # 璁板綍涓婃姤鍒?Spring锛氭敮鎸佺幆澧冨彉閲忛厤缃笌 /api 鍥為€€
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
                    print(f"涓婃姤 cameraRecords 鏃跺彂鐢熼敊璇? {_e}")
                self.socketio.emit('message', {'data': {'taskId': self.data.get('taskId'), 'type': 'success', 'text': '摄像检测完成'}})
                self.cleanup_files([self.paths['download'], self.paths['output'], self.paths['camera_output']])

        return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

    def stopCamera(self):
        """Stop camera processing."""
        self.recording = False
        return json.dumps({"status": 200, "message": "操作成功", "code": 0})

    def save_data(self, data, path):
        """Send recognition result data to backend service."""
        headers = {'Content-Type': 'application/json'}
        try:
            print(f"Attempting to POST img record to: {path}")
            # 鎵撳嵃 payload 澶ц嚧淇℃伅锛堥伩鍏嶆墦鍗拌繃澶э級
            try:
                _preview = data if isinstance(data, str) and len(data) < 1000 else (data[:1000] + '...') if isinstance(data, str) else str(data)
                print(f"Payload preview: {_preview}")
            except Exception:
                pass
            response = requests.post(path, data=data, headers=headers)
            if response.status_code == 200:
                print("record upload succeeded")
            else:
                # 鎵撳嵃骞朵繚瀛樺搷搴?body 浠ヤ究鎺掓煡 404/401 绛夐敊璇師鍥?
                resp_text = ''
                try:
                    resp_text = response.text
                except Exception:
                    resp_text = '<鏃犳硶璇诲彇 response.text>'
                print(f"璁板綍涓婁紶澶辫触锛岀姸鎬佺爜: {response.status_code}, body: {resp_text}")
                # 淇濆瓨璋冭瘯淇℃伅鍒版湰鍦帮紝鏂逛究绂荤嚎鎺掓煡/閲嶈瘯
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
                    print(f"澶辫触璁板綍宸蹭繚瀛樺埌: {fname}")
                except Exception as _e:
                    print(f"淇濆瓨澶辫触璁板綍鏃跺嚭閿? {_e}")
            # 杩斿洖鐘舵€佺爜缁欒皟鐢ㄦ柟鍒ゆ柇鏄惁闇€瑕侀噸璇?
            try:
                return response.status_code
            except Exception:
                return None
        except requests.RequestException as e:
            print(f"涓婁紶璁板綍鏃跺彂鐢熼敊璇? {str(e)}")
            # 淇濆瓨 payload 浠ヤ究鍚庣画閲嶈瘯
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
                print(f"閿欒璁板綍宸蹭繚瀛樺埌: {fname}")
            except Exception as _e:
                print(f"淇濆瓨閿欒璁板綍鏃跺嚭閿? {_e}")
            return None

    def convert_avi_to_mp4(self, temp_output):
        """Convert AVI to browser-friendly MP4 with FFmpeg."""
        out_path = self.paths['output']
        input_ext = str(Path(temp_output).suffix or '').lower()
        if input_ext == '.mp4':
            try:
                if os.path.exists(out_path):
                    os.remove(out_path)
            except Exception:
                pass
            if temp_output != out_path:
                try:
                    shutil.copyfile(temp_output, out_path)
                except Exception as e:
                    print(f"copy mp4 output failed: {e}")
            yield 100
            return

        ffmpeg_bin = shutil.which('ffmpeg')
        if not ffmpeg_bin:
            print("ffmpeg not found, skip mp4 conversion.")
            try:
                if os.path.exists(out_path):
                    os.remove(out_path)
            except Exception:
                pass
            yield 100
            return

        try:
            if os.path.exists(out_path):
                os.remove(out_path)
        except Exception:
            pass

        ffmpeg_command = [
            ffmpeg_bin,
            '-y',
            '-i',
            temp_output,
            '-c:v',
            'libx264',
            '-pix_fmt',
            'yuv420p',
            '-movflags',
            '+faststart',
            out_path,
        ]
        process = subprocess.Popen(
            ffmpeg_command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='ignore',
        )
        total_duration = self.get_video_duration(temp_output)

        if process.stderr is not None:
            for line in process.stderr:
                if "time=" in line:
                    try:
                        time_str = line.split("time=")[1].split(" ")[0]
                        h, m, s = map(float, time_str.split(":"))
                        processed_time = h * 3600 + m * 60 + s
                        if total_duration > 0:
                            progress = (processed_time / total_duration) * 100
                            yield max(0, min(100, progress))
                    except Exception as e:
                        print(f"Failed to parse ffmpeg progress: {e}")

        return_code = process.wait()
        if return_code != 0:
            print(f"ffmpeg convert failed with code: {return_code}")
        yield 100

    def get_video_duration(self, path):
        """鑾峰彇瑙嗛鎬绘椂闀匡紙绉掞級"""
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
        """鑾峰彇鎸囧畾鏂囦欢澶逛腑鐨勬墍鏈夋枃浠跺悕"""
        try:
            return [file for file in os.listdir(directory) if os.path.isfile(os.path.join(directory, file))]
        except Exception as e:
            print(f"鍙戠敓閿欒: {e}")
            return []

    def upload(self, out_path):
        """Upload processed file to Spring file service and return URL."""
        upload_url = "http://localhost:9999/files/upload"
        try:
            with open(out_path, 'rb') as file:
                files = {'file': (os.path.basename(out_path), file)}
                response = requests.post(upload_url, files=files)
                if response.status_code == 200:
                    print("upload succeeded")
                    return response.json().get('data')
                print("upload failed")
        except Exception as e:
            print(f"upload error: {str(e)}")

    def download(self, url, save_path):
        """涓嬭浇鏂囦欢骞朵繚瀛樺埌鎸囧畾璺緞"""
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        try:
            with requests.get(url, stream=True) as response:
                response.raise_for_status()
                with open(save_path, 'wb') as file:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            file.write(chunk)
            print(f"鏂囦欢宸叉垚鍔熶笅杞藉苟淇濆瓨鍒?{save_path}")
        except requests.RequestException as e:
            print(f"涓嬭浇澶辫触: {e}")

    def cleanup_files(self, file_paths):
        """娓呯悊鏂囦欢"""
        for path in file_paths:
            if os.path.exists(path):
                os.remove(path)

    def cleanup_resources(self, cap, video_writer):
        """閲婃斁璧勬簮"""
        if cap.isOpened():
            cap.release()
        if video_writer is not None:
            video_writer.release()
        cv2.destroyAllWindows()


# 鍚姩搴旂敤
if __name__ == '__main__':
    try:
        env_port = int(os.environ.get('FLASK_PORT') or os.environ.get('PORT') or 5000)
    except Exception:
        env_port = 5000
    video_app = VideoProcessingApp(port=env_port)
    video_app.run()



