"""Flask service entrypoint for student behavior detection + AI analysis."""

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from flask import Flask, request
from flask_socketio import SocketIO, emit


# Add project root (the folder that contains 'screen_capture') to sys.path to reuse project modules
try:
    here = Path(__file__).resolve()
    for up in here.parents:
        if (up / "screen_capture").exists():
            if str(up) not in sys.path:
                sys.path.append(str(up))
            break
except Exception:
    pass

from config import AppConfig
from handlers import CommonHandlersMixin, DetectionHandlersMixin, StreamHandlersMixin


class VideoProcessingApp(CommonHandlersMixin, DetectionHandlersMixin, StreamHandlersMixin):
    def __init__(self, host: str = None, port: int = None, config: AppConfig = None) -> None:
        self.config = config or AppConfig.from_env()
        self.app = Flask(__name__)
        self.socketio = SocketIO(self.app, cors_allowed_origins="*")
        self.host = host or self.config.flask_host
        self.port = port or self.config.flask_port
        self.data: Dict[str, Any] = {}
        self.camera_flags: Dict[str, bool] = {}

        video_dir = Path(self.config.runs_dir) / "video"
        video_dir.mkdir(parents=True, exist_ok=True)
        self.paths = {
            "download": str(video_dir / "download.mp4"),
            "output": str(video_dir / "output.mp4"),
            "camera_output": str(video_dir / "camera_output.avi"),
            "video_output": str(video_dir / "video_output.avi"),
        }
        self.recording = False

        self._install_response_wrapper()
        self.setup_routes()

    def setup_routes(self) -> None:
        self.app.add_url_rule("/file_names", "file_names", self.file_names, methods=["GET"])
        self.app.add_url_rule("/predictImg", "predictImg", self.predictImg, methods=["POST"])
        self.app.add_url_rule("/analyze", "analyze", self.analyze, methods=["POST"])
        self.app.add_url_rule("/dualDetect", "dualDetect", self.dualDetect, methods=["POST"])
        self.app.add_url_rule("/ai/status", "ai_status", self.ai_status, methods=["GET"])
        self.app.add_url_rule("/flask/ai/status", "ai_status_alias", self.ai_status, methods=["GET"])

        # Common aliases so cURL can call /flask/* directly without frontend proxy
        self.app.add_url_rule("/flask/file_names", "file_names_wrapped", self.file_names_wrapped, methods=["GET"])
        self.app.add_url_rule("/flask/predictImg", "predictImg_alias", self.predictImg, methods=["POST"])
        self.app.add_url_rule("/predict", "predict_legacy", self.predict_legacy, methods=["POST"])
        self.app.add_url_rule("/flask/predict", "predict_legacy_alias", self.predict_legacy, methods=["POST"])
        self.app.add_url_rule("/flask/analyze", "analyze_alias", self.analyze, methods=["POST"])
        self.app.add_url_rule("/flask/dualDetect", "dualDetect_alias", self.dualDetect, methods=["POST"])
        self.app.add_url_rule("/flask/files/upload", "files_upload_alias", self.files_upload, methods=["POST"])
        self.app.add_url_rule("/flask/files/<path:filename>", "files_get_alias", self.files_get, methods=["GET"])
        self.app.add_url_rule("/predictVideo", "predictVideo", self.predictVideo)
        self.app.add_url_rule("/predictCamera", "predictCamera", self.predictCamera)
        self.app.add_url_rule("/stopCamera", "stopCamera", self.stopCamera, methods=["GET"])
        self.app.add_url_rule("/files/upload", "files_upload", self.files_upload, methods=["POST"])
        self.app.add_url_rule("/files/<path:filename>", "files_get", self.files_get, methods=["GET"])

        @self.socketio.on("connect")
        def handle_connect():
            print("WebSocket connected!")
            emit("message", {"data": "Connected to WebSocket server!"})

        @self.socketio.on("disconnect")
        def handle_disconnect():
            print("WebSocket disconnected!")

    def run(self) -> None:
        self.socketio.run(self.app, host=self.host, port=self.port, allow_unsafe_werkzeug=True)

    def _install_response_wrapper(self) -> None:
        @self.app.after_request
        def _wrap_json_response(response):
            if not response.mimetype or "application/json" not in response.mimetype:
                return response
            payload = response.get_json(silent=True)
            if payload is None:
                return response

            normalized = self._normalize_payload(payload, response.status_code)
            response.set_data(json.dumps(normalized, ensure_ascii=False))
            response.headers["Content-Type"] = "application/json; charset=utf-8"
            response.headers["X-Trace-Id"] = normalized.get("traceId", "")
            response.content_length = len(response.get_data())
            return response

    def _normalize_payload(self, payload: Any, status_code: int) -> Dict[str, Any]:
        if isinstance(payload, dict):
            required = {"code", "message", "data", "traceId", "timestamp"}
            if required.issubset(set(payload.keys())):
                if "msg" not in payload:
                    payload["msg"] = payload.get("message")
                return payload

        trace_id = request.headers.get("X-Trace-Id") or uuid.uuid4().hex
        success = status_code < 400
        code = 0 if success else 1
        message = "success" if success else "error"
        data: Any = payload

        if isinstance(payload, dict):
            payload_msg = payload.get("message") or payload.get("msg")
            if isinstance(payload_msg, str) and payload_msg.strip():
                message = payload_msg

            # For Flask-native payloads like {"status":200,"data":"..."},
            # keep top-level data as the actual business payload.
            if "status" in payload and "data" in payload:
                data = payload.get("data")

            payload_code = payload.get("code")
            if payload_code is not None:
                try:
                    parsed = int(payload_code)
                    code = 0 if parsed == 0 else parsed
                    success = parsed == 0
                except Exception:
                    pass

            payload_status = payload.get("status")
            if payload_status is not None:
                try:
                    parsed_status = int(payload_status)
                    if parsed_status >= 400:
                        success = False
                        if code == 0:
                            code = parsed_status
                    elif code != 0 and success:
                        code = 0
                except Exception:
                    pass

        if success and code != 0:
            code = 0
        if not success and code == 0:
            code = 1

        normalized: Dict[str, Any] = {
            "code": code,
            "message": message,
            "msg": message,
            "data": data,
            "traceId": trace_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if isinstance(payload, dict):
            for key, value in payload.items():
                if key not in normalized:
                    normalized[key] = value
        return normalized


if __name__ == "__main__":
    cfg = AppConfig.from_env()
    video_app = VideoProcessingApp(host=cfg.flask_host, port=cfg.flask_port, config=cfg)
    video_app.run()
