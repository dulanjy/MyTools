import json
from pathlib import Path

b = Path(r"C:/Users/hp1/Desktop/yolov11/ultralytics-main/runs/dual_detect/00000756_jpg.rf.89c1e6796b2428435a848b51fb1e1d80_behavior.json")
c = Path(r"C:/Users/hp1/Desktop/yolov11/ultralytics-main/runs/dual_detect/00000756_jpg.rf.89c1e6796b2428435a848b51fb1e1d80_counts.json")

with open(b, 'r', encoding='utf-8') as f:
    behavior = json.load(f)
with open(c, 'r', encoding='utf-8') as f:
    counts = json.load(f)

# extract head count from counts
head_count = counts.get('counts', {}).get('head', None)
if head_count is not None:
    behavior.setdefault('counts', {})['head'] = head_count
    # overwrite file
    with open(b, 'w', encoding='utf-8') as f:
        json.dump(behavior, f, ensure_ascii=False, indent=2)
    print('Merged head count into behavior JSON:', head_count)
else:
    print('No head count found in counts JSON')
