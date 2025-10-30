# --- Numpy 2.0 兼容补丁开始: 为旧版 imgaug 等访问 np.sctypes 提供兼容 ---
import numpy as _np
if not hasattr(_np, 'sctypes'):
    try:
        _np.sctypes = {
            'int':   [_np.int8, _np.int16, _np.int32, _np.int64],
            'uint':  [_np.uint8, _np.uint16, _np.uint32, _np.uint64],
            'float': [_np.float16, _np.float32, _np.float64],
            'complex': [_np.complex64, _np.complex128],
            'others': [_np.bool_, _np.bytes_, _np.str_]
        }
    except Exception:
        pass
# --- Numpy 2.0 兼容补丁结束 ---

from paddleocr import PaddleOCR
# 兼容导入 draw_ocr：不同版本位置变化，失败则用自定义 simple_draw_ocr
try:
    try:
        from paddleocr.tools.infer.utility import draw_ocr  # 优先
    except Exception:
        try:
            from paddleocr.ppocr.utils.visual import draw_ocr  # 备用路径
        except Exception:
            from paddleocr.tools.infer.predict_system import draw_ocr  # 再次尝试
except Exception:
    draw_ocr = None

from PIL import Image, ImageDraw, ImageFont
import os, sys, time, traceback
from typing import List

print('Python', sys.version)

# ---- 版本诊断 ----
def _safe_import(name):
    try:
        mod = __import__(name)
        print(f'{name} =', getattr(mod, '__version__', 'UNKNOWN'))
        return mod
    except Exception as e:
        print(f'{name} import failed:', e)
        return None

_np = _safe_import('numpy')
_cv2 = _safe_import('cv2')
_paddle = _safe_import('paddle')
try:
    import google.protobuf as _pb
    print('protobuf =', _pb.__version__)
    from packaging.version import Version
    if Version(_pb.__version__) >= Version('4.0.0'):
        print('[Warn] protobuf 版本较新，如遇 "Descriptors cannot be created directly" 执行:')
        print('       pip install --force-reinstall protobuf==3.20.2')
except Exception as e:
    print('protobuf import failed:', e)

# ---- 字体与简易绘制 ----

# 简易渲染函数（没有官方 draw_ocr 时使用）
def simple_draw_ocr(pil_img, boxes, txts, scores=None, font_path=None):
    img = pil_img.copy()
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(font_path or 'simfang.ttf', 16)
    except Exception:
        font = ImageFont.load_default()
    for i, box in enumerate(boxes):
        if isinstance(box, (list, tuple)) and len(box) == 4 and isinstance(box[0], (list, tuple)):
            draw.polygon([tuple(p) for p in box], outline='red')
            label = txts[i]
            if scores:
                label += f' ({scores[i]:.2f})'
            x, y = box[0]
            draw.text((x, y-15), label, fill='yellow', font=font)
    return img

# ---- 尝试导入 PaddleOCR draw_ocr ----
try:
    try:
        from paddleocr import PaddleOCR  # type: ignore
    except Exception as e:
        print('[Info] PaddleOCR 基础导入失败，将尝试回退 RapidOCR: ', e)
        PaddleOCR = None  # type: ignore
    draw_ocr = None
    if PaddleOCR:
        try:
            try:
                from paddleocr.tools.infer.utility import draw_ocr
            except Exception:
                try:
                    from paddleocr.ppocr.utils.visual import draw_ocr
                except Exception:
                    from paddleocr.tools.infer.predict_system import draw_ocr
        except Exception as e:
            print('[Info] draw_ocr 高级可视化导入失败，使用 simple_draw_ocr:', e)
            draw_ocr = None
except Exception as e:
    print('[Fatal] paddleocr import overall failed:', e)
    PaddleOCR = None  # type: ignore
    draw_ocr = None

# ---- 本地模型目录逻辑 ----
USE_LOCAL = False
base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'PaddleOCR-main', 'inference'))
kwargs = dict(lang='ch', use_angle_cls=False, show_log=False)

missing_files: List[str] = []
if USE_LOCAL and os.path.isdir(base):
    det_dir = os.path.join(base, 'ch_ppocr_mobile_v2.0_det_infer')
    rec_dir = os.path.join(base, 'ch_ppocr_mobile_v2.0_rec_infer')
    if os.path.isdir(det_dir) and os.path.isdir(rec_dir):
        kwargs['det_model_dir'] = det_dir
        kwargs['rec_model_dir'] = rec_dir
        # 粗略检查关键文件
        for d in (det_dir, rec_dir):
            exp = ['inference.pdmodel','inference.pdiparams','inference.pdiparams.info']
            for f in exp:
                if not os.path.exists(os.path.join(d, f)):
                    missing_files.append(f'{d}/{f}')
        if missing_files:
            print('[Warn] 本地模型目录缺失关键文件:')
            for mf in missing_files:
                print('       -', mf)
            print('       将继续尝试初始化，如失败可删除整个 inference 目录让其重新下载。')
    else:
        print('[Info] 本地 inference 目录存在但 det/rec 子目录不全，忽略本地模型。')
else:
    if USE_LOCAL:
        print('[Info] 未找到本地 inference 目录，走在线/默认模型。')

print('[Init] kwargs =', kwargs)
backend_used = None
ocr = None
init_error = None
start_init = time.time()

if PaddleOCR:
    try:
        ocr = PaddleOCR(**kwargs)
        backend_used = 'paddle'
        print(f'[Init] PaddleOCR 用时 {time.time() - start_init:.2f}s')
    except Exception as e:
        init_error = e
        print('[Error] PaddleOCR 初始化失败:')
        traceback.print_exc()
else:
    init_error = Exception('PaddleOCR 未导入')

# ---- RapidOCR 回退 ----
if ocr is None:
    try:
        from rapidocr_onnxruntime import RapidOCR  # type: ignore
        print('[Info] 尝试回退 RapidOCR ...')
        start2 = time.time()
        ocr = RapidOCR()
        backend_used = 'rapidocr'
        print(f'[Init] RapidOCR 用时 {time.time() - start2:.2f}s')
    except Exception as e2:
        print('[Fatal] RapidOCR 回退也失败。')
        print('--- Paddle 错误 ---')
        if init_error:
            print(str(init_error))
        print('--- RapidOCR 错误 ---')
        traceback.print_exc()
        sys.exit(1)

print('[OK] OCR 后端 =', backend_used)

img_path = './screen_capture/tests/test.png'
if not os.path.exists(img_path):
    print(f'[Warn] {img_path} 不存在，跳过识别。放一张含文字图片即可。')
    sys.exit(0)

# ---- 推理 ----
try:
    start = time.time()
    if backend_used == 'rapidocr':
        # RapidOCR 返回 (结果列表, 时间)
        result, elapsed = ocr(img_path)  # type: ignore
        print(f'[Infer] RapidOCR total = {elapsed:.2f}s (wall={time.time()-start:.2f}s)')
        # 统一格式转换为 PaddleOCR 风格列表，以便后续处理
        norm = [[item[0], [item[1], item[2]]] for item in (result or []) if len(item) >= 3]
        result = [norm]
    else:
        result = ocr.ocr(img_path, cls=False)  # type: ignore
        print(f'[Infer] Paddle total = {time.time() - start:.2f}s')
except Exception:
    print('[Error] 推理阶段异常:')
    traceback.print_exc()
    sys.exit(1)

# ---- 打印结构 ----
if not result or not result[0]:
    print('[Info] 无文本或解析为空')
    sys.exit(0)

for block in result:
    for line in block:
        print(line)

image = Image.open(img_path).convert('RGB')
block = result[0]
boxes = [line[0] for line in block]
texts = [line[1][0] for line in block]
conf = [line[1][1] for line in block]

try:
    if backend_used == 'paddle' and draw_ocr:
        try:
            vis = draw_ocr(image, boxes, texts, conf, font_path='doc/fonts/simfang.ttf')
            from PIL import Image as _Image
            if vis.dtype != 'uint8':
                vis = vis.astype('uint8')
            out = _Image.fromarray(vis)
        except Exception as e:
            print('[draw_ocr fallback]', e)
            out = simple_draw_ocr(image, boxes, texts, conf, font_path='doc/fonts/simfang.ttf')
    else:
        out = simple_draw_ocr(image, boxes, texts, conf, font_path='doc/fonts/simfang.ttf')
    out.save('result.jpg')
    print('结果已保存: result.jpg')
except Exception:
    print('[Warn] 可视化保存失败:')
    traceback.print_exc()
    # 不视为致命错误
    pass