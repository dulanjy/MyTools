"""
Dual-model detection script
- Loads two YOLO .pt weights (behavior model and per-counts/head-count model)
- Runs both models on the same input image(s)
- Saves full JSON for behavior model (based on provided example) and a minimal JSON for counts model

Usage examples:
python tools/dual_detect.py --source path/to/image_or_dir --out_dir runs/dual_detect --behavior_pt pt/best_student.pt --counts_pt pt/best_per_counts.pt
"""

import argparse
from pathlib import Path
import json
from ultralytics import YOLO
from PIL import Image


def run_on_image(img_path, behavior_model, counts_model, out_dir: Path):
    img = str(img_path)
    # Run behavior model
    b_res = behavior_model(img)
    # Run counts model
    c_res = counts_model(img)

    # Behavior: take first result
    b_r = b_res[0]
    c_r = c_res[0]

    # image size
    if hasattr(b_r, 'orig_shape'):
        h, w = int(b_r.orig_shape[0]), int(b_r.orig_shape[1])
    else:
        pil = Image.open(img)
        w, h = pil.size

    # Build per-object list from behavior model
    objects = []
    # b_r.boxes.xyxy, b_r.boxes.conf, b_r.boxes.cls
    boxes = getattr(b_r, 'boxes', None)
    if boxes is not None and len(boxes) > 0:
        xyxy = boxes.xyxy.tolist() if hasattr(boxes, 'xyxy') else []
        confs = boxes.conf.tolist() if hasattr(boxes, 'conf') else []
        cls_ids = boxes.cls.tolist() if hasattr(boxes, 'cls') else []
        names = behavior_model.model.names if hasattr(behavior_model, 'model') else {}
        for i, box in enumerate(xyxy):
            cls_name = names[int(cls_ids[i])] if int(cls_ids[i]) in names else str(int(cls_ids[i]))
            objects.append({
                'label': cls_name,
                'bbox_xyxy': [float(box[0]), float(box[1]), float(box[2]), float(box[3])],
                'confidence': float(confs[i]) if confs else None
            })

    # Counts model: count head boxes
    c_boxes = getattr(c_r, 'boxes', None)
    counts = 0
    if c_boxes is not None and len(c_boxes) > 0:
        counts = len(c_boxes.xyxy.tolist()) if hasattr(c_boxes, 'xyxy') else 0

    # Assemble behavior JSON similar to attachment and add counts
    behavior_json = {
        'image': str(img_path.resolve()),
        'size': {'width': w, 'height': h},
        'counts': {},
        'boxes': {},
        'objects': objects,
        'per_counts_count': counts
    }

    # Populate counts and boxes per class based on objects
    for obj in objects:
        lbl = obj['label']
        behavior_json['counts'].setdefault(lbl, 0)
        behavior_json['counts'][lbl] += 1
        behavior_json['boxes'].setdefault(lbl, []).append({'bbox_xyxy': obj['bbox_xyxy'], 'confidence': obj['confidence']})

    # Minimal counts JSON
    counts_json = {
        'image': str(img_path.resolve()),
        'size': {'width': w, 'height': h},
        'counts': {
            'head': counts
        }
    }

    # Save outputs
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = img_path.stem
    behavior_path = out_dir / f"{stem}_behavior.json"
    counts_path = out_dir / f"{stem}_counts.json"
    with open(behavior_path, 'w', encoding='utf-8') as f:
        json.dump(behavior_json, f, ensure_ascii=False, indent=2)
    with open(counts_path, 'w', encoding='utf-8') as f:
        json.dump(counts_json, f, ensure_ascii=False, indent=2)

    return behavior_path, counts_path


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source', type=str, required=True, help='Image path or directory')
    p.add_argument('--out_dir', type=str, default='runs/dual_detect', help='Output directory')
    p.add_argument('--behavior_pt', type=str, default='pt/best_student.pt', help='Behavior model weights')
    p.add_argument('--counts_pt', type=str, default='pt/best_per_counts.pt', help='Counts model weights')
    args = p.parse_args()

    src = Path(args.source)
    out_dir = Path(args.out_dir)

    behavior_model = YOLO(args.behavior_pt)
    counts_model = YOLO(args.counts_pt)

    if src.is_file():
        b, c = run_on_image(src, behavior_model, counts_model, out_dir)
        print('Saved:', b, c)
    else:
        images = [p for p in src.glob('*') if p.suffix.lower() in ['.jpg','.jpeg','.png']]
        for im in images:
            b, c = run_on_image(im, behavior_model, counts_model, out_dir)
            print('Saved:', b, c)


if __name__ == '__main__':
    main()
