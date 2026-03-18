"""Runtime configuration for Flask service."""

import os
from dataclasses import dataclass


@dataclass
class AppConfig:
    flask_host: str = "0.0.0.0"
    flask_port: int = 5000
    files_dir: str = "./files"
    runs_dir: str = "./runs"
    weights_dir: str = "./weights"
    spring_base_url: str = "http://localhost:9999"
    spring_upload_path: str = "/files/upload"
    spring_imgrecords_path: str = "/imgRecords"
    spring_videorecords_path: str = "/videoRecords"
    spring_camerarecords_path: str = "/cameraRecords"
    spring_behavior_save_path: str = "/behavior/save"

    @classmethod
    def from_env(cls) -> "AppConfig":
        return cls(
            flask_host=os.environ.get("FLASK_HOST", "0.0.0.0"),
            flask_port=_to_int(os.environ.get("FLASK_PORT") or os.environ.get("PORT"), 5000),
            files_dir=os.environ.get("FLASK_FILES_DIR", "./files"),
            runs_dir=os.environ.get("FLASK_RUNS_DIR", "./runs"),
            weights_dir=os.environ.get("FLASK_WEIGHTS_DIR", "./weights"),
            spring_base_url=os.environ.get("SPRING_BASE_URL", "http://localhost:9999").rstrip("/"),
            spring_upload_path=_norm_path(os.environ.get("SPRING_UPLOAD_PATH", "/files/upload")),
            spring_imgrecords_path=_norm_path(os.environ.get("SPRING_IMGRECORDS_PATH", "/imgRecords")),
            spring_videorecords_path=_norm_path(os.environ.get("SPRING_VIDEORECORDS_PATH", "/videoRecords")),
            spring_camerarecords_path=_norm_path(os.environ.get("SPRING_CAMERARECORDS_PATH", "/cameraRecords")),
            spring_behavior_save_path=_norm_path(os.environ.get("SPRING_BEHAVIOR_SAVE_PATH", "/behavior/save")),
        )


def _to_int(raw: str, default: int) -> int:
    try:
        return int(raw) if raw is not None else default
    except Exception:
        return default


def _norm_path(path: str) -> str:
    if not path:
        return ""
    return path if path.startswith("/") else ("/" + path)
