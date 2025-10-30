检测 JSON + 图片（多模态）：
python -u .\student_behavior_ai\analyze.py --det-json ".\path\to\det.json" --image ".\class.jpg" --out ".\report.md"
只有检测 JSON（纯文本）：
python -u .\student_behavior_ai\analyze.py --det-json ".\path\to\det.json" --out ".\report.md"
兼容旧计数 JSON：
python -u .\student_behavior_ai\analyze.py --image ".\class.jpg" --counts ".\class_counts.json" --out ".\report.md"

# 学生课堂行为 AI 分析（MVP）

本目录提供一个最小可用的命令行工具，结合一张课堂图片（JPG/PNG）与同名或指定的计数字段 JSON，调用多模态大模型给出“课堂专注度/低头率/看手机/阅读”等分析与建议。

- 图像输入：单张图片（推荐 1280~1920 边长以内，工具会自动压缩）
- 结构化输入：JSON 计数（可选），例如：
  ```json
  {
    " upright ": 12,
    " turn_head ": 1,
    " bow_head ": 9,
    " reading ": 1,
    " raise_head ": 2,
    " Using_phone ": 2,
    " book ": 2
  }
  ```

## 使用方法

- 先在项目根目录确保已配置 Zhipu API Key：
  - PowerShell（写入用户环境）：
    ```powershell
    setx ZHIPU_API_KEY "your_key_here"
    ```
  - 或在设置页/keyring 中配置（应用内已支持）。

- 运行（在项目根目录）：
  ```powershell
  # 使用示例数据：screen_capture/predict 目录下的一组 JPG+JSON
  python -m student_behavior_ai.analyze --image .\screen_capture\predict\00000001_jpg.rf.1046fb34275bf7547edb1e0e287ef371.jpg \
                                        --counts .\screen_capture\predict\00000001_jpg.rf.1046fb34275bf7547edb1e0e287ef371_counts.json \
                                        --out report.md
  ```

- 参数说明：
  - `--image`: 必填，课堂图片路径
  - `--counts`: 选填，计数字段 JSON 路径（若不提供且存在同名 *_counts.json*，工具会自动尝试）
  - `--out`: 选填，将分析结果写入 Markdown 文件
  - `--no-ai`: 选填，禁用大模型，仅使用规则引擎输出（便于本地快速验证）

## 输出内容
- 评分与要点（例如：专注度、低头率、看手机概率、阅读/举手/环顾情况）
- 风险提示与建议（教学节奏、互动方式、座位/视线管理等）
- 附：原始计数与模型元信息（尺寸/缩放/编码大小）

## 实现要点
- 复用现有 `screen_capture.ai_client.AIClient` 的多模态接口 `analyze_image`
- 将 JSON 计数嵌入到 Prompt 文本中，模型共同参考图片与结构化统计
- 无 Key 或网络异常时，回退到规则引擎（基于计数的简单评分/建议）

## 后续计划
- [ ] 支持批量目录分析与汇总报表（CSV/Excel）
- [ ] 引入教室座位区域划分（前排/后排）与热力可视化
- [ ] 引入时间维度：多帧/短视频抽样合并评估
- [ ] 结果可视化：在图片上叠加关键行为标注/比例条

***

> 注意：此工具用于教学质量分析与反馈，不作为任何个体评价的唯一依据，应遵循隐私与合规要求。