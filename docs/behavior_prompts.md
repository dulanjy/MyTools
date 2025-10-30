# 课堂行为分析 Prompt 模板（可直接复制使用）

本页提供两类“指定输出”模板：
- Markdown 报告版：用于给老师阅读的结构化报告
- 严格 JSON 版：用于系统对接/落库的结构化结果

提示：如果存在检测/统计 JSON（例如 `*_counts.json` 或检测框 JSON），建议在提示词中强调“以 JSON 为主、图片为辅；不可见证据不臆测”。

---

## A. Markdown 报告模板（面向老师汇报）

将以下内容复制到应用内“图像分析 → 课堂行为分析…”的 Prompt 对话框中，按需改动你的术语：

你是一名教学观察与课堂行为分析助手。请基于课堂图片（以及可能提供的 JSON 计数）输出标准化报告，结构如下：
1) 关键观察要点
   - 用项目符号列出 3~7 条
2) 指标评估（给出估算百分比与一句话依据）
   - 低头率（%）
   - 看手机（%）
   - 阅读/记笔记（%）
   - 举手/发言（%）
   - 环顾/分心（%）
   - 互动密度（低/中/高）
   - 可选：专注度评分（0~100）/ 课堂活跃度评分（0~100）
3) 风险与建议
   - 风险点（2~4 条）
   - 改进建议（从教学节奏/互动设计/座位与视线管理/课堂规范等维度给出 3~6 条）
4) 局限性与说明
   - 说明图片信息不足或不可见的细节，避免臆测

判定口径建议（可保留）：
- 低头：头部明显朝下、目光不指向讲台/书本
- 看手机：手持设备明显、低头/手势指向设备
- 阅读/记笔记：面向纸本/书本或有书写动作
- 举手：手臂举起超过肩部高度
- 环顾/分心：目光游离教学目标、交谈或分神
- 互动密度：据举手、交流姿势、教师走位互动等综合判断

注意：
- 若分辨率有限或遮挡严重，请降低置信度并明确“不确定”。
- 若已提供检测/统计 JSON，请“以 JSON 内容为主、图片为辅”进行判断；当图片与 JSON 存在冲突时，在 limitations 说明，并优先保留 JSON 的结论。
- 对于难以仅凭图片精确判定的细分行为（如 bow_head 的具体活动、using_phone 的使用状态），若 JSON 已给出结论则以 JSON 为准；若 JSON 也无法确定，请将相关指标填为 null，并在 limitations 说明原因。
- 不要输出学生隐私（如可识别姓名、面孔具体描述等）。
- 可选：在报告末尾附 1~2 句课堂总体评价。

---

## B. 严格 JSON 输出模板（用于系统对接）

用于需要机器消费结构化结果时。复制到 Prompt，并强调“只输出合法 JSON”。

只输出 JSON（UTF-8，无注释、无多余文本），字段如下：
{
  "summary": "一句话概括",
  "observations": ["要点1", "要点2", "要点3"],
  "metrics": {
    "head_down_rate": 0-100,
    "phone_usage_rate": 0-100,
      "reading_rate": 0-100,
    "hand_raise_rate": 0-100,
      "looking_around_rate": 0-100,
      "writing_rate": 0-100,
      "sleeping_rate": 0-100,
    "distracted_rate": 0-100,
    "interaction_level": "low|medium|high",
    "focus_score": 0-100,
    "activity_score": 0-100
  },
  "risks": ["风险1", "风险2"],
  "suggestions": ["建议1", "建议2", "建议3"],
  "limitations": ["局限1", "局限2"],
  "confidence": "low|medium|high"
}

规则与约定：
- 数值使用 0~100 的整数；无法判断的项用 null，并在 limitations 说明原因。
- interaction_level 取值限定为 low/medium/high。
- 仅输出合法 JSON，严禁附加解释文本或 Markdown。
- 若提供了结构化 JSON（检测/统计/已有分析），以 JSON 为主、图片为辅；冲突时在 limitations 说明，并优先保留 JSON 结论。
- 若提供了空间分布（spatial.grid3x3）或检测框位置，请结合其进行位置相关的观察总结（例如前排/中排/后排、左中右的相对集中度）。

---

## C. 双输出模板（先 JSON，再报告）

如果既要结构化结果又要给老师看的报告，可以让模型先输出 JSON，再追加一份 Markdown 摘要：

步骤1：
- 使用“严格 JSON 输出模板”作为首个 Prompt，获取 JSON 结果。

步骤2：
- 继续会话，发送：
请基于你刚才输出的 JSON 结果，生成一份面向老师阅读的 Markdown 报告（结构与 A 类似，简明扼要，300~600 字）。

---

## D. 简短版 Prompt（速用）

- 报告速用：
请基于课堂图片输出：关键要点、各项指标（低头/看手机/阅读记笔记/举手/分心/互动密度+可选专注度与活跃度评分）、风险与建议、局限性。给出百分比及一句话依据，避免臆测，不含隐私。

- JSON 速用：
只输出 JSON，字段含 summary、observations[]、metrics{head_down_rate,phone_usage_rate,reading_note_rate,hand_raise_rate,distracted_rate,interaction_level,focus_score,activity_score}、risks[]、suggestions[]、limitations[]、confidence。数值 0~100，未知用 null，不附加多余文本。

---

## E. 与检测/统计 JSON 的配合（JSON 优先）

当应用将检测/统计 JSON（如 `*_counts.json`、检测框 JSON 或已有结构化 JSON）附加在 Prompt 后：
- 在“注意/规则”中明确“以 JSON 为主、图片为辅；不可见证据不臆测”。
- 模型可据此推断/微调指标；与图片冲突时在 limitations 说明依据，并优先保留 JSON 的结论。

---

以上模板可直接用于：
- UI：AI 对话窗口 → 图像分析 → 课堂行为分析… → Prompt 输入框
- CLI：`student_behavior_ai/analyze.py` 的 `--prompt` 参数

如需自定义你的指标或评分维度，把名称替换到模板相应位置即可。