"""Common HTTP handlers and helpers."""

import os
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from flask import jsonify, request, send_from_directory
from werkzeug.utils import secure_filename

try:
    from screen_capture.ai_client import AIClient  # type: ignore
except Exception:
    AIClient = None  # type: ignore


class CommonHandlersMixin:
    def _localize_image_path(self, path_or_url: str) -> str:
        if not path_or_url:
            return path_or_url
        if isinstance(path_or_url, str) and path_or_url.lower().startswith(("http://", "https://")):
            tmp_dir = Path(self.config.runs_dir) / "tmp"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            local_path = str(tmp_dir / "input.jpg")
            try:
                self.download(path_or_url, local_path)
                return local_path
            except Exception:
                return path_or_url
        return path_or_url

    def _infer_kind(self, weight: Optional[str]) -> Optional[str]:
        try:
            if not weight:
                return None
            full = str(Path(weight).name).lower()
            if any(tok in full for tok in ["head", "count", "counts", "per_counts"]):
                return "head"
            return "student"
        except Exception:
            return None

    def _resolve_weight_path(self, weight: str) -> str:
        p = Path(weight)
        if p.is_absolute():
            return str(p)
        if p.exists():
            return str(p)
        return str((Path(self.config.weights_dir) / weight).resolve())

    def ai_status(self):
        info: Dict[str, Any] = {"has_ai_client": AIClient is not None}
        try:
            if AIClient is not None:
                client = AIClient()
                info.update(
                    {
                        "ready": bool(getattr(client, "ready", False)),
                        "model_text": getattr(client, "model_text", ""),
                        "model_vision": getattr(client, "model_vision", ""),
                    }
                )
            return jsonify({"status": 200, "message": "success", "data": info})
        except Exception as e:
            return jsonify({"status": 500, "message": str(e), "data": info}), 500

    def files_upload(self):
        f = request.files.get("file")
        if not f:
            return jsonify({"status": 400, "message": "missing file field"}), 400

        files_dir = Path(self.config.files_dir)
        files_dir.mkdir(parents=True, exist_ok=True)

        orig = secure_filename(f.filename or "upload.bin")
        name = f"{uuid.uuid4().hex}_{orig}"
        save_path = files_dir / name
        f.save(str(save_path))

        url = f"http://localhost:{self.port}/files/{name}"
        return jsonify({"status": 200, "message": "success", "data": url, "url": url})

    def files_get(self, filename: str):
        files_dir = Path(self.config.files_dir)
        files_dir.mkdir(parents=True, exist_ok=True)
        return send_from_directory(str(files_dir), filename, as_attachment=False)

    def file_names(self):
        weight_dir = Path(self.config.weights_dir)
        items = []
        if weight_dir.exists():
            for p in sorted(weight_dir.iterdir()):
                if p.is_file():
                    items.append({"value": p.name, "label": p.name})
        return jsonify({"status": 200, "message": "success", "weight_items": items})

    def file_names_wrapped(self):
        # Keep a dedicated endpoint for old clients that call /flask/file_names.
        return self.file_names()
