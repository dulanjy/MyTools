import argparse
import json
from collections import defaultdict
from pathlib import Path

import cv2
from ultralytics import YOLO


def parse_args():
    parser = argparse.ArgumentParser(
    description="Use a trained YOLOv8 .pt model to predict on images and save annotated outputs + counts")
    parser.add_argument("--model", type=str, required=True, help="Path to the trained .pt weights, e.g. pt/best_student.pt")
    parser.add_argument("--source", type=str, required=True, help="Path to image file, folder, or glob pattern")
    parser.add_argument("--conf", type=float, default=0.25, help="Confidence threshold")
    parser.add_argument("--imgsz", type=int, default=640, help="Inference image size")
    parser.add_argument("--device", type=str, default="0", help='Device id like "0", or "cpu"')
    parser.add_argument("--project", type=str, default="runs/detect", help="Parent directory for saves")
    parser.add_argument("--name", type=str, default="predict", help="Subdirectory name for this run")
    parser.add_argument("--exist-ok", action="store_true", help="Overwrite existing run directory")
    parser.add_argument("--show", action="store_true", help="Show window preview (for single images)")
    parser.add_argument("--json-dir", type=str, default=None, help="Optional directory to save counts JSON files separately")
    parser.add_argument("--save-crop", action="store_true", help="Save cropped images of each detected object")
    return parser.parse_args()


def _resolve_model_path(path_str: str) -> str:
    """Resolve model path robustly.
    1) If the given path exists (absolute or relative to CWD), use it.
    2) Otherwise, try resolving it relative to this script's directory.
    3) Fallback to original string (letting YOLO raise a clear error).
    """
    p = Path(path_str)
    if p.exists():
        return str(p)
    script_dir = Path(__file__).resolve().parent
    alt = script_dir / p
    if alt.exists():
        return str(alt)
    return path_str


def save_counts(result, class_names, json_dir: str | None = None):
    """Save per-image metadata (counts + positions) as JSON.

    JSON schema:
    {
        "image": <absolute_or_source_path>,
        "size": {"width": W, "height": H},
        "counts": {"label": n, ...},
        "boxes": {
        "label": [ {"bbox_xyxy": [x1,y1,x2,y2], "confidence": conf}, ... ],
        ...
        },
        "objects": [
        {"label": l, "bbox_xyxy": [...], "confidence": conf}, ...
        ]
    }
    """
    counts = defaultdict(int)
    boxes_by_label = defaultdict(list)
    objects = []

    # extract size
    w = h = None
    if hasattr(result, "orig_shape") and result.orig_shape is not None:
        try:
            h, w = int(result.orig_shape[0]), int(result.orig_shape[1])
        except Exception:
            pass

    # iterate boxes
    if getattr(result, "boxes", None) is not None:
        for box in result.boxes:
            try:
                cls_id = int(box.cls[0])
            except Exception:
                continue
            name = class_names.get(cls_id, str(cls_id))
            counts[name] += 1
            # bbox xyxy and confidence
            try:
                xyxy = [float(v) for v in box.xyxy[0].tolist()]
            except Exception:
                xyxy = None
            try:
                conf = float(box.conf[0])
            except Exception:
                conf = None
            entry = {"bbox_xyxy": xyxy, "confidence": conf}
            boxes_by_label[name].append(entry)
            objects.append({"label": name, **entry})

    payload = {
        "image": getattr(result, "path", None),
        "size": {"width": w, "height": h} if (w is not None and h is not None) else None,
        "counts": dict(counts),
        "boxes": boxes_by_label,
        "objects": objects,
    }

    # Determine save path: if json_dir is set, write there; else next to saved image(s)
    img_stem = Path(result.path).stem if hasattr(result, "path") else "image"
    if json_dir:
        out_path = Path(json_dir) / f"{img_stem}_counts.json"
        Path(json_dir).mkdir(parents=True, exist_ok=True)
    else:
        save_dir = Path(getattr(result, "save_dir", Path("runs/detect/predict")))
        out_path = save_dir / f"{img_stem}_counts.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[INFO] Saved metadata -> {out_path}")


def main():
    args = parse_args()
    # Resolve model path to avoid CWD-related FileNotFoundError
    model_path = _resolve_model_path(args.model)
    model = YOLO(model_path)

    # Run prediction and auto-save annotated images
    results = model.predict(
        source=args.source,
        conf=args.conf,
        imgsz=args.imgsz,
        device=args.device,
        save=True,
        save_crop=args.save_crop,
        project=args.project,
        name=args.name,
        exist_ok=args.exist_ok,
    )

    names = model.names if hasattr(model, "names") else {}

    # Save per-image counts and optionally show
    for r in results:
        save_counts(r, names, json_dir=args.json_dir)
        if args.show:
            im = r.plot()  # RGB
            bgr = cv2.cvtColor(im, cv2.COLOR_RGB2BGR)
            cv2.imshow("Prediction", bgr)
            cv2.waitKey(0)
            cv2.destroyAllWindows()

    # Print a short summary for the last result
    if results:
        last = results[-1]
        print("[SUMMARY] Classes detected (last image):")
        counts = defaultdict(int)
        if last.boxes is not None:
            for box in last.boxes:
                cid = int(box.cls[0])
                counts[names.get(cid, str(cid))] += 1
        for k, v in counts.items():
            print(f"  - {k}: {v}")


if __name__ == "__main__":
    main()
#"python 'C:\Users\hp1\Desktop\yolov11\ultralytics-main\predict_image.py' --model 'C:\Users\hp1\Desktop\yolov11\ultralytics-main\pt\best_student.pt' --source 'C:\Users\hp1\Desktop\class_data\images\00000001_jpg.rf.1046fb34275bf7547edb1e0e287ef371.jpg' --conf 0.25 --imgsz 640 --device 0 --project 'C:\Users\hp1\Desktop\yolov11\ultralytics-main\runs\detect' --name 'predict' --exist-ok --show"