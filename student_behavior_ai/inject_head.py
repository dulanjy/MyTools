from __future__ import annotations
import argparse, json, os, sys
from typing import Any, Dict

try:
    # 复用归一化逻辑，保证键名一致（using_phone/phone、head_down/bow_head 等）
    from student_behavior_ai.analyze import normalize_counts  # type: ignore
except Exception:
    def normalize_counts(raw: Dict[str, Any] | None) -> Dict[str, int]:  # 兜底：最小实现
        out: Dict[str, int] = {}
        if not raw:
            return out
        def _norm_label(s: str) -> str:
            s2 = (s or '').strip().lower().replace(' ', '_').replace('-', '_')
            alias = {
                'using_phone': 'using_phone', 'use_phone': 'using_phone',
                'phone': 'phone', 'cellphone': 'phone', 'mobile_phone': 'phone',
                'hand_raising': 'hand_raise', 'hand_raise': 'hand_raise', 'raise_hand': 'hand_raise', 'hands_up': 'hand_raise',
                'bow_head': 'bow_head', 'head_down': 'bow_head', 'looking_down': 'bow_head', 'bend': 'bow_head',
                'reading': 'reading', 'book': 'reading',
                'upright': 'upright', 'turn_head': 'turn_head', 'raise_head': 'raise_head',
                'writing': 'writing', 'note_taking': 'writing', 'notetaking': 'writing',
                'sleep': 'sleeping', 'sleeping': 'sleeping', 'doze': 'sleeping',
            }
            return alias.get(s2, s2)
        for k, v in raw.items():
            try:
                n = int(v)
            except Exception:
                continue
            key = _norm_label(str(k))
            out[key] = out.get(key, 0) + n
        return out


IGNORE_FOR_HEAD = {'phone'}  # 设备数量不代表人数


def pick_head_from_counts(counts: Dict[str, int]) -> int | None:
    """根据计数估算 head（人数）。优先 upright；否则回退 raise_head；再回退总和（忽略 phone）。"""
    if not counts:
        return None
    if 'head' in counts and isinstance(counts.get('head'), int) and counts['head'] > 0:
        return int(counts['head'])
    # upright 往往等于课堂人数（如无遮挡/重复标签）
    if isinstance(counts.get('upright'), int) and counts['upright'] > 0:
        return int(counts['upright'])
    if isinstance(counts.get('raise_head'), int) and counts['raise_head'] > 0:
        return int(counts['raise_head'])
    # 最后兜底：求和（忽略明显非人数的维度）
    s = 0
    for k, v in counts.items():
        if k in IGNORE_FOR_HEAD:
            continue
        try:
            s += int(v)
        except Exception:
            pass
    return s if s > 0 else None


def main():
    ap = argparse.ArgumentParser(description='为行为 JSON 注入/修正人数字段 head（并同步 counts.head）')
    ap.add_argument('--in', dest='inp', required=True, help='输入 JSON 路径（行为检测/分析 JSON）')
    ap.add_argument('--out', dest='out', help='输出 JSON 路径（缺省覆盖原文件，或用 --in-place）')
    ap.add_argument('--in-place', action='store_true', help='原地覆盖输入文件（与 --out 二选一）')
    args = ap.parse_args()

    in_path = os.path.abspath(args.inp)
    if not os.path.exists(in_path):
        print(f'[错误] 文件不存在: {in_path}')
        sys.exit(2)

    with open(in_path, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except Exception as e:
            print(f'[错误] 解析 JSON 失败: {e}')
            sys.exit(2)

    # 提取 counts：优先 data['counts']，否则从 per_class 平铺
    counts_raw: Dict[str, Any] | None = None
    if isinstance(data, dict):
        if isinstance(data.get('counts'), dict):
            counts_raw = data['counts']
        elif isinstance(data.get('per_class'), dict):
            # 兼容两种 per_class：{label:int} 或 {label:{count:int,rate:int}}
            tmp: Dict[str, int] = {}
            for k, v in data['per_class'].items():
                try:
                    if isinstance(v, dict) and isinstance(v.get('count'), int):
                        tmp[k] = int(v['count'])
                    elif isinstance(v, int):
                        tmp[k] = int(v)
                except Exception:
                    pass
            counts_raw = tmp

    counts_norm = normalize_counts(counts_raw or {})
    head = pick_head_from_counts(counts_norm)

    if head is None or head <= 0:
        print('[提示] 无法可靠估算 head（人数），未写入。')
    else:
        # 写入顶层 head，并同步到 counts.head
        try:
            data['head'] = int(head)
            if isinstance(data.get('counts'), dict):
                data['counts']['head'] = int(head)
            print(f'[OK] 已注入 head={head}')
        except Exception as e:
            print(f'[错误] 注入 head 失败: {e}')
            sys.exit(2)

    out_path = in_path if args.in_place or not args.out else os.path.abspath(args.out)
    try:
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(json.dumps(data, ensure_ascii=False, indent=2))
        print(f'[OK] 已写入: {out_path}')
    except Exception as e:
        print(f'[错误] 写文件失败: {e}')
        sys.exit(2)


if __name__ == '__main__':
    main()
