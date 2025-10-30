from paddleocr import PaddleOCR
import inspect, time, numpy as np
from PIL import Image
import os

IMG = r"C:\Users\hp1\Desktop\MyTools\screen_capture\tests\test.png"
if not os.path.isfile(IMG):
    raise FileNotFoundError(IMG)

sig = inspect.signature(PaddleOCR.__init__).parameters
kw = {}

# 必选
if 'lang' in sig: kw['lang'] = 'ch'

# 可能存在的轻量相关参数（逐一测试是否被接受）
for name, val in [
    ('det_model_name', 'PP-OCRv5_mobile_det'),
    ('rec_model_name', 'PP-OCRv5_mobile_rec'),
    ('layout', False),
    ('table', False),
    ('kie', False),
    ('use_angle_cls', False),
    ('use_textline_orientation', False),
    ('enable_doc_orientation', False),
    ('visual', False),
]:
    if name in sig:
        kw[name] = val

# 强制避免 doc 解析可选组件（如果参数支持）
for name in ['doc', 'structure', 'ppstructure']:
    if name in kw:
        kw[name] = False

t0 = time.time()
ocr = PaddleOCR(**kw)
print("Init:", time.time()-t0, "s")
print("Used kwargs:", kw)

img = Image.open(IMG).convert('RGB')
w, h = img.size
max_side = 960
scale = max(w, h)/max_side
if scale > 1:
    img = img.resize((int(w/scale), int(h/scale)))
arr = np.array(img)

t1 = time.time()
res = ocr.predict(arr)  # 新接口
infer_t = time.time()-t1

# 解析
def extract_lines(res):
    if not res: return []
    f = res[0]
    if isinstance(f, dict):
        for k in ('ocr','result','data','lines'):
            if k in f and isinstance(f[k], list):
                return f[k]
        return []
    if isinstance(f, list):
        return f
    return []
lines = extract_lines(res)
print(f"Infer lines={len(lines)} time={infer_t:.2f}s size={w}x{h}->{img.size[0]}x{img.size[1]}")
for i, ln in enumerate(lines[:3]):
    try:
        box, (txt, score) = ln
        print(f"[{i}] {txt} ({score:.3f})")
    except:
        print(f"[{i}] {ln}")