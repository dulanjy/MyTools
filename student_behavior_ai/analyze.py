from __future__ import annotations
import argparse, json, os, time
from typing import Dict, Any, Optional, List, Tuple

from PIL import Image

# 复用项目内 AI 客户端
try:
    from screen_capture.ai_client import AIClient
except Exception:
    AIClient = None  # type: ignore


DEFAULT_PROMPT = (
    "你是一名教学观察与课堂行为分析助手。若提供了结构化 JSON（检测/统计/已有分析），"
    "必须以 JSON 为主、图片为辅进行判断；冲突时优先保留 JSON 结论，并在 limitations 说明依据。"
    "请客观评估本次课堂的学生专注度与行为特征，按以下结构输出：\n"
    "1) 关键观察要点（建议 3~6 条，短句；可结合计数与3×3空间分布）\n"
    "2) 指标评估（低头率、看手机、阅读/举手/环顾/书写/打瞌睡等，以0~100估算并简述依据）\n"
    "3) 风险与建议，风险点（2~4 条），改进建议（从教学节奏/互动设计/座位与视线管理/课堂规范等维度给出 3~6 条）\n"
    "可以适当结合json中的数据进行风险与建议，不一定要局限在图片内容\n"
    "注意：不要臆测不可见细节；图片仅作为辅证核对，不应覆盖 JSON 主体信息。"
)

def build_json_only_prompt(base_prompt: Optional[str]) -> str:
    """构造严格 JSON 输出的系统提示。

    设计要点（JSON-first）：
    - 若存在结构化 JSON（检测/统计/已有分析），以 JSON 为主、图片为辅；
    - 冲突时优先保留 JSON 结论，并在 limitations 解释；
    - 引导模型输出 3~6 条 observations，并约束 schema v1.1 字段与取值范围。
    """
    head = (base_prompt.strip() + "\n\n") if base_prompt else ''
    schema = (
        '请严格仅输出一个 JSON 对象（UTF-8，无注释、无多余文本）。\n'
        'JSON 优先规则：\n'
        '- 若提供了结构化 JSON（检测/统计/已有分析），以 JSON 为主、图片为辅；不可见证据不臆测；\n'
        '- 如与图片或直觉冲突，优先保留 JSON 结论，并在 limitations 说明冲突以提供参考；\n'
        '- observations 建议 3~6 条、短句，结合计数与 3×3 空间分布归纳显著现象。\n\n'
        '输出字段（schema v1.1）：\n'
        '{\n'
        '  "schema_version": "1.1",\n'
        '  "summary": "一句话概括",\n'
        '  "observations": ["要点1", "要点2", "要点3"],\n'
        '  "metrics": {\n'
        '    "head_down_rate": null,\n'
        '    "phone_usage_rate": null,\n'
        '    "reading_rate": null,\n'
        '    "hand_raise_rate": null,\n'
        '    "looking_around_rate": null,\n'
        '    "writing_rate": null,\n'
        '    "sleeping_rate": null,\n'
        '    "distracted_rate": null,\n'
        '    "interaction_level": "medium",\n'
        '    "focus_score": 0,\n'
        '    "activity_score": 0\n'
        '  },\n'
        '  "per_class": {},\n'
        '  "spatial": {"grid3x3": [[0,0,0],[0,0,0],[0,0,0]]},\n'
        '  "risks": ["风险1", "风险2"],\n'
        '  "suggestions": ["建议1", "建议2", "建议3"],\n'
        '  "limitations": ["局限1", "局限2"],\n'
        '  "confidence": "low|medium|high",\n'
        '  "source": {"image_path": "", "image_size": {"width": 0, "height": 0}}\n'
        '}\n\n'
        '规则补充：\n'
        '- 所有百分比/评分统一为 0~100 的整数；无法判断用 null，并在 limitations 说明原因；\n'
        '- interaction_level 取值仅限 "low"/"medium"/"high"；\n'
        '- 不要逐条罗列检测框，聚焦总体归类与显著现象。'
    )
    return head + schema


def _norm_label(label: str) -> str:
    s = (label or '').strip().lower().replace(' ', '_').replace('-', '_')
    # 常见同义映射
    alias = {
        'using_phone': 'using_phone',
        'use_phone': 'using_phone',
        'phone': 'phone',
        'hand_raising': 'hand_raise',
        'hand_raise': 'hand_raise',
        'raise_hand': 'hand_raise',
        'bow_head': 'bow_head',
        'bend': 'bow_head',
        'reading': 'reading',
        'book': 'reading',
        'upright': 'upright',
        'turn_head': 'turn_head',
        'raise_head': 'raise_head',
        'writing': 'writing',
    }
    return alias.get(s, s)


def parse_detection_json(path: str) -> Tuple[Dict[str, int], List[Dict[str, Any]], Tuple[int, int] | None]:
    """容错解析检测 JSON：返回 (counts, boxes, image_size)。支持多种常见格式。"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return {}, [], None

    boxes: List[Dict[str, Any]] = []
    counts: Dict[str, int] = {}
    img_size: Tuple[int, int] | None = None

    def to_xyxy(bb):
        try:
            x1, y1, x2, y2 = float(bb[0]), float(bb[1]), float(bb[2]), float(bb[3])
        except Exception:
            return [0.0, 0.0, 0.0, 0.0]
        # 若疑似为 xywh（x2<=x1 或 y2<=y1），转换为 xyxy
        if x2 <= x1 or y2 <= y1:
            x2 = x1 + max(0.0, x2)
            y2 = y1 + max(0.0, y2)
        return [x1, y1, x2, y2]

    if isinstance(data, dict):
        # image size 多形式
        if isinstance(data.get('image_size'), (list, tuple)) and len(data.get('image_size')) == 2:
            try:
                img_size = (int(data['image_size'][0]), int(data['image_size'][1]))
            except Exception:
                img_size = None
        elif isinstance(data.get('size'), dict):
            try:
                img_size = (int(data['size'].get('width')), int(data['size'].get('height')))
            except Exception:
                img_size = None
        elif isinstance(data.get('imageWidth'), (int, float)) and isinstance(data.get('imageHeight'), (int, float)):
            try:
                img_size = (int(data['imageWidth']), int(data['imageHeight']))
            except Exception:
                img_size = None
        elif isinstance(data.get('width'), (int, float)) and isinstance(data.get('height'), (int, float)):
            try:
                img_size = (int(data['width']), int(data['height']))
            except Exception:
                img_size = None

        # boxes: list 形式
        if isinstance(data.get('boxes'), list):
            for it in data['boxes']:
                try:
                    lbl = _norm_label(str(it.get('label', '')))
                    bb = it.get('bbox') or it.get('box') or it.get('bbox_xyxy') or it.get('xyxy') or it.get('xywh')
                    if isinstance(bb, (list, tuple)) and len(bb) == 4:
                        boxes.append({'label': (lbl or 'object'), 'bbox': to_xyxy(bb)})
                except Exception:
                    pass
        # boxes: dict 形式 {label: [ {...}, ... ]}
        if isinstance(data.get('boxes'), dict):
            for k, arr in data['boxes'].items():
                lbl = _norm_label(str(k))
                if isinstance(arr, list):
                    for it in arr:
                        try:
                            bb = it.get('bbox') or it.get('box') or it.get('bbox_xyxy') or it.get('xyxy') or it.get('xywh')
                            if isinstance(bb, (list, tuple)) and len(bb) == 4:
                                boxes.append({'label': (lbl or 'object'), 'bbox': to_xyxy(bb)})
                        except Exception:
                            pass
        # bboxes: dict 形式 {label: [[...], ...]}
        if isinstance(data.get('bboxes'), dict):
            for k, v in data['bboxes'].items():
                lbl = _norm_label(str(k))
                if isinstance(v, list):
                    for bb in v:
                        try:
                            if isinstance(bb, (list, tuple)) and len(bb) == 4:
                                boxes.append({'label': (lbl or 'object'), 'bbox': to_xyxy(bb)})
                        except Exception:
                            pass
        # objects: list 形式
        if isinstance(data.get('objects'), list):
            for it in data['objects']:
                try:
                    lbl = _norm_label(str(it.get('label', '')))
                    bb = it.get('bbox') or it.get('box') or it.get('bbox_xyxy') or it.get('xyxy') or it.get('xywh')
                    if isinstance(bb, (list, tuple)) and len(bb) == 4:
                        boxes.append({'label': (lbl or 'object'), 'bbox': to_xyxy(bb)})
                except Exception:
                    pass
        # COCO-like: categories + annotations
        cats: Dict[int, str] = {}
        if isinstance(data.get('categories'), list):
            for it in data['categories']:
                try:
                    cid = int(it.get('id'))
                    cats[cid] = _norm_label(str(it.get('name', '')))
                except Exception:
                    pass
        if isinstance(data.get('annotations'), list):
            for it in data['annotations']:
                try:
                    bb = it.get('bbox') or it.get('box')
                    if not (isinstance(bb, (list, tuple)) and len(bb) == 4):
                        continue
                    lbl = it.get('category') or it.get('label')
                    if not lbl and isinstance(it.get('category_id'), (int, float)):
                        lbl = cats.get(int(it['category_id']), '')
                    lbl = _norm_label(str(lbl or 'object'))
                    boxes.append({'label': lbl, 'bbox': to_xyxy(bb)})
                except Exception:
                    pass
        # LabelMe: shapes points -> bbox
        if isinstance(data.get('shapes'), list):
            for it in data['shapes']:
                try:
                    lbl = _norm_label(str(it.get('label', '')))
                    pts = it.get('points')
                    if isinstance(pts, list) and len(pts) >= 2:
                        xs = [float(p[0]) for p in pts if isinstance(p, (list, tuple)) and len(p) >= 2]
                        ys = [float(p[1]) for p in pts if isinstance(p, (list, tuple)) and len(p) >= 2]
                        if xs and ys:
                            x1, y1, x2, y2 = min(xs), min(ys), max(xs), max(ys)
                            boxes.append({'label': (lbl or 'object'), 'bbox': [x1, y1, x2, y2]})
                except Exception:
                    pass
        # 通用数组键：result/detections/predictions
        for key in ('result', 'detections', 'predictions'):
            if isinstance(data.get(key), list):
                for it in data[key]:
                    try:
                        lbl = _norm_label(str(it.get('label') or it.get('name') or it.get('category') or ''))
                        bb = it.get('bbox') or it.get('box') or it.get('bbox_xyxy') or it.get('xyxy') or it.get('xywh')
                        if isinstance(bb, (list, tuple)) and len(bb) == 4:
                            boxes.append({'label': (lbl or 'object'), 'bbox': to_xyxy(bb)})
                        pts = it.get('points') or it.get('poly')
                        if isinstance(pts, list) and len(pts) >= 2:
                            xs = [float(p[0]) for p in pts if isinstance(p, (list, tuple)) and len(p) >= 2]
                            ys = [float(p[1]) for p in pts if isinstance(p, (list, tuple)) and len(p) >= 2]
                            if xs and ys:
                                x1, y1, x2, y2 = min(xs), min(ys), max(xs), max(ys)
                                boxes.append({'label': (lbl or 'object'), 'bbox': [x1, y1, x2, y2]})
                    except Exception:
                        pass
        # counts 合成：优先使用显式 counts
        if isinstance(data.get('counts'), dict):
            for k, v in data['counts'].items():
                try:
                    counts[_norm_label(str(k))] = int(v)
                except Exception:
                    pass

    # 由 boxes 汇总 counts；若仍无，则尝试顶层 {label:int}
    if boxes and not counts and isinstance(data, dict):
        for b in boxes:
            lbl = b.get('label') or 'object'
            counts[lbl] = counts.get(lbl, 0) + 1
    if not boxes and not counts and isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, int):
                counts[_norm_label(str(k))] = int(v)

    return counts, boxes, img_size


def spatial_summary(boxes: List[Dict[str, Any]], img_size: Tuple[int, int] | None) -> Dict[str, Any]:
    """将空间信息聚合为 3×3 网格计数。返回：{'grid3x3': [[...],[...],[...]], 'image_size': {...}}"""
    w, h = (img_size or (1, 1))
    grid = [[0,0,0],[0,0,0],[0,0,0]]  # rows: 0=front,1=mid,2=back; cols: 0=left,1=mid,2=right
    if not boxes:
        return {'grid3x3': grid, 'image_size': {'width': w, 'height': h}}

    def idx_of(bb: List[float]) -> Tuple[int, int]:
        x1, y1, x2, y2 = bb
        cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        nx, ny = cx / max(1.0, float(w)), cy / max(1.0, float(h))
        col = 0 if nx < 1/3 else (1 if nx < 2/3 else 2)
        row = 0 if ny < 1/3 else (1 if ny < 2/3 else 2)
        return row, col

    for b in boxes:
        bb = b.get('bbox')
        if isinstance(bb, (list, tuple)) and len(bb) == 4:
            r, c = idx_of([float(bb[0]), float(bb[1]), float(bb[2]), float(bb[3])])
            grid[r][c] += 1
    return {'grid3x3': grid, 'image_size': {'width': w, 'height': h}}


def load_counts(path: str | None) -> Dict[str, Any]:
    if not path:
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def infer_counts_path(image_path: str) -> Optional[str]:
    base, _ = os.path.splitext(image_path)
    cand = base + "_counts.json"
    return cand if os.path.exists(cand) else None


def rule_based_summary(counts: Dict[str, Any]) -> str:
    # 一个非常简单的规则引擎示例，可按需强化
    upright = int(counts.get(' upright ', 0) or counts.get('upright', 0))
    bow = int(counts.get(' bow_head ', 0) or counts.get('bow_head', 0))
    phone = int(counts.get(' Using_phone ', 0) or counts.get('using_phone', 0))
    reading = int(counts.get(' reading ', 0) or counts.get('reading', 0))
    total = max(1, upright + bow + phone + reading)
    bow_rate = bow / total * 100
    phone_rate = phone / total * 100
    lines = []
    lines.append("[规则引擎初步评估]")
    lines.append(f"总样本：{total}，低头率约 {bow_rate:.1f}% ，看手机约 {phone_rate:.1f}%")
    if phone_rate >= 10:
        lines.append("发现较多使用手机行为，建议提醒注意课堂纪律与任务聚焦。")
    if bow_rate >= 30:
        lines.append("低头比例偏高，可能在记笔记/走神或设备操作，建议加快节奏或引入互动。")
    if reading > 0:
        lines.append("存在阅读行为，可能为跟随课堂材料，建议观察是否与教学任务一致。")
    if upright / total >= 0.6:
        lines.append("多数同学处于端正状态，整体专注度尚可。")
    return "\n".join(lines)


def build_prompt(counts: Dict[str, Any], custom_prompt: Optional[str]) -> str:
    head = custom_prompt.strip() if custom_prompt else DEFAULT_PROMPT
    if counts:
        try:
            counts_str = json.dumps(counts, ensure_ascii=False)
        except Exception:
            counts_str = str(counts)
        head += "\n\n以下是针对该画面的计数字段(JSON)：\n" + counts_str + "\n"
    return head


def main():
    ap = argparse.ArgumentParser(description='课堂行为 AI 分析（图片 + 可选计数JSON）')
    ap.add_argument('--image', help='图片路径（可选；若提供则走多模态）')
    ap.add_argument('--counts', help='计数JSON路径（可选，未提供时尝试同名 *_counts.json）')
    ap.add_argument('--det-json', help='检测JSON路径（可选，包含每个标签框及其位置信息）')
    ap.add_argument('--prompt', help='自定义 Prompt（覆盖默认）')
    ap.add_argument('--out', help='将结果写入 Markdown 文件')
    ap.add_argument('--no-ai', action='store_true', help='仅使用规则引擎，禁用大模型')
    ap.add_argument('--json-only', action='store_true', help='强制严格 JSON 输出（用于后续可视化）')
    ap.add_argument('--json-out', help='将 AI JSON 结果另存为此文件（配合 --json-only 使用）')
    ap.add_argument('--viz', nargs='?', const='auto', help='从 JSON 结果生成 PNG 可视化；值为输出路径（缺省为同名 _summary.png）')
    ap.add_argument('--title', default='课堂行为分析', help='可视化图标题（与 --viz 一起使用）')
    args = ap.parse_args()

    if not args.image and not args.det_json and not args.counts:
        raise SystemExit('请至少提供 --image 或 --det-json 或 --counts 之一')

    counts: Dict[str, Any] = {}
    boxes: List[Dict[str, Any]] = []
    img_size_from_json: Tuple[int, int] | None = None
    counts_path = None

    # 优先从检测 JSON 解析
    if args.det_json:
        c2, b2, img_size_from_json = parse_detection_json(args.det_json)
        counts.update(c2)
        boxes = b2
    # 其次加载计数 JSON
    if args.counts:
        counts_path = args.counts
    elif args.image:
        counts_path = infer_counts_path(args.image)
    counts_loaded = load_counts(counts_path)
    for k, v in counts_loaded.items():
        if isinstance(v, int):
            counts[k] = counts.get(k, 0) + int(v)

    # 规则引擎输出（始终可用）
    rb = rule_based_summary(counts)

    # 若禁用 AI，则直接输出规则引擎结果
    if args.no_ai or AIClient is None:
        out = rb
        if args.out:
            with open(args.out, 'w', encoding='utf-8') as f:
                f.write(out)
        print(out)
        return

    # 启用 AI：加载图片并调用现有多模态接口
    img = None
    if args.image:
        try:
            img = Image.open(args.image).convert('RGB')
        except Exception as e:
            raise SystemExit(f'无法打开图片: {e}')

    client = AIClient()
    if not client.ready:
        # 回退
        out = rb + "\n\n[提示] AI 客户端未就绪（缺少密钥或依赖），已回退到规则引擎。"
        if args.out:
            with open(args.out, 'w', encoding='utf-8') as f:
                f.write(out)
        print(out)
        return

    # 组合空间概览，避免将全部 bbox 塞入 Prompt
    sp = spatial_summary(boxes, img_size_from_json)
    # 计算学生总数（head）：优先使用显式 counts['head']，否则汇总 counts 的整数值
    try:
        head_count = None
        if isinstance(counts, dict) and 'head' in counts and isinstance(counts.get('head'), int):
            head_count = int(counts.get('head'))
        else:
            s = 0
            for v in counts.values():
                try:
                    if isinstance(v, int):
                        s += int(v)
                except Exception:
                    pass
            head_count = s if s > 0 else None
    except Exception:
        head_count = None
    # 构建 prompt：可选择严格 JSON 模式
    if args.json_only:
        head = build_json_only_prompt(args.prompt)
    else:
        head = build_prompt(counts, args.prompt)
    # 将学生总数注入 Prompt（便于模型参考），以 'head' 字段标识
    if head_count is not None:
        head += f"\n\n学生总数 (head): {head_count}\n"
    if sp:
        try:
            sp_str = json.dumps(sp, ensure_ascii=False)
        except Exception:
            sp_str = str(sp)
        head += "\n\n以下为检测框的空间分布（3x3 区域计数）JSON：\n" + sp_str + "\n"

    if img is not None:
        res = client.analyze_image(img, head)
    else:
        # 仅文本分析
        messages = []
        messages.append({'role': 'user', 'content': [{'type': 'text', 'text': head}]})
        res = client.chat(messages)
    if 'content' in res:
        meta = res.get('meta') or {}
        head_out = [
            "# 课堂行为分析（AI）",
            "",
            "## 规则引擎初步",
            rb,
            "",
            "## AI 详细分析",
            res['content'],
            "",
            "## 元信息",
            f"原始尺寸: {meta.get('orig')}  缩放后: {meta.get('resized')}  比例: {meta.get('ratio')}  格式: {meta.get('format')}  大小: {meta.get('bytes')}B" if meta else "(文本分析，无图像元信息)",
        ]
        out = "\n".join(head_out)

        # 如需导出 JSON 与可视化（针对 --json-only 场景）
        if args.json_only and (args.json_out or args.viz):
            raw = res['content'] or ''
            parsed: Optional[Dict[str, Any]] = None
            try:
                parsed = json.loads(raw)
            except Exception:
                # 尝试从文本中提取 JSON
                def _try_extract_json(text: str):
                    try:
                        import re
                        m = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", text, re.IGNORECASE)
                        if not m:
                            m = re.search(r"```\s*(\{[\s\S]*?\})\s*```", text, re.IGNORECASE)
                        if m:
                            return json.loads(m.group(1))
                    except Exception:
                        pass
                    try:
                        first = text.find('{')
                        while first != -1:
                            depth = 0; in_str = False; esc = False
                            for i in range(first, len(text)):
                                ch = text[i]
                                if in_str:
                                    if esc:
                                        esc = False
                                    elif ch == '\\':
                                        esc = True
                                    elif ch == '"':
                                        in_str = False
                                else:
                                    if ch == '"':
                                        in_str = True
                                    elif ch == '{':
                                        depth += 1
                                    elif ch == '}':
                                        depth -= 1
                                        if depth == 0:
                                            cand = text[first:i+1]
                                            try:
                                                return json.loads(cand)
                                            except Exception:
                                                break
                            first = text.find('{', first + 1)
                    except Exception:
                        pass
                    return None
                parsed = _try_extract_json(raw)
            if parsed is not None:
                # 导出 JSON
                json_path_out = None
                if args.json_out:
                    json_path_out = os.path.abspath(args.json_out)
                    try:
                        # 注入 provenance: AI（文本或视觉）
                        if isinstance(parsed, dict):
                            # provenance
                            if 'provenance' not in parsed or not isinstance(parsed.get('provenance'), dict):
                                parsed['provenance'] = {
                                    'generated_by': 'ai',
                                    'model': getattr(client, 'model_vision', '') if img is not None else getattr(client, 'model_text', ''),
                                    'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
                                }
                            # 若模型未提供 head 字段，注入基于 counts 的估计（便于可视化与下游使用）
                            try:
                                if 'head' not in parsed or not isinstance(parsed.get('head'), int):
                                    if head_count is not None:
                                        parsed['head'] = int(head_count)
                            except Exception:
                                pass
                        with open(json_path_out, 'w', encoding='utf-8') as f:
                            f.write(json.dumps(parsed, ensure_ascii=False, indent=2))
                    except Exception as e:
                        print(f"[警告] 写入 JSON 失败: {e}")
                        json_path_out = None
                # 可视化
                if args.viz:
                    try:
                        # 延迟导入以避免非必要依赖
                        from student_behavior_ai.visualize import render_report_image
                        if args.viz == 'auto':
                            if json_path_out:
                                base, _ = os.path.splitext(json_path_out)
                                png_out = base + '_summary.png'
                            else:
                                png_out = os.path.abspath('report_summary.png')
                        else:
                            png_out = os.path.abspath(args.viz)
                        render_report_image(parsed, png_out, title=args.title)
                        print(f"[可视化] 已生成: {png_out}")
                    except Exception as e:
                        print(f"[警告] 生成可视化失败: {e}")
    else:
        out = rb + f"\n\n[错误] AI 调用失败: {res.get('error')}"

    # 若 AI 未就绪或未调用到（上面已 return 的分支除外），在严格 JSON 模式下可生成本地回退 JSON
    if (args.no_ai or not client.ready) and args.json_only and (args.json_out or args.viz):
        # 构造回退 JSON（与 UI 保持一致的 schema v1.1）
        sp = spatial_summary(boxes, img_size_from_json)
        try:
            iw, ih = img.size if img is not None else (0, 0)
        except Exception:
            iw, ih = (0, 0)
        fallback = {
            'schema_version': '1.1',
            'summary': '（规则）基于检测计数与空间分布的初步整理',
            'observations': [],
            'metrics': {
                'head_down_rate': None,
                'phone_usage_rate': None,
                'reading_rate': None,
                'hand_raise_rate': None,
                'looking_around_rate': None,
                'writing_rate': None,
                'sleeping_rate': None,
                'distracted_rate': None,
                'interaction_level': 'medium',
                'focus_score': 0,
                'activity_score': 0,
            },
            'per_class': {k: {'count': int(v), 'rate': None} for k, v in (counts or {}).items()},
            'spatial': sp or {},
            'risks': [],
            'suggestions': [],
            'limitations': ['AI 未就绪，使用输入检测 JSON 的计数与空间分布直接整理；数值仅供参考'],
            'confidence': 'low',
            'source': {
                'image_path': os.path.abspath(args.image) if args.image else '',
                'image_size': {'width': (img_size_from_json or (iw, ih))[0] if (img_size_from_json or (iw, ih)) else 0, 'height': (img_size_from_json or (iw, ih))[1] if (img_size_from_json or (iw, ih)) else 0},
            },
            'provenance': {
                'generated_by': 'local_fallback',
                'model': '',
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
            }
        }
        # 写 JSON（如指定）
        if args.json_out:
            try:
                with open(os.path.abspath(args.json_out), 'w', encoding='utf-8') as f:
                    f.write(json.dumps(fallback, ensure_ascii=False, indent=2))
                print(f"[回退] 已写入 JSON: {os.path.abspath(args.json_out)}")
            except Exception as e:
                print(f"[警告] 写入回退 JSON 失败: {e}")
        # 可视化（如指定）
        if args.viz:
            try:
                from student_behavior_ai.visualize import render_report_image
                png_out = os.path.abspath('report_summary.png') if args.viz == 'auto' else os.path.abspath(args.viz)
                render_report_image(fallback, png_out, title=args.title)
                print(f"[回退可视化] 已生成: {png_out}")
            except Exception as e:
                print(f"[警告] 回退可视化失败: {e}")

    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            f.write(out)
    print(out)


if __name__ == '__main__':
    main()
