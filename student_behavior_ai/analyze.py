from __future__ import annotations
import argparse, json, os, time
from typing import Dict, Any, Optional, List, Tuple

from PIL import Image

# 复用项目内 AI 客户端
try:
    from screen_capture.ai_client import AIClient
except Exception:
    AIClient = None  # type: ignore

# 可选一致性与富化处理：根据 per_class/head 生成 observations/risks/suggestions 等
try:
    from student_behavior_ai.postprocess import enrich_consistency  # type: ignore
except Exception:
    enrich_consistency = None  # type: ignore


DEFAULT_PROMPT = (
    "你是一名教学观察与课堂行为分析助手。使用简体中文回答。若提供了结构化 JSON（检测/统计/已有分析），"
    "必须以 JSON 为主、图片为辅进行判断；冲突时优先保留 JSON 结论，并在 limitations 说明依据。"
    "请按如下结构输出一份简明的 Markdown 报告（面向老师阅读；前端仅重点展示‘关键观察要点’与‘局限性’）：\n\n"
    "1) 关键观察要点\n"
    "   - 用项目符号列出 4~8 条；每条尽量 ≤30 字，结合计数或 3×3 空间分布（前/中/后、左/中/右），"
    "并包含‘位置/行为/比例’等中的至少两项信息（如：中排右侧低头 3/6 ≈50%）。\n"
    "2) 指标评估（给出 0~100 的整数及一句话依据）\n"
    "   - 低头率/看手机/阅读/书写/举手/环顾/打瞌睡/分心；互动密度（low/medium/high）；专注度与活跃度评分。\n"
    "3) 风险与建议（可简要）\n"
    "   - 风险点 2~4 条；建议 3~6 条，围绕节奏/互动/座位/规范等。避免空泛与与场景无关的内容。\n"
    "4) 局限性与说明\n"
    "   - 明确遮挡/分辨率/单帧等局限；如与 JSON 冲突，优先 JSON 并说明原因；避免臆测与百科式表述。"
)

def build_json_only_prompt(base_prompt: Optional[str]) -> str:
    """构造更严格的 JSON 输出系统提示（加码版）。

    目标：当提供 counts/spatial 等结构化数据时，输出更“实”和“具体”的 schema v1.1 JSON，
    并对数量、取值范围、一致性做出明确约束；若无法满足，必须在 limitations 解释原因。
    """
    head = (base_prompt.strip() + "\n\n") if base_prompt else ''
    schema = (
        '只输出一个 JSON 对象（UTF-8，合法 JSON，无注释、无多余文本、无 Markdown）。\n'
        'JSON 优先规则：\n'
        '- 若提供了结构化 JSON（检测/统计/已有分析），以 JSON 为主、图片为辅；不可见证据不臆测；\n'
        '- 如与图片或直觉冲突，优先保留 JSON 结论，并在 limitations 说明冲突与依据；\n'
        '- 对 counts 中的常见同义请按以下归一：using_phone/use_phone→using_phone；phone/cellphone/mobile_phone→phone；\n'
        '  hand_raising/raise_hand/hands_up→hand_raise；head_down/looking_down/bend→bow_head；note_taking/notetaking→writing；sleep/doze→sleeping。\n\n'
        '前端仅展示 observations 与 limitations 两个板块，请务必完整、具体且客观地填充它们。\n\n'
        '输出字段（schema v1.1）：\n'
        '{\n'
        '  "schema_version": "1.1",\n'
        '  "summary": "一句话概括（≤30字，避免空泛）",\n'
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
        '  "per_class": {},  \n'
        '  "spatial": {"grid3x3": [[0,0,0],[0,0,0],[0,0,0]], "image_size": {"width": 0, "height": 0}},\n'
        '  "risks": ["风险1", "风险2"],\n'
        '  "suggestions": ["建议1", "建议2", "建议3"],\n'
        '  "limitations": ["局限1", "局限2"],\n'
        '  "confidence": "low|medium|high",\n'
        '  "source": {"image_path": "", "image_size": {"width": 0, "height": 0}}\n'
        '}\n\n'
        '数量与取值硬性约束：\n'
        '- 使用简体中文；observations 至少 4 条、至多 8 条；每条为短句（≤30字），结合计数与 3×3 网格突出显著现象，尽量包含“位置/行为/比例”；\n'
        '- risks 至少 2 条、至多 5 条；suggestions 至少 3 条、至多 8 条；\n'
        '- limitations 至少 2 条、至多 8 条；明确数据不确定性、遮挡/分辨率限制、与 grid 或 head 不一致之处及处理口径；避免泛化与百科式描述；\n'
        '- metrics 中除无法判断项外，一律为 0~100 的整数（四舍五入）；interaction_level ∈ {low, medium, high}；\n'
        '- 若已提供 counts/head，则必须据此给出可计算的指标，不得随意置 null；确实无法推断时置 null 并在 limitations 解释原因。\n\n'
        '一致性与派生规则：\n'
        '- 若 counts 提供了行为计数，估算 head（学生总数）：优先 counts.head，否则取主要行为之和；\n'
        '- rate 计算：rate = round( count / max(1, head) × 100 )（整数%）；\n'
        '- distracted_rate 建议与 {head_down_rate, phone_usage_rate, looking_around_rate} 的最大值保持一致或略高，并说明依据；\n'
        '- per_class 可为 {label:int}（计数），或 {label:{"count":int,"rate":int}}（推荐，若 head 已估算）。\n'
        '- 如可确定，请补充 "head": int 与 "人数": int 字段（同值）。\n\n'
        '空间分布约束：\n'
        '- 若提供了 spatial.grid3x3，请据其归纳“前/中/后、左/中/右”的显著聚集/稀疏现象；\n'
        '- 若 grid3x3 与 head/计数明显不一致，请在 limitations 明确指出矛盾与处理口径（参考示例）。\n\n'
        '写作规范：\n'
        '- 仅输出合法 JSON；不要输出 Markdown、解释性文字或额外包裹；\n'
        '- 不要逐条罗列检测框；避免臆测不可见细节；避免涉及可识别个人隐私的描述；不要包含模型/提示词/系统信息；不要自称AI.'
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


def normalize_counts(raw: Dict[str, Any] | None) -> Dict[str, int]:
    """归一化计数键名（去空格/大小写/同义词），合并到标准标签。"""
    out: Dict[str, int] = {}
    if not raw:
        return out
    for k, v in raw.items():
        try:
            n = int(v)
        except Exception:
            continue
        key = _norm_label(str(k))
        out[key] = out.get(key, 0) + n
    return out


def _ratio(n: int, d: int) -> int:
    if d <= 0:
        return 0
    x = int(round((n / d) * 100))
    return max(0, min(100, x))


def derive_metrics(counts: Dict[str, int], head_count: Optional[int]) -> Dict[str, Any]:
    """基于归一化 counts 与 head 估算各类比率与评分。返回 metrics 字典。"""
    c = normalize_counts(counts)
    # 估算总人数：优先 head，否则用主要行为之和
    denom = head_count if isinstance(head_count, int) and head_count > 0 else 0
    if denom <= 0:
        for k in ('upright', 'bow_head', 'reading', 'writing', 'using_phone', 'phone'):
            denom += c.get(k, 0)
    denom = max(denom, 1)

    head_down = c.get('bow_head', 0)
    phone_any = c.get('using_phone', 0) + c.get('phone', 0)
    reading = c.get('reading', 0)
    writing = c.get('writing', 0)
    hand = c.get('hand_raise', 0)
    looking = c.get('turn_head', 0)  # 近似“环顾”
    sleeping = c.get('sleeping', 0)

    head_down_rate = _ratio(head_down, denom)
    phone_rate = _ratio(phone_any, denom)
    reading_rate = _ratio(reading, denom)
    writing_rate = _ratio(writing, denom)
    hand_raise_rate = _ratio(hand, denom)
    looking_rate = _ratio(looking, denom)
    sleeping_rate = _ratio(sleeping, denom)

    # 简单评分：低头/手机越低越好，举手/阅读/书写越高越好
    focus_score = max(0, 100 - int(0.6 * head_down_rate + 0.8 * phone_rate))
    activity_score = min(100, int(0.6 * hand_raise_rate + 0.5 * reading_rate + 0.5 * writing_rate + 0.3 * looking_rate))
    interaction_level = 'high' if hand_raise_rate >= 20 else ('medium' if hand_raise_rate >= 5 else 'low')

    return {
        'head_down_rate': head_down_rate,
        'phone_usage_rate': phone_rate,
        'reading_rate': reading_rate,
        'hand_raise_rate': hand_raise_rate,
        'looking_around_rate': looking_rate,
        'writing_rate': writing_rate,
        'sleeping_rate': sleeping_rate,
        'distracted_rate': max(head_down_rate, phone_rate, looking_rate),
        'interaction_level': interaction_level,
        'focus_score': focus_score,
        'activity_score': activity_score,
    }


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


def rule_based_summary(counts: Dict[str, Any], head_count: Optional[int] = None) -> str:
    """更稳健的规则引擎摘要：归一化计数、给出关键比率与建议。"""
    c = normalize_counts(counts)
    denom = head_count if isinstance(head_count, int) and head_count > 0 else 0
    if denom <= 0:
        denom = sum(c.get(k, 0) for k in ('upright', 'bow_head', 'reading', 'writing', 'using_phone', 'phone'))
    denom = max(denom, 1)

    metrics = derive_metrics(c, denom)

    upright = c.get('upright', 0)
    bow = c.get('bow_head', 0)
    phone_any = c.get('using_phone', 0) + c.get('phone', 0)
    reading = c.get('reading', 0)
    writing = c.get('writing', 0)

    lines: List[str] = []
    lines.append("[规则引擎初步评估]")
    lines.append(
        f"样本估计：{denom} 人；低头 {bow}、看手机 {phone_any}、阅读 {reading}、书写 {writing}、端正 {upright}。")
    lines.append(
        "指标估算：" +
        f"低头率 {metrics['head_down_rate']}% ｜ 手机 {metrics['phone_usage_rate']}% ｜ 阅读 {metrics['reading_rate']}% ｜ "
        f"书写 {metrics['writing_rate']}% ｜ 举手 {metrics['hand_raise_rate']}% ｜ 环顾 {metrics['looking_around_rate']}%")

    if metrics['phone_usage_rate'] >= 15:
        lines.append("手机使用偏多，建议明确课堂任务与设备使用规范，并设置阶段性检查点。")
    if metrics['head_down_rate'] >= 30:
        lines.append("低头比例偏高，可能在记笔记/走神或设备操作，可尝试加快节奏或引入讨论/点名。")
    if metrics['hand_raise_rate'] <= 3 and metrics['focus_score'] < 70:
        lines.append("互动略低且专注度一般，可安排冷启动提问或小组汇报以提升参与度。")
    if metrics['reading_rate'] >= 20 and writing == 0:
        lines.append("阅读较多但书写较少，建议要求关键点勾画/随堂笔记以巩固。")

    return "\n".join(lines)


def build_prompt(counts: Dict[str, Any], custom_prompt: Optional[str], head_count: Optional[int] = None, spatial: Optional[Dict[str, Any]] = None) -> str:
    """构造面向 Markdown 报告的提示词，并注入关键指标与 JSON 优先规则。"""
    head = custom_prompt.strip() if custom_prompt else DEFAULT_PROMPT

    c_norm = normalize_counts(counts)
    if c_norm:
        try:
            counts_str = json.dumps(c_norm, ensure_ascii=False)
        except Exception:
            counts_str = str(c_norm)
        head += "\n\n以下为检测/统计 JSON（已归一化）：\n" + counts_str + "\n"

    # 注入推算指标，帮助模型对齐量化口径
    m = derive_metrics(c_norm, head_count)
    try:
        metrics_str = json.dumps(m, ensure_ascii=False)
    except Exception:
        metrics_str = str(m)
    head += "\n以下为基于 JSON 的指标估算（0~100，供参考）：\n" + metrics_str + "\n"

    # 注入学生总数与空间分布
    if isinstance(head_count, int) and head_count > 0:
        head += f"\n学生总数（head）估计：{head_count}\n"
    if spatial:
        try:
            sp_str = json.dumps(spatial, ensure_ascii=False)
        except Exception:
            sp_str = str(spatial)
        head += "\n以下为 3×3 空间分布计数（JSON）：\n" + sp_str + "\n"

    head += "\n请以 JSON 为主、图片为辅进行判断；当图片与 JSON 冲突时，优先保留 JSON 结论并在 limitations 说明。"
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
    # 在得出 head_count 之前，先用计数粗估；稍后会再次用于 Markdown 汇总
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
        # 在严格 JSON 模式下，仍然注入 head 与空间分布作为参考
        if head_count is not None:
            head += f"\n\n学生总数 (head): {head_count}\n"
        if sp:
            try:
                sp_str = json.dumps(sp, ensure_ascii=False)
            except Exception:
                sp_str = str(sp)
            head += "\n以下为检测框的空间分布（3x3 区域计数）JSON：\n" + sp_str + "\n"
    else:
        head = build_prompt(counts, args.prompt, head_count=head_count, spatial=sp)

    if img is not None:
        res = client.analyze_image(img, head)
    else:
        # 仅文本分析
        messages = []
        messages.append({'role': 'user', 'content': [{'type': 'text', 'text': head}]})
        res = client.chat(messages)
    if 'content' in res:
        meta = res.get('meta') or {}
        # 使用最新 head_count 重新生成规则摘要（确保与上文口径一致）
        rb_now = rule_based_summary(counts, head_count=head_count)
        head_out = [
            "# 课堂行为分析（AI）",
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
        # 估算 head
        c_norm_fallback = normalize_counts(counts) if normalize_counts else (counts or {})
        head_est_fb = None
        try:
            if isinstance(c_norm_fallback, dict):
                if 'head' in c_norm_fallback and isinstance(c_norm_fallback.get('head'), int):
                    head_est_fb = int(c_norm_fallback['head'])
                else:
                    sfb = 0
                    for v in c_norm_fallback.values():
                        if isinstance(v, int):
                            sfb += int(v)
                    head_est_fb = sfb if sfb > 0 else None
        except Exception:
            head_est_fb = None
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
        # 注入 head/人数，便于富化
        try:
            if head_est_fb is not None:
                fallback['head'] = int(head_est_fb)
                fallback['人数'] = int(head_est_fb)
        except Exception:
            pass
        # 富化：自动生成 observations 等（若可用）
        try:
            if enrich_consistency and isinstance(fallback, dict):
                fallback = enrich_consistency(fallback)
        except Exception:
            pass
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
