from __future__ import annotations
from typing import Any, Dict, Optional, List

def _int(x: Any) -> Optional[int]:
    try:
        return int(x)
    except Exception:
        return None

def enrich_consistency(data: Dict[str, Any]) -> Dict[str, Any]:
    """Post-process AI JSON (schema v1.1) for minimal consistency and completeness.

    - Ensure 'head' populated when inferable; add alias '人数'.
    - Normalize per_class to {'count': int, 'rate': int?} when head is present.
    - Fill missing metrics from per_class/head if possible.
    - Add limitations when obvious contradictions exist (e.g., per_class sum > head,
      spatial grid sum far larger than head).
    """
    if not isinstance(data, dict):
        return data

    limitations = data.get('limitations')
    if not isinstance(limitations, list):
        limitations = []

    # Head detection
    head = _int(data.get('head'))

    # per_class may be {label: int} or {label: {count, rate}}
    per_class = data.get('per_class') or {}
    if not isinstance(per_class, dict):
        per_class = {}
    # compute sum of counts
    total_counts = 0
    pc_norm: Dict[str, Any] = {}
    for k, v in per_class.items():
        if isinstance(v, dict):
            c = _int(v.get('count'))
        else:
            c = _int(v)
        if c is None:
            c = 0
        total_counts += c
        pc_norm[k] = {'count': c}

    # Infer head if missing
    if head is None:
        head = total_counts if total_counts > 0 else None
        if head is not None:
            data['head'] = head

    # 人数 alias
    if head is not None:
        try:
            data['人数'] = int(head)
        except Exception:
            pass

    # Fill per_class.rate if head is known
    if head is not None and head > 0:
        for k, vv in pc_norm.items():
            c = _int(vv.get('count')) or 0
            try:
                vv['rate'] = int(round(c / max(1, head) * 100))
            except Exception:
                pass
    if pc_norm:
        data['per_class'] = pc_norm

    # Metrics fill from per_class/head
    metrics = data.get('metrics') or {}
    if not isinstance(metrics, dict):
        metrics = {}
    def _ensure_rate(key: str, labels: list[str]):
        nonlocal metrics
        if metrics.get(key) is None and head is not None and head > 0:
            csum = 0
            for lb in labels:
                it = pc_norm.get(lb) or {}
                csum += _int(it.get('count')) or 0
            metrics[key] = int(round(csum / head * 100))

    # map behaviors to metric keys
    _ensure_rate('head_down_rate', ['bow_head'])
    _ensure_rate('phone_usage_rate', ['using_phone', 'phone'])
    _ensure_rate('reading_rate', ['reading'])
    _ensure_rate('hand_raise_rate', ['hand_raise'])
    _ensure_rate('looking_around_rate', ['turn_head'])
    _ensure_rate('writing_rate', ['writing'])
    _ensure_rate('sleeping_rate', ['sleeping'])

    # distracted_rate as max of some
    if metrics.get('distracted_rate') is None:
        try:
            mx = max(
                _int(metrics.get('head_down_rate')) or 0,
                _int(metrics.get('phone_usage_rate')) or 0,
                _int(metrics.get('looking_around_rate')) or 0,
            )
            metrics['distracted_rate'] = mx
        except Exception:
            pass

    data['metrics'] = metrics

    # Spatial contradiction check
    spatial = data.get('spatial') or {}
    if isinstance(spatial, dict):
        g = spatial.get('grid3x3')
        if isinstance(g, list) and len(g) == 3 and all(isinstance(r, list) and len(r) == 3 for r in g):
            try:
                gsum = sum(int(x) for row in g for x in row)
                if head is not None and gsum > max(head, total_counts) * 2:
                    limitations.append(
                        f"空间分布 grid3x3 总和（{gsum}）显著大于学生总数（{head}）/计数总和（{total_counts}），数据可能存在重复或单位不一致。"
                    )
            except Exception:
                pass

    # per_class vs head contradiction
    if head is not None and total_counts > head:
        limitations.append(
            f"计数字段总和（{total_counts}）大于学生总数（{head}），可能存在数据录入或类别重叠。"
        )

    if limitations:
        data['limitations'] = limitations

    # ---------- Enrich textual summary/observations/risks/suggestions when data is available ----------
    try:
        # Prefer not to overwrite user-provided rich content
        summary = data.get('summary')
        observations = data.get('observations') if isinstance(data.get('observations'), list) else []
        risks = data.get('risks') if isinstance(data.get('risks'), list) else []
        suggestions = data.get('suggestions') if isinstance(data.get('suggestions'), list) else []

        # Extract key counts
        def _pc_count(k: str) -> int:
            v = pc_norm.get(k) or {}
            return _int(v.get('count')) or 0

        c_head = head if head is not None else total_counts if total_counts > 0 else None
        c_upright = _pc_count('upright')
        c_bow = _pc_count('bow_head')
        c_reading = _pc_count('reading')
        c_raise = _pc_count('raise_head')
        c_sleep = _pc_count('sleeping')
        c_using = _pc_count('using_phone')
        c_phone = _pc_count('phone')
        c_phone_any = c_using + c_phone

        def _is_generic_summary(s: Optional[str]) -> bool:
            if not s:
                return True
            s2 = str(s).strip()
            return s2 in ('基于计数与空间分布的概览', '概览', 'summary') or len(s2) < 6

        # Compose summary if missing or too generic and we have some counts
        if (total_counts > 0 or (isinstance(c_head, int) and c_head > 0)) and _is_generic_summary(summary):
            parts: List[str] = []
            if isinstance(c_head, int) and c_head > 0:
                parts.append(f"课堂内共有{c_head}名学生")
            main_bits: List[str] = []
            if c_upright > 0 and (not isinstance(c_head, int) or c_upright >= max(1, int(0.6 * c_head))):
                main_bits.append('多数保持坐姿端正')
            if c_bow > 0:
                main_bits.append('部分存在低头')
            if c_reading > 0:
                main_bits.append('阅读')
            if c_phone_any > 0:
                main_bits.append('使用手机等行为')
            if main_bits:
                parts.append('，' + '、'.join(main_bits))
            data['summary'] = '，'.join(parts) + '。'

        # Compose observations bullets if missing or too short
        if len(observations) < 4 and (total_counts > 0 or (isinstance(c_head, int) and c_head > 0)):
            obs: List[str] = []
            if isinstance(c_head, int) and c_upright == c_head and c_head > 0:
                obs.append(f"全部{c_head}名学生均呈坐姿端正状态（upright={c_upright}）。")
            elif c_upright > 0:
                obs.append(f"{c_upright}名学生坐姿端正（upright={c_upright}）。")
            if c_bow > 0:
                obs.append(f"{c_bow}名学生处于低头状态（bow_head={c_bow}），可能与阅读或设备操作相关。")
            if c_reading > 0:
                obs.append(f"{c_reading}名学生正在阅读（reading={c_reading}）。")
            if c_raise > 0:
                obs.append(f"{c_raise}名学生抬头注视前方（raise_head={c_raise}），关注课堂。")
            if c_sleep > 0:
                obs.append(f"存在{c_sleep}名睡眠学生（sleeping={c_sleep}）。")
            if c_phone_any > 0:
                obs.append(f"课桌/使用中的手机合计{c_phone_any}（using_phone={c_using}, phone={c_phone}）。")
            # fallback: ensure at least 4 items
            while len(obs) < 4:
                obs.append('课堂秩序总体正常，个体差异存在。')
            data['observations'] = obs[:8]

        # Risks
        if not risks:
            rs: List[str] = []
            if c_phone_any >= 2:
                rs.append(f"手机数量较多（{c_phone_any}），可能影响部分学生注意力。")
            if c_sleep >= 1:
                rs.append("出现睡眠行为，可能影响课堂氛围与学习效果。")
            if c_bow + c_reading >= max(2, int((c_head or 6) * 0.25)):
                rs.append("低头/阅读行为较集中，可能削弱与教师的互动与反馈。")
            data['risks'] = rs[:5] if rs else rs

        # Suggestions
        if not suggestions:
            sg: List[str] = []
            if c_phone_any > 0:
                sg.append("提醒规范手机使用，必要时设置收纳或定时检查，强化课堂专注度。")
            if c_bow > 0 or c_reading > 0:
                sg.append("增加抬头交流的提问/点名频率，穿插短时任务促进眼神交流。")
            if c_raise == 0:
                sg.append("设计小组讨论或举手问答环节，提高互动密度。")
            if c_sleep > 0:
                sg.append("关注个体状态，适当安排活动性环节或课间引导。")
            data['suggestions'] = sg[:8] if sg else sg
    except Exception:
        # Best-effort enrichment; ignore errors
        pass
    return data

__all__ = ["enrich_consistency"]
