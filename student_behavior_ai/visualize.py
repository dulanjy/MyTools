from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Tuple
import re

from PIL import Image, ImageDraw, ImageFont


def _load_font(prefer_chinese: bool = True, size: int = 18) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = []
    if prefer_chinese and os.name == 'nt':
        # Windows 常见中文字体
        candidates = [
            r"C:\\Windows\\Fonts\\msyh.ttc",  # 微软雅黑
            r"C:\\Windows\\Fonts\\msyh.ttf",
            r"C:\\Windows\\Fonts\\simhei.ttf",  # 黑体
            r"C:\\Windows\\Fonts\\simfang.ttf",
        ]
    else:
        # 常见跨平台中文字体路径（不保证存在）
        candidates = [
            "/System/Library/Fonts/STHeiti Light.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _measure(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> Tuple[int, int]:
    # 统一测量文本尺寸，兼容不同 Pillow 版本
    if hasattr(draw, 'textbbox'):
        try:
            l, t, r, b = draw.textbbox((0, 0), text, font=font)
            return r - l, b - t
        except Exception:
            pass
    if hasattr(font, 'getbbox'):
        try:
            l, t, r, b = font.getbbox(text)
            return r - l, b - t
        except Exception:
            pass
    if hasattr(font, 'getsize'):
        try:
            return font.getsize(text)
        except Exception:
            pass
    # 兜底估算
    sz = getattr(font, 'size', 16)
    return max(1, int(len(text) * sz * 0.6)), int(sz * 1.2)


def _draw_multiline(draw: ImageDraw.ImageDraw, text: str, xy: Tuple[int, int], font: ImageFont.ImageFont, fill=(20, 20, 20), max_width: int = 760, line_gap: int = 4) -> int:
    # 简易自动换行
    x, y = xy
    words = list(text)
    line = ''
    width_used = 0
    _, lh = _measure(draw, 'Hg', font)
    for ch in words:
        w, _ = _measure(draw, line + ch, font)
        if x + w - xy[0] > max_width:
            draw.text((x, y), line, font=font, fill=fill)
            y += lh + line_gap
            line = ch
        else:
            line += ch
    if line:
        draw.text((x, y), line, font=font, fill=fill)
        y += lh + line_gap
    return y


def _bar_color(kind: str, value: int) -> Tuple[int, int, int]:
    # kind: 'positive' 越高越好, 'negative' 越高越差, 'neutral'
    v = max(0, min(100, int(value)))
    if kind == 'positive':
        # 红(低) -> 绿(高)
        r = int(255 * (100 - v) / 100)
        g = int(180 + 75 * v / 100)
        b = 80
        return (r, g, b)
    elif kind == 'negative':
        # 绿(低) -> 红(高)
        g = int(200 * (100 - v) / 100)
        r = int(160 + 95 * v / 100)
        b = 80
        return (r, g, b)
    return (60, 150, 220)


def _rounded_rect(draw: ImageDraw.ImageDraw, box, radius: int, fill):
    # 兼容 Pillow 版本：无 rounded_rectangle 时用普通 rectangle 回退
    if hasattr(draw, 'rounded_rectangle'):
        try:
            draw.rounded_rectangle(box, radius=radius, fill=fill)
            return
        except Exception:
            pass
    draw.rectangle(box, fill=fill)


def _draw_bar(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, pct: int, kind: str) -> None:
    # 背景条
    _rounded_rect(draw, (x, y, x + w, y + h), radius=h // 2, fill=(235, 235, 235))
    # 前景条
    v = max(0, min(100, int(pct)))
    fw = int(w * v / 100)
    _rounded_rect(draw, (x, y, x + fw, y + h), radius=h // 2, fill=_bar_color(kind, v))


def _pill(draw: ImageDraw.ImageDraw, text: str, xy: Tuple[int, int], font: ImageFont.ImageFont, fg=(255, 255, 255), bg=(80, 140, 240), pad_x: int = 10, pad_y: int = 4) -> Tuple[int, int]:
    x, y = xy
    tw, th = _measure(draw, text, font)
    rect = (x, y, x + tw + pad_x * 2, y + th + pad_y * 2)
    _rounded_rect(draw, rect, radius=(th // 2 + pad_y), fill=bg)
    draw.text((x + pad_x, y + pad_y), text, font=font, fill=fg)
    return rect[2], rect[3]


def render_report_image(data: Dict[str, Any], out_path: str, title: str = "课堂行为分析", width: int = 1000, height: int = 700) -> str:
    # 画布
    im = Image.new('RGB', (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(im)

    # 字体
    font_title = _load_font(size=28)
    font_h = _load_font(size=20)
    font_p = _load_font(size=18)
    font_s = _load_font(size=16)

    margin = 24
    x = margin
    y = margin

    # 标题与时间
    draw.text((x, y), title, font=font_title, fill=(30, 30, 30))
    ts = datetime.now().strftime('%Y-%m-%d %H:%M')
    tw, _ = _measure(draw, ts, font_s)
    draw.text((width - margin - tw, y + 8), ts, font=font_s, fill=(120, 120, 120))
    y += 40

    # 一句话概括 + 置信度 + 互动级别 pill
    summary = str(data.get('summary') or '（无摘要）')
    confidence = str(data.get('confidence') or 'unknown')
    interaction = str(((data.get('metrics') or {}).get('interaction_level')) or 'unknown')
    y = _draw_multiline(draw, f"摘要：{summary}", (x, y), font_p, max_width=width - 2 * margin)
    # 小行：置信度 与 互动级别
    y += 2
    _, y2 = _pill(draw, f"置信度: {confidence}", (x, y), font_s, bg=(130, 130, 130))
    _pill(draw, f"互动: {interaction}", (x + 160, y), font_s, bg=(80, 140, 240))
    y = y2 + 12

    # 左侧：关键要点 + 风险/建议
    col_gap = 20
    left_w = int((width - 2 * margin - col_gap) * 0.48)
    right_w = width - 2 * margin - col_gap - left_w
    left_x = x
    right_x = x + left_w + col_gap

    # 关键要点
    draw.text((left_x, y), '关键观察要点', font=font_h, fill=(40, 40, 40))
    y1 = y + 28
    obs = data.get('observations') or []
    if isinstance(obs, list) and obs:
        for o in obs[:6]:
            y1 = _draw_multiline(draw, f"• {str(o)}", (left_x, y1), font_p, max_width=left_w)
    else:
        y1 = _draw_multiline(draw, "• （无）", (left_x, y1), font_p, max_width=left_w)

    # 风险与建议
    y2 = y
    draw.text((right_x, y2), '风险与建议', font=font_h, fill=(40, 40, 40))
    y2 += 28
    risks = data.get('risks') or []
    suggs = data.get('suggestions') or []
    y2 = _draw_multiline(draw, '风险：', (right_x, y2), font_p, max_width=right_w)
    if isinstance(risks, list) and risks:
        for r in risks[:4]:
            y2 = _draw_multiline(draw, f"- {str(r)}", (right_x + 12, y2), font_p, max_width=right_w - 12)
    else:
        y2 = _draw_multiline(draw, "- （无）", (right_x + 12, y2), font_p, max_width=right_w - 12)
    y2 = _draw_multiline(draw, '建议：', (right_x, y2 + 6), font_p, max_width=right_w)
    if isinstance(suggs, list) and suggs:
        for s in suggs[:5]:
            y2 = _draw_multiline(draw, f"- {str(s)}", (right_x + 12, y2), font_p, max_width=right_w - 12)
    else:
        y2 = _draw_multiline(draw, "- （无）", (right_x + 12, y2), font_p, max_width=right_w - 12)

    # 指标与评分（下半)
    y = max(y1, y2) + 12
    draw.line((margin, y, width - margin, y), fill=(230, 230, 230), width=2)
    y += 16
    draw.text((left_x, y), '指标评估（%）', font=font_h, fill=(40, 40, 40))
    draw.text((right_x, y), '评分', font=font_h, fill=(40, 40, 40))
    y += 30

    metrics = (data.get('metrics') or {})
    # 左：五项指标条
    bar_specs = [
        ('低头率', 'head_down_rate', 'negative'),
        ('看手机', 'phone_usage_rate', 'negative'),
        ('阅读', 'reading_rate', 'positive'),
        ('举手/发言', 'hand_raise_rate', 'positive'),
        ('分心', 'distracted_rate', 'negative'),
    ]
    bar_x = left_x
    bar_y = y
    bar_w = left_w
    bar_h = 18
    bar_gap = 14
    for label, key, kind in bar_specs:
        val = metrics.get(key)
        pct = int(val) if isinstance(val, (int, float)) else 0
        _draw_bar(draw, bar_x, bar_y, bar_w, bar_h, pct, kind)
        draw.text((bar_x + 6, bar_y - 2), f"{label}", font=font_s, fill=(60, 60, 60))
        tw, _ = _measure(draw, f"{pct}%", font_s)
        draw.text((bar_x + bar_w - tw - 6, bar_y - 2), f"{pct}%", font=font_s, fill=(60, 60, 60))
        bar_y += bar_h + bar_gap

    # 右：评分条（0~100）
    score_specs = [
        ('专注度', 'focus_score', 'positive'),
        ('活跃度', 'activity_score', 'positive'),
    ]
    s_x = right_x
    s_y = y
    s_w = right_w
    s_h = 22
    s_gap = 18
    for label, key, kind in score_specs:
        val = metrics.get(key)
        pct = int(val) if isinstance(val, (int, float)) else 0
        _draw_bar(draw, s_x, s_y, s_w, s_h, pct, kind)
        draw.text((s_x + 8, s_y - 2), f"{label}", font=font_s, fill=(60, 60, 60))
        tw, _ = _measure(draw, f"{pct}", font_s)
        draw.text((s_x + s_w - tw - 8, s_y - 2), f"{pct}", font=font_s, fill=(60, 60, 60))
        s_y += s_h + s_gap

    # 局限性（左对齐显示于底部）
    y = max(bar_y, s_y) + 8
    draw.line((margin, y, width - margin, y), fill=(235, 235, 235), width=2)
    y += 12
    limits = data.get('limitations') or []
    draw.text((left_x, y), '局限性与说明', font=font_h, fill=(40, 40, 40))
    y += 28
    if isinstance(limits, list) and limits:
        for lm in limits[:4]:
            y = _draw_multiline(draw, f"- {str(lm)}", (left_x, y), font=font_p, max_width=width - 2 * margin)
    else:
        y = _draw_multiline(draw, "- （无）", (left_x, y), font=font_p, max_width=width - 2 * margin)

    # 保存
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    im.save(out_path, format='PNG')
    return out_path


def render_report_image_from_file(json_path: str, out_path: str, title: str = "课堂行为分析") -> str:
    with open(json_path, 'r', encoding='utf-8') as f:
        text = f.read()
    # 先尝试直接解析
    try:
        data = json.loads(text)
    except Exception:
        # 兼容带 wrapper 或说明文本的情况：尝试提取 fenced 或最大花括号块
        def _extract_json_from_text(t: str):
            # 1) ```json { ... } ``` 或 ``` { ... } ```
            try:
                m = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", t, re.IGNORECASE)
                if not m:
                    m = re.search(r"```\s*(\{[\s\S]*?\})\s*```", t, re.IGNORECASE)
                if m:
                    return json.loads(m.group(1))
            except Exception:
                pass
            # 2) 扫描最大平衡花括号块
            try:
                first = t.find('{')
                while first != -1:
                    depth = 0
                    in_str = False
                    esc = False
                    for i in range(first, len(t)):
                        ch = t[i]
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
                                    cand = t[first:i+1]
                                    try:
                                        return json.loads(cand)
                                    except Exception:
                                        break
                    first = t.find('{', first + 1)
            except Exception:
                pass
            return None
        data = _extract_json_from_text(text)
        if data is None:
            raise ValueError('无法从文件内容提取有效 JSON，请确认文件是合法 JSON 或使用严格 JSON 模板导出。')
    if not isinstance(data, dict):
        raise ValueError('JSON 顶层必须为对象')
    return render_report_image(data, out_path, title=title)


def _main():
    import argparse
    ap = argparse.ArgumentParser(description='将课堂行为分析 JSON 渲染为 PNG 摘要图')
    ap.add_argument('--json', required=True, help='JSON 文件路径')
    ap.add_argument('--out', required=False, help='输出 PNG 路径（默认同名 .png）')
    ap.add_argument('--title', default='课堂行为分析', help='图像标题')
    args = ap.parse_args()
    inp = os.path.abspath(args.json)
    outp = args.out or os.path.splitext(inp)[0] + '_summary.png'
    outp = os.path.abspath(outp)
    path = render_report_image_from_file(inp, outp, title=args.title)
    print(f'已生成: {path}')


if __name__ == '__main__':
    _main()
#python .\student_behavior_ai\visualize.py --json C:\Users\hp1\Desktop\MyTools\screen_capture\predict\1.json --out .\report_summary.png --title "课堂行为分析"