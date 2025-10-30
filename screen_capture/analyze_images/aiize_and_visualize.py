from __future__ import annotations
import os, sys, json
from typing import Optional, Dict, Any

# 确保项目根目录在 sys.path
HERE = os.path.abspath(os.path.dirname(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# 项目内依赖（在插入 sys.path 后导入）
try:
    from screen_capture.ai_client import AIClient
except Exception:
    AIClient = None  # type: ignore

try:
    from student_behavior_ai.visualize import render_report_image
except Exception as e:
    print(f"[错误] 无法导入可视化模块: {e}")
    sys.exit(1)


def build_strict_json_prompt(base_prompt: Optional[str]) -> str:
    head = (base_prompt.strip() + "\n\n") if base_prompt else ''
    rules = (
        '请严格遵守：\n'
        '- 仅输出一个 JSON 对象，且不包含任何 Markdown、前后缀文本或注释；\n'
        '- 所有百分比或评分统一为 0~100 的整数；无法判断时使用 null；\n'
        '- interaction_level 取值必须是 "low"、"medium" 或 "high"；\n'
        '- per_class 仅包含实际出现的标签；rate 不确定可设为 null；\n'
        '- 不要逐条罗列检测框，聚焦总体归类与显著现象；\n'
        '- 若与输入数据矛盾，请在 limitations 简述原因与取舍依据。\n\n'
        '输出格式（示例模板，请用实际值替换；示例中的值均可被覆盖）：\n'
        '{\n'
        '  "schema_version": "1.1",\n'
        '  "summary": "",\n'
        '  "observations": [],\n'
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
        '  "risks": [],\n'
        '  "suggestions": [],\n'
        '  "limitations": [],\n'
        '  "confidence": "medium",\n'
        '  "source": {"image_path": "", "image_size": {"width": 0, "height": 0}}\n'
        '}\n'
    )
    return head + rules


def extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    # 直接尝试
    try:
        return json.loads(text)
    except Exception:
        pass
    # fenced block
    try:
        import re
        m = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", text, re.IGNORECASE)
        if not m:
            m = re.search(r"```\s*(\{[\s\S]*?\})\s*```", text, re.IGNORECASE)
        if m:
            return json.loads(m.group(1))
    except Exception:
        pass
    # 最大平衡花括号
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


def main():
    if len(sys.argv) < 2:
        print('用法: python aiize_and_visualize.py <json_path> [title]')
        sys.exit(2)
    in_path = os.path.abspath(sys.argv[1])
    title = sys.argv[2] if len(sys.argv) >= 3 else '课堂行为分析（AI 规整）'
    if not os.path.exists(in_path):
        print(f'[错误] 文件不存在: {in_path}')
        sys.exit(2)
    with open(in_path, 'r', encoding='utf-8') as f:
        src_obj = json.load(f)
    src_text = json.dumps(src_obj, ensure_ascii=False, indent=2)

    # 目标输出路径：强制到 screen_capture/analyze_images 目录
    out_dir = os.path.dirname(in_path)
    try:
        os.makedirs(out_dir, exist_ok=True)
    except Exception:
        pass
    stem = os.path.splitext(os.path.basename(in_path))[0]
    base = os.path.join(out_dir, stem)
    out_json = base + '_ai.json'
    out_png = base + '_summary.png'

    # AI 规整
    parsed: Optional[Dict[str, Any]] = None
    client = AIClient() if AIClient is not None else None  # type: ignore
    if client is not None and client.ready:
        prompt = build_strict_json_prompt('以下为已有的课堂分析 JSON，请规整为严格 JSON (schema v1.1)：\n') + '\n原始 JSON：\n' + src_text + '\n'
        res = client.chat([{ 'role': 'user', 'content': [{ 'type': 'text', 'text': prompt }] }])
        if 'content' in res:
            parsed = extract_json_from_text(res['content'] or '')
            if parsed is None:
                print('[警告] AI 返回非纯 JSON，尝试解析失败，回退到输入 JSON。')
        else:
            print(f"[警告] AI 失败: {res.get('error')}")
    else:
        try:
            # 轻量日志：脚本自身无集中 logger，这里直接打印友好提示
            print('[提示] AI 客户端未就绪（缺少密钥或依赖），本次将直接使用输入 JSON 可视化。')
        except Exception:
            pass

    if parsed is None:
        parsed = src_obj

    # 写出 JSON
    with open(out_json, 'w', encoding='utf-8') as f:
        f.write(json.dumps(parsed, ensure_ascii=False, indent=2))
    print(f'[输出] 已保存 JSON: {out_json}')

    # 可视化
    try:
        render_report_image(parsed, out_png, title=title)
        print(f'[输出] 已保存可视化 PNG: {out_png}')
    except Exception as e:
        print(f'[错误] 生成可视化失败: {e}')
        sys.exit(1)


if __name__ == '__main__':
    main()
