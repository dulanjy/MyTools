"""Video/camera streaming handlers and IO helpers."""

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import requests
from flask import Response, jsonify, request

try:
    from ultralytics import YOLO  # type: ignore
except Exception:
    YOLO = None  # type: ignore


class StreamHandlersMixin:
    def predictVideo(self):
        input_video = request.args.get("inputVideo")
        if not input_video:
            return jsonify({"status": 400, "message": "inputVideo is required"}), 400

        self.data.clear()
        self.data.update(
            {
                "username": request.args.get("username"),
                "weight": request.args.get("weight"),
                "conf": request.args.get("conf"),
                "startTime": request.args.get("startTime"),
                "inputVideo": input_video,
                "kind": request.args.get("kind") or self._infer_kind(request.args.get("weight")) or "student",
            }
        )

        self.download(self.data["inputVideo"], self.paths["download"])
        cap = cv2.VideoCapture(self.paths["download"])
        if not cap.isOpened():
            return jsonify({"status": 400, "message": "cannot open input video"}), 400

        fps = int(cap.get(cv2.CAP_PROP_FPS) or 20)
        video_writer = cv2.VideoWriter(
            self.paths["video_output"],
            cv2.VideoWriter_fourcc(*"XVID"),
            fps,
            (640, 480),
        )
        model = None
        if YOLO is not None and self.data.get("weight"):
            model = YOLO(self._resolve_weight_path(self.data["weight"]))

        def generate():
            try:
                while cap.isOpened():
                    ret, frame = cap.read()
                    if not ret:
                        break
                    frame = cv2.resize(frame, (640, 480))
                    if model is not None:
                        results = model.predict(source=frame, conf=float(self.data.get("conf") or 0.25), show=False)
                        processed = results[0].plot()
                    else:
                        processed = frame
                    video_writer.write(processed)
                    ok, jpeg = cv2.imencode(".jpg", processed)
                    if not ok:
                        continue
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n"
            finally:
                self.cleanup_resources(cap, video_writer)
                self.socketio.emit("message", {"data": "处理完成，正在保存"})
                for progress in self.convert_avi_to_mp4(self.paths["video_output"]):
                    self.socketio.emit("progress", {"data": progress})
                uploaded = self.upload(self.paths["output"])
                self.data["outVideo"] = uploaded
                self._post_video_record(self.data, self.config.spring_videorecords_path, "/api/videoRecords")
                self.cleanup_files([self.paths["download"], self.paths["output"], self.paths["video_output"]])

        return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")

    def predictCamera(self):
        self.data.clear()
        self.data.update(
            {
                "username": request.args.get("username"),
                "weight": request.args.get("weight"),
                "conf": request.args.get("conf"),
                "startTime": request.args.get("startTime"),
                "kind": request.args.get("kind") or self._infer_kind(request.args.get("weight")) or "student",
            }
        )

        model = None
        if YOLO is not None and self.data.get("weight"):
            model = YOLO(self._resolve_weight_path(self.data["weight"]))

        cap = cv2.VideoCapture(0)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        video_writer = cv2.VideoWriter(self.paths["camera_output"], cv2.VideoWriter_fourcc(*"XVID"), 20, (640, 480))
        self.recording = True

        def generate():
            try:
                while self.recording:
                    ret, frame = cap.read()
                    if not ret:
                        break
                    if model is not None:
                        results = model.predict(source=frame, imgsz=640, conf=float(self.data.get("conf") or 0.25), show=False)
                        processed = results[0].plot()
                    else:
                        processed = frame
                    video_writer.write(processed)
                    ok, jpeg = cv2.imencode(".jpg", processed)
                    if not ok:
                        continue
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n"
            finally:
                self.cleanup_resources(cap, video_writer)
                self.socketio.emit("message", {"data": "处理完成，正在保存"})
                for progress in self.convert_avi_to_mp4(self.paths["camera_output"]):
                    self.socketio.emit("progress", {"data": progress})
                uploaded = self.upload(self.paths["output"])
                self.data["outVideo"] = uploaded
                self._post_video_record(self.data, self.config.spring_camerarecords_path, "/api/cameraRecords")
                self.cleanup_files([self.paths["download"], self.paths["output"], self.paths["camera_output"]])

        return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")

    def stopCamera(self):
        self.recording = False
        return jsonify({"status": 200, "message": "success"})

    def _post_video_record(self, payload: Dict[str, Any], primary_path: str, fallback_path: str) -> Optional[int]:
        base = self.config.spring_base_url.rstrip("/")
        candidates = [f"{base}{primary_path}"]
        if fallback_path and fallback_path != primary_path:
            candidates.append(f"{base}{fallback_path}")
        body = json.dumps(payload, ensure_ascii=False)
        status = None
        for url in candidates:
            status = self.save_data(body, url)
            if status == 200:
                return status
        return status

    def save_data(self, data: str, path: str) -> Optional[int]:
        headers = {"Content-Type": "application/json"}
        try:
            response = requests.post(path, data=data, headers=headers, timeout=20)
            return response.status_code
        except requests.RequestException:
            return None

    def convert_avi_to_mp4(self, temp_output: str):
        ffmpeg_command = f"ffmpeg -i \"{temp_output}\" -vcodec libx264 \"{self.paths['output']}\" -y"
        process = subprocess.Popen(ffmpeg_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        total_duration = self.get_video_duration(temp_output)

        if process.stderr is None:
            yield 100
            return
        for line in process.stderr:
            if "time=" not in line:
                continue
            try:
                time_str = line.split("time=")[1].split(" ")[0]
                h, m, s = map(float, time_str.split(":"))
                processed_time = h * 3600 + m * 60 + s
                if total_duration > 0:
                    progress = int((processed_time / total_duration) * 100)
                    yield max(0, min(100, progress))
            except Exception:
                continue
        process.wait()
        yield 100

    def get_video_duration(self, path: str) -> float:
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            return 0.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
        cap.release()
        return total_frames / fps if fps > 0 else 0.0

    def get_file_names(self, directory: str) -> List[str]:
        try:
            return [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]
        except Exception:
            return []

    def upload(self, out_path: str) -> Optional[str]:
        upload_url = f"{self.config.spring_base_url}{self.config.spring_upload_path}"
        try:
            with open(out_path, "rb") as f:
                files = {"file": (Path(out_path).name, f)}
                response = requests.post(upload_url, files=files, timeout=20)
            if response.status_code == 200:
                body = response.json()
                if isinstance(body, dict):
                    return body.get("data") or body.get("url")
        except Exception:
            return None
        return None

    def download(self, url: str, save_path: str) -> None:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        with requests.get(url, stream=True, timeout=30) as response:
            response.raise_for_status()
            with open(save_path, "wb") as file:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        file.write(chunk)

    def cleanup_files(self, file_paths: List[str]) -> None:
        for path in file_paths:
            try:
                if path and os.path.exists(path):
                    os.remove(path)
            except Exception:
                continue

    def cleanup_resources(self, cap: Any, video_writer: Any) -> None:
        try:
            if cap is not None and cap.isOpened():
                cap.release()
        except Exception:
            pass
        try:
            if video_writer is not None:
                video_writer.release()
        except Exception:
            pass
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass
