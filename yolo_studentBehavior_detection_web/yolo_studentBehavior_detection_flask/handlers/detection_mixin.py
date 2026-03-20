"""Detection and analysis handlers."""

import json
import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from flask import jsonify, request

from predict.detector import Detector
from predict.dual_detector import run_dual_on_image

try:
    from ultralytics import YOLO  # type: ignore
except Exception:
    YOLO = None  # type: ignore

try:
    from screen_capture.ai_client import AIClient  # type: ignore
except Exception:
    AIClient = None  # type: ignore

try:
    from student_behavior_ai.analyze import (  # type: ignore
        build_json_only_prompt,
        derive_metrics,
        normalize_counts,
        rule_based_summary,
        spatial_summary,
    )
except Exception:
    build_json_only_prompt = None
    derive_metrics = None
    normalize_counts = None
    rule_based_summary = None
    spatial_summary = None

try:
    from student_behavior_ai.postprocess import enrich_consistency  # type: ignore
except Exception:
    enrich_consistency = None

try:
    from student_behavior_ai.report_markdown import markdown_from_ai_json  # type: ignore
except Exception:
    markdown_from_ai_json = None

try:
    from student_behavior_ai.visualize import render_report_image  # type: ignore
except Exception:
    render_report_image = None


class DetectionHandlersMixin:
    def predictImg(self):
        data = request.get_json(force=True, silent=True) or {}
        input_img = data.get("inputImg")
        weight = data.get("weight")
        if not input_img:
            return jsonify({"status": 400, "message": "inputImg is required"}), 400
        if not weight:
            return jsonify({"status": 400, "message": "weight is required"}), 400

        username = data.get("username", "")
        conf = float(data.get("conf", 0.5) or 0.5)
        kind = data.get("kind") or self._infer_kind(weight) or "student"
        backend = (data.get("backend") or "").strip().lower()
        if not backend:
            backend = "onnxruntime" if str(weight).lower().endswith(".onnx") else "ultralytics"

        img_path = self._localize_image_path(input_img)
        weight_path = self._resolve_weight_path(weight)
        runs_dir = Path(self.config.runs_dir)
        runs_dir.mkdir(parents=True, exist_ok=True)
        vis_path = str(runs_dir / "result.jpg")

        try:
            detector = Detector(weights_path=weight_path, kind=kind, backend=backend)
            det = detector.predict_image(img_path, conf=conf, save_vis_path=vis_path)
        except Exception as e:
            return jsonify({"status": 400, "message": f"predict failed: {e}"}), 400

        out_img_url = self.upload(vis_path) or str(Path(vis_path).resolve())
        objects = []
        boxes: Dict[str, List[Dict[str, Any]]] = {}
        labels: List[str] = []
        confidences: List[float] = []
        for d in det.detections:
            label = str(d.get("label") or "object")
            score = float(d.get("score") or 0.0)
            bbox = d.get("bbox")
            labels.append(label)
            confidences.append(score)
            obj = {"label": label, "bbox_xyxy": bbox, "confidence": score}
            objects.append(obj)
            boxes.setdefault(label, []).append({"bbox_xyxy": bbox, "confidence": score})

        out = {
            "status": 200,
            "message": "success",
            "outImg": out_img_url,
            "allTime": f"{det.time.get('total', 0):.3f}s",
            "detections": det.detections,
            "counts": det.counts,
            "objects": objects,
            "boxes": boxes,
            "image": str(Path(img_path).resolve()),
            "size": {
                "width": int(det.image_size[0] if det.image_size else 0),
                "height": int(det.image_size[1] if det.image_size else 0),
            },
            "backend": det.backend,
            "model": det.model_name,
            "image_size": list(det.image_size) if det.image_size else [0, 0],
            # compatibility for old /imgPredict page
            "label": json.dumps(labels, ensure_ascii=False),
            "confidence": json.dumps(confidences, ensure_ascii=False),
        }

        record = {
            "username": username,
            "inputImg": input_img,
            "outImg": out_img_url,
            "weight": weight,
            "kind": kind,
            "allTime": out["allTime"],
            "conf": conf,
            "startTime": data.get("startTime", ""),
            "label": out["label"],
            "confidence": out["confidence"],
        }
        self._post_with_fallback(record, self.config.spring_imgrecords_path, "/api/imgRecords")
        return jsonify(out)

    def predict_legacy(self):
        try:
            raw = self.predictImg()
            resp = raw
            http_status = 200
            if isinstance(raw, tuple):
                resp = raw[0]
                if len(raw) > 1 and isinstance(raw[1], int):
                    http_status = raw[1]
            elif hasattr(raw, "status_code"):
                http_status = int(getattr(raw, "status_code"))

            if hasattr(resp, "status_code"):
                try:
                    http_status = int(getattr(resp, "status_code"))
                except Exception:
                    pass

            body = resp.get_json(silent=True) if hasattr(resp, "get_json") else None
            if body is None:
                return jsonify({"code": 500, "msg": "empty response"}), max(http_status, 500)

            payload_status = self._safe_int(body.get("status"))
            payload_code = self._safe_int(body.get("code"))
            ok = (payload_status is None or payload_status < 400) and (payload_code is None or payload_code == 0)
            legacy_code = 0 if ok else 500
            legacy_msg = body.get("message") or body.get("msg") or ("success" if ok else "error")
            legacy_data = body.get("data", body)
            legacy = {"code": legacy_code, "msg": legacy_msg, "data": json.dumps(legacy_data, ensure_ascii=False)}
            if ok:
                return jsonify(legacy)
            return jsonify(legacy), (payload_status or http_status or 400)
        except Exception as e:
            return jsonify({"code": 500, "msg": str(e)}), 500

    def dualDetect(self):
        data = request.get_json(force=True, silent=True) or {}
        input_img = data.get("inputImg")
        if not input_img:
            return jsonify({"status": 400, "message": "inputImg is required"}), 400

        behavior_weight = data.get("behavior_weight") or "best_student.pt"
        counts_weight = data.get("counts_weight") or "best_per_counts.pt"
        conf = float(data.get("conf", 0.5) or 0.5)
        imgsz = int(data.get("imgsz", 640) or 640)
        backend = (data.get("backend") or "").strip().lower()
        save_json = bool(data.get("save_json", False))
        out_dir = data.get("out_dir") or str(Path(self.config.runs_dir) / "behavior_json")

        img_path = self._localize_image_path(input_img)
        behavior_weight_path = self._resolve_weight_path(behavior_weight)
        counts_weight_path = self._resolve_weight_path(counts_weight)

        try:
            use_onnx_for_behavior = behavior_weight_path.lower().endswith(".onnx") or backend == "onnxruntime"
            use_onnx_for_counts = counts_weight_path.lower().endswith(".onnx") or backend == "onnxruntime"

            if (not use_onnx_for_behavior and not use_onnx_for_counts) and YOLO is not None:
                merged = run_dual_on_image(
                    img_path,
                    behavior_weight_path,
                    counts_weight_path,
                    conf=conf,
                    imgsz=imgsz,
                )
            else:
                merged = self._run_dual_generic(
                    img_path=img_path,
                    behavior_weight=behavior_weight_path,
                    counts_weight=counts_weight_path,
                    conf=conf,
                    backend=backend,
                )
        except Exception as e:
            return jsonify({"status": 400, "message": f"dual detect failed: {e}"}), 400

        saved_paths = None
        if save_json:
            outp = Path(out_dir)
            outp.mkdir(parents=True, exist_ok=True)
            stem = Path(img_path).stem
            behavior_json_path = outp / f"{stem}_behavior.json"
            behavior_json = {
                "image": merged.get("image"),
                "size": merged.get("size"),
                "counts": merged.get("counts", {}),
                "boxes": merged.get("boxes", {}),
                "objects": merged.get("objects") or merged.get("detections", []),
                "head": merged.get("head"),
                "人数": merged.get("人数"),
            }
            behavior_json_path.write_text(json.dumps(behavior_json, ensure_ascii=False, indent=2), encoding="utf-8")
            saved_paths = {"behavior_json": str(behavior_json_path)}

        resp = {"status": 200, "message": "success", **merged}
        if saved_paths:
            resp["saved_paths"] = saved_paths
        return jsonify(resp)

    def analyze(self):
        data = request.get_json(force=True, silent=True) or {}
        title = data.get("title") or "课堂行为分析"
        save_json_out = bool(data.get("save_json_out", False))
        out_dir = data.get("out_dir") or str(Path(self.config.runs_dir) / "analysis")
        out_stem = data.get("out_stem") or "analysis"

        analysis_json_path = data.get("analysis_json_path")
        if analysis_json_path:
            try:
                analysis_json = json.loads(Path(analysis_json_path).read_text(encoding="utf-8"))
            except Exception as e:
                return jsonify({"status": 400, "message": f"read analysis_json_path failed: {e}"}), 400
            result = self._build_analysis_outputs(
                analysis_json=analysis_json,
                title=title,
                save_json_out=save_json_out,
                out_dir=out_dir,
                out_stem=out_stem,
            )
            result["saved_analysis_json_path"] = analysis_json_path
            return jsonify(result)

        behavior_payload = self._load_behavior_payload(data)
        if behavior_payload is None:
            return jsonify({"status": 400, "message": "analysis requires behavior_json_path / behavior_json / inputImg+weight"}), 400

        counts = self._normalize_counts(behavior_payload.get("counts") or {})
        head = self._safe_int(behavior_payload.get("head"))
        if head is None:
            head = self._estimate_head(counts)
        boxes = self._collect_boxes_for_spatial(behavior_payload)
        img_size = self._parse_img_size(behavior_payload.get("size"), behavior_payload.get("image_size"))

        metrics = self._derive_metrics(counts, head)
        spatial = self._spatial_summary(boxes, img_size)
        summary = self._rule_summary(counts, head)
        analysis_json = {
            "schema_version": "1.1",
            "summary": summary.splitlines()[0] if summary else "课堂行为分析完成",
            "observations": [line for line in summary.splitlines()[1:] if line.strip()][:6],
            "metrics": metrics,
            "per_class": counts,
            "spatial": spatial,
            "risks": [],
            "suggestions": [],
            "limitations": [],
            "confidence": "medium",
            "source": {
                "image_path": behavior_payload.get("image") or data.get("inputImg") or "",
                "image_size": {"width": img_size[0], "height": img_size[1]},
            },
            "head": head,
            "人数": head,
        }

        ai_json = self._call_ai_json(
            image_path=behavior_payload.get("image") or data.get("inputImg"),
            counts=counts,
            head=head,
            spatial=spatial,
        )
        if isinstance(ai_json, dict):
            analysis_json.update(ai_json)

        if enrich_consistency:
            try:
                analysis_json = enrich_consistency(analysis_json)
            except Exception:
                pass

        result = self._build_analysis_outputs(
            analysis_json=analysis_json,
            title=title,
            save_json_out=save_json_out,
            out_dir=out_dir,
            out_stem=out_stem,
        )

        self._save_behavior_record(
            analysis_json=analysis_json,
            metrics=metrics,
            spatial=spatial,
            head=head,
        )
        return jsonify(result)

    def _run_dual_generic(
        self,
        img_path: str,
        behavior_weight: str,
        counts_weight: str,
        conf: float,
        backend: str,
    ) -> Dict[str, Any]:
        b_backend = "onnxruntime" if behavior_weight.lower().endswith(".onnx") or backend == "onnxruntime" else "ultralytics"
        c_backend = "onnxruntime" if counts_weight.lower().endswith(".onnx") or backend == "onnxruntime" else "ultralytics"
        b_det = Detector(weights_path=behavior_weight, kind="student", backend=b_backend)
        c_det = Detector(weights_path=counts_weight, kind="student", backend=c_backend)
        b_res = b_det.predict_image(img_path, conf=conf, save_vis_path=None)
        c_res = c_det.predict_image(img_path, conf=conf, save_vis_path=None)

        width, height = 0, 0
        if b_res.image_size:
            width, height = int(b_res.image_size[0]), int(b_res.image_size[1])

        boxes_map: Dict[str, List[Dict[str, Any]]] = {}
        counts_map: Dict[str, int] = {}
        objects = []
        for d in b_res.detections:
            label = str(d.get("label", "object"))
            bbox = d.get("bbox")
            confd = d.get("score")
            objects.append({"label": label, "bbox_xyxy": bbox, "confidence": confd})
            boxes_map.setdefault(label, []).append({"bbox_xyxy": bbox, "confidence": confd})
            counts_map[label] = counts_map.get(label, 0) + 1

        head_count = len(c_res.detections or [])
        return {
            "image": str(Path(img_path).resolve()),
            "size": {"width": width, "height": height},
            "detections": objects,
            "objects": objects,
            "boxes": boxes_map,
            "counts": counts_map,
            "head": head_count,
            "人数": head_count,
            "backend": "mixed" if b_backend != c_backend else b_backend,
            "provenance": {"head_source": "counts_model"},
            "models": {"behavior": behavior_weight, "counts": counts_weight},
        }

    def _load_behavior_payload(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        behavior_json_path = data.get("behavior_json_path")
        behavior_json_raw = data.get("behavior_json")
        if behavior_json_path:
            try:
                obj = json.loads(Path(behavior_json_path).read_text(encoding="utf-8"))
                if isinstance(obj, dict):
                    return obj
            except Exception:
                return None
        if behavior_json_raw is not None:
            if isinstance(behavior_json_raw, dict):
                return behavior_json_raw
            try:
                obj = json.loads(str(behavior_json_raw))
                if isinstance(obj, dict):
                    return obj
            except Exception:
                return None

        input_img = data.get("inputImg")
        weight = data.get("weight")
        if input_img and weight:
            img_path = self._localize_image_path(input_img)
            conf = float(data.get("conf", 0.5) or 0.5)
            backend = (data.get("backend") or "").strip().lower()
            if not backend:
                backend = "onnxruntime" if str(weight).lower().endswith(".onnx") else "ultralytics"
            detector = Detector(
                weights_path=self._resolve_weight_path(weight),
                kind=data.get("kind") or self._infer_kind(weight) or "student",
                backend=backend,
            )
            det = detector.predict_image(img_path, conf=conf, save_vis_path=None)
            objects = []
            boxes: Dict[str, List[Dict[str, Any]]] = {}
            for d in det.detections:
                label = str(d.get("label") or "object")
                bbox = d.get("bbox")
                confd = d.get("score")
                objects.append({"label": label, "bbox_xyxy": bbox, "confidence": confd})
                boxes.setdefault(label, []).append({"bbox_xyxy": bbox, "confidence": confd})
            return {
                "image": str(Path(img_path).resolve()),
                "size": {"width": int(det.image_size[0]), "height": int(det.image_size[1])},
                "counts": det.counts,
                "objects": objects,
                "boxes": boxes,
                "head": self._estimate_head(self._normalize_counts(det.counts)),
            }
        return None

    def _build_analysis_outputs(
        self,
        analysis_json: Dict[str, Any],
        title: str,
        save_json_out: bool,
        out_dir: str,
        out_stem: str,
    ) -> Dict[str, Any]:
        markdown = ""
        if markdown_from_ai_json:
            try:
                markdown = markdown_from_ai_json(analysis_json, title=title)
            except Exception:
                markdown = ""

        analysis_image_url = ""
        saved_analysis_png_path = ""
        if render_report_image:
            try:
                files_dir = Path(self.config.files_dir)
                files_dir.mkdir(parents=True, exist_ok=True)
                png_name = f"analysis_{uuid.uuid4().hex}.png"
                png_path = files_dir / png_name
                render_report_image(analysis_json, str(png_path), title=title)
                analysis_image_url = f"http://localhost:{self.port}/files/{png_name}"
                saved_analysis_png_path = str(png_path)
            except Exception:
                pass

        saved_analysis_json_path = ""
        if save_json_out:
            outp = Path(out_dir)
            outp.mkdir(parents=True, exist_ok=True)
            json_path = outp / f"{out_stem}.json"
            json_path.write_text(json.dumps(analysis_json, ensure_ascii=False, indent=2), encoding="utf-8")
            saved_analysis_json_path = str(json_path)

        return {
            "status": 200,
            "message": "success",
            "analysis_json": analysis_json,
            "analysis_markdown": markdown,
            "analysis_image_url": analysis_image_url,
            "saved_analysis_json_path": saved_analysis_json_path,
            "saved_analysis_png_path": saved_analysis_png_path,
        }

    def _call_ai_json(
        self,
        image_path: Optional[str],
        counts: Dict[str, int],
        head: int,
        spatial: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if AIClient is None:
            return None
        client = AIClient()
        if not getattr(client, "ready", False):
            return None

        prompt = "根据输入的课堂行为统计，输出结构化 JSON 分析结果。"
        if build_json_only_prompt:
            try:
                prompt = build_json_only_prompt(prompt)
            except Exception:
                pass
        payload = {"counts": counts, "head": head, "spatial": spatial}
        prompt = f"{prompt}\n\n输入JSON:\n{json.dumps(payload, ensure_ascii=False)}"

        raw = None
        try:
            if image_path and str(image_path).lower().startswith(("http://", "https://")):
                raw = client.chat([{"role": "user", "content": prompt}], response_format={"type": "json_object"})
            elif image_path and Path(image_path).exists():
                try:
                    from PIL import Image  # type: ignore

                    with Image.open(image_path) as im:
                        raw = client.analyze_image(im, prompt)
                except Exception:
                    raw = client.chat([{"role": "user", "content": prompt}], response_format={"type": "json_object"})
            else:
                raw = client.chat([{"role": "user", "content": prompt}], response_format={"type": "json_object"})
        except Exception:
            return None

        content = None
        if isinstance(raw, dict):
            content = raw.get("content")
        if not isinstance(content, str):
            return None
        return self._extract_json(content)

    def _extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        try:
            obj = json.loads(text)
            return obj if isinstance(obj, dict) else None
        except Exception:
            pass
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return None
        try:
            obj = json.loads(m.group(0))
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None

    def _save_behavior_record(self, analysis_json: Dict[str, Any], metrics: Dict[str, Any], spatial: Dict[str, Any], head: int) -> None:
        record = {
            "classroomId": str(analysis_json.get("classroom_id") or "default"),
            "studentCount": int(head or 0),
            "focusScore": int(metrics.get("focus_score", 0) or 0),
            "activityScore": int(metrics.get("activity_score", 0) or 0),
            "interactionLevel": str(metrics.get("interaction_level", "medium")),
            "metricsJson": json.dumps(metrics, ensure_ascii=False),
            "spatialJson": json.dumps(spatial, ensure_ascii=False),
            "risksJson": json.dumps(analysis_json.get("risks", []), ensure_ascii=False),
            "suggestionsJson": json.dumps(analysis_json.get("suggestions", []), ensure_ascii=False),
        }
        self._post_with_fallback(record, self.config.spring_behavior_save_path, "")

    def _post_with_fallback(self, payload: Dict[str, Any], primary_path: str, fallback_path: str) -> Optional[int]:
        base = self.config.spring_base_url.rstrip("/")
        candidates = [f"{base}{primary_path}"]
        if fallback_path and fallback_path != primary_path:
            candidates.append(f"{base}{fallback_path}")
        body = json.dumps(payload, ensure_ascii=False)
        status = None
        for url in candidates:
            try:
                status = self.save_data(body, url)
                if status == 200:
                    return status
            except Exception:
                status = None
        return status

    def _normalize_counts(self, counts: Dict[str, Any]) -> Dict[str, int]:
        if normalize_counts:
            try:
                return normalize_counts(counts)  # type: ignore[misc]
            except Exception:
                pass
        out: Dict[str, int] = {}
        for k, v in (counts or {}).items():
            try:
                out[str(k)] = int(v)
            except Exception:
                continue
        return out

    def _derive_metrics(self, counts: Dict[str, int], head: int) -> Dict[str, Any]:
        if derive_metrics:
            try:
                return derive_metrics(counts, head)  # type: ignore[misc]
            except Exception:
                pass
        return {
            "head_down_rate": 0,
            "phone_usage_rate": 0,
            "reading_rate": 0,
            "hand_raise_rate": 0,
            "looking_around_rate": 0,
            "writing_rate": 0,
            "sleeping_rate": 0,
            "distracted_rate": 0,
            "interaction_level": "low",
            "focus_score": 0,
            "activity_score": 0,
        }

    def _rule_summary(self, counts: Dict[str, int], head: int) -> str:
        if rule_based_summary:
            try:
                return rule_based_summary(counts, head)  # type: ignore[misc]
            except Exception:
                pass
        return "课堂行为分析完成"

    def _spatial_summary(self, boxes: List[Dict[str, Any]], img_size: Tuple[int, int]) -> Dict[str, Any]:
        if spatial_summary:
            try:
                return spatial_summary(boxes, img_size)  # type: ignore[misc]
            except Exception:
                pass
        return {"grid3x3": [[0, 0, 0], [0, 0, 0], [0, 0, 0]], "image_size": {"width": img_size[0], "height": img_size[1]}}

    def _collect_boxes_for_spatial(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        objects = payload.get("objects")
        if isinstance(objects, list):
            for it in objects:
                if not isinstance(it, dict):
                    continue
                bbox = it.get("bbox") or it.get("bbox_xyxy")
                if isinstance(bbox, list) and len(bbox) == 4:
                    out.append({"label": it.get("label", "object"), "bbox": bbox})
        boxes = payload.get("boxes")
        if isinstance(boxes, dict):
            for label, arr in boxes.items():
                if not isinstance(arr, list):
                    continue
                for it in arr:
                    if not isinstance(it, dict):
                        continue
                    bbox = it.get("bbox") or it.get("bbox_xyxy")
                    if isinstance(bbox, list) and len(bbox) == 4:
                        out.append({"label": str(label), "bbox": bbox})
        return out

    def _parse_img_size(self, size_obj: Any, image_size_obj: Any) -> Tuple[int, int]:
        if isinstance(size_obj, dict):
            w = self._safe_int(size_obj.get("width")) or 0
            h = self._safe_int(size_obj.get("height")) or 0
            if w > 0 and h > 0:
                return (w, h)
        if isinstance(image_size_obj, (list, tuple)) and len(image_size_obj) >= 2:
            w = self._safe_int(image_size_obj[0]) or 0
            h = self._safe_int(image_size_obj[1]) or 0
            if w > 0 and h > 0:
                return (w, h)
        return (1, 1)

    def _estimate_head(self, counts: Dict[str, int]) -> int:
        if not counts:
            return 0
        if "head" in counts and counts["head"] > 0:
            return counts["head"]
        total = 0
        for k, v in counts.items():
            lk = k.lower()
            if lk in {"head", "人数"}:
                continue
            total += int(v or 0)
        return max(1, total) if total > 0 else 0

    def _safe_int(self, v: Any) -> Optional[int]:
        try:
            if v is None:
                return None
            return int(v)
        except Exception:
            return None
