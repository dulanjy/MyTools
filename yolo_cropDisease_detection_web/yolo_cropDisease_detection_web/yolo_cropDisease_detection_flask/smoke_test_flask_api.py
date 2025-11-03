import json
import os
from pathlib import Path

# Ensure we run from the flask app directory
BASE = Path(__file__).resolve().parent
os.chdir(BASE)

from main import VideoProcessingApp

app = VideoProcessingApp(host='127.0.0.1', port=5001)
client = app.app.test_client()

# Prepare paths
img_path = str(BASE / 'picture' / 'test1.jpg')

# 1) /file_names
r = client.get('/file_names')
print('GET /file_names:', r.status_code)
print(r.get_data(as_text=True))

# 2) /predictImg (single behavior model)
payload1 = {
    'inputImg': img_path,
    'weight': 'best_student.pt',
    'kind': 'student',
    'conf': 0.25,
}
r = client.post('/predictImg', data=json.dumps(payload1), content_type='application/json')
print('POST /predictImg:', r.status_code)
print(r.get_data(as_text=True))

# 3) /dualDetect (behavior + headcount)
payload2 = {
    'inputImg': img_path,
    'behavior_weight': './weights/best_student.pt',
    'counts_weight': './weights/best_per_counts.pt',
    'conf': 0.25,
    'imgsz': 640,
    'save_json': True,
}
r = client.post('/dualDetect', data=json.dumps(payload2), content_type='application/json')
print('POST /dualDetect:', r.status_code)
print(r.get_data(as_text=True))
