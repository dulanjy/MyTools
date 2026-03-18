## 学生行为检测与分析服务 API 一览（Flask）

本文档汇总 `yolo_studentBehavior_detection_flask/main.py` 中对外提供的 HTTP 接口，包含路径、方法、参数与返回说明，并标注关键行为与注意事项，便于联调与排障。

基础信息
- 基础地址：`http://localhost:<FLASK_PORT>`（默认 5000；也可由环境变量 `FLASK_PORT` 或 `PORT` 设置）
- 所有接口均提供 `/flask/*` 的别名路径（便于通过前端代理/固定前缀访问）。
- 文件服务：`/files/*` 用于下载由本服务保存/生成的文件。
- 身份认证：当前未接入鉴权。

环境变量（与记录上报相关）
- `SPRING_BASE_URL`：Spring 服务基础地址，默认 `http://localhost:9999`
- `SPRING_IMGRECORDS_PATH`：图片识别记录路径，默认 `/imgRecords`（回退尝试 `/api/imgRecords`）
- `SPRING_VIDEORECORDS_PATH`：视频记录路径，默认 `/videoRecords`（回退尝试 `/api/videoRecords`）
- `SPRING_CAMERARECORDS_PATH`：摄像头记录路径，默认 `/cameraRecords`（回退尝试 `/api/cameraRecords`）
- 失败上报会落盘到 `yolo_studentBehavior_detection_flask/runs/debug_img_records/*.json`，包含请求 URL、响应 body 与 payload，便于排查与补发。

---

### 1) AI 就绪状态
- 路径：`GET /ai/status`（别名：`/flask/ai/status`）
- 作用：检查 AI 客户端（如智谱）是否可用，返回模型与密钥探测信息。
- 返回字段（示例）：
  - `status`: 200/500
  - `data.has_ai_client`: 是否成功导入 AI 客户端模块
  - `data.ready`: 客户端就绪
  - `data.model_text`/`data.model_vision`: 文本/多模态模型名
  - `data.has_key_env`/`data.has_key_keyring`: 是否检测到 API Key（环境变量/系统秘钥环）
  - `data.has_sdk`: SDK 是否就绪

---

### 2) 获取权重文件名
- 路径：`GET /file_names`（别名：`/flask/file_names`）
- 作用：枚举 `./weights` 目录下的可用权重文件，用于前端下拉选择。
- 返回：`{"weight_items": [{"value": "xxx.pt", "label": "xxx.pt"}, ...]}`

---

### 3) 图片预测（单模型）
- 路径：`POST /predictImg`（别名：`/flask/predictImg`）
- 入参（JSON）：
  - `username`（可选）：用户名
  - `weight`：权重文件名（位于 `./weights/`）
  - `conf`（可选，默认 0.5）：置信度阈值
  - `startTime`（可选）：开始时间字符串
  - `inputImg`：图片本地路径或 HTTP(S) URL（URL 将自动下载到临时目录）
  - `kind`（可选，默认 `student`）：任务类型
  - `backend`（可选）：推理后端（`ultralytics`/`onnxruntime`），为空时依据权重后缀自动判定
- 返回（JSON）：
  - `status`/`message`
  - `outImg`：可视化结果 URL（若上传成功则为 `SPRING` 返回链接，否则为本地绝对路径）
  - `allTime`：总耗时字符串
  - `detections`：原始检测结果数组
  - `counts`：各类计数汇总
  - `objects`：[{label, bbox_xyxy, confidence}] 结构化目标列表
  - `boxes`：{label: [{bbox_xyxy, confidence}, ...]}
  - `image`/`size`/`image_size`：输入图路径与尺寸
  - `backend`/`model`：后端与模型名
  - `record_upload`：上报 Spring 的调试信息（尝试的 URL、最后状态码、失败调试目录）
- 说明：
  - 完成后会尝试上报一条“图片识别记录”到 Spring（路径按环境变量配置）。
  - 上报失败会保存到 `runs/debug_img_records/`，便于排查/补发。

---

### 4) 双模型检测（行为+人头）
- 路径：`POST /dualDetect`（别名：`/flask/dualDetect`）
- 入参（JSON）：
  - `inputImg`：图片本地路径或 HTTP(S) URL
  - `behavior_weight`（可选，默认 `./weights/best_student.pt`）
  - `counts_weight`（可选，默认 `./weights/best_per_counts.pt`）
  - `conf`（可选，默认 0.25）
  - `imgsz`（可选，默认 640）
  - `save_json`（可选，默认 false）：是否保存 `*_behavior.json`
  - `out_dir`（可选，默认 `runs/dual_detect`）
  - `backend`（可选）：`ultralytics`/`onnxruntime` 强制后端
- 返回（JSON，合并结构）：
  - `image`：输入图绝对路径
  - `size`：{width, height}
  - `detections`/`objects`：行为模型的检测框
  - `boxes`：分组后的目标框映射
  - `counts`：行为类别计数（不含 head）
  - `head`/`人数`：人头模型计数
  - `backend`：`mixed` 或具体后端
  - `provenance.head_source`：人数来源
  - `models.behavior`/`models.counts`：使用的权重
  - `saved_paths.behavior_json`：当 `save_json=true` 时写入的 `*_behavior.json` 路径

---

### 5) AI 分析（严格 JSON + 可视化）
- 路径：`POST /analyze`（别名：`/flask/analyze`）
- 典型用法：先 `POST /dualDetect` 生成 `*_behavior.json`，然后将其路径传给本接口。
- 入参（JSON，部分可选）：
  - `behavior_json_path` / `behavior_json`：已有行为 JSON（推荐）
  - `analysis_json_path`：若已有 AI 化后的 JSON，可直接复用（本接口会富化并可视化）
  - `inputImg` + `weight` + `kind` + `conf`：也支持直接输入图片分析（严格模式下需提供行为 JSON，除非 `strict_pipeline=false`）
  - `json_only`（默认 true）：强制输出严格 JSON
  - `two_stage`（默认 true）：先拿 JSON，再本地渲染报告
  - `strict_pipeline`（默认 true）：未提供行为 JSON 且无 counts 时拒绝直出
  - `prompt`：自定义提示词（会与系统前置对齐规则合并）
  - `counts`：外部计数（与检测结果合并）
  - `backend`：推理后端（用于图片直出时）
  - `save_reference`（默认 true）：保存参考 JSON（模式、提示词、输入等）
  - `save_json_out`（默认 false）：落盘 AI JSON 与 PNG
  - `out_dir`：输出目录（默认推导自行为 JSON/图片路径，或 `./runs/analysis`）
  - `out_stem`：输出文件名（不带后缀），例如 `input_analysis`
  - `title`（默认 `课堂行为分析`）：报告标题
- 返回（JSON）：
  - `counts` / `detections` / `image_size`：用于可视化与回退
  - `analysis_json`：严格 JSON（含 `summary/metrics/per_class/spatial/limitations/confidence/observations/head/人数` 等）
  - `analysis_markdown`：基于模板渲染的简报（前端通常只展示 `observations` 与 `limitations`）
  - `analysis_image_url`：生成的 PNG 报告
  - `saved_analysis_json_path` / `saved_analysis_png_path` / `saved_reference_json_path`：当 `save_json_out=true` 时存在
- 说明与兜底：
  - 若 `analysis_json_path` 提供，本接口会直接复用且做一致性富化。
  - 若 AI 不可用，回退到本地规则生成（`provenance.generated_by=local_postprocess`），并尽力补齐 `observations`。

---

### 6) 文件上传/下载
- 上传：`POST /files/upload`（别名：`/flask/files/upload`）
  - 表单字段：`file`（单文件）
  - 返回：`{"data": "http://localhost:<port>/files/<uuid>_<orig>"}`
- 下载：`GET /files/<path:filename>`（别名：`/flask/files/<path:filename>`）
  - 说明：用于获取可视化 PNG、上传的原图/视频等。

---

### 7) 视频预测（文件）
- 路径：`GET /predictVideo`
- 入参（QueryString）：
  - `username` / `weight` / `conf` / `startTime` / `inputVideo` / `kind`
- 行为：
  - 以 MJPEG（multipart/x-mixed-replace）流式返回处理帧。
  - 结束后自动转码为 MP4，上传，并上报到 Spring（路径按环境变量配置，含 `/api` 回退）。
- 返回：流式响应（前端通过 `<img>`/`video` 或流播放器消费）。

---

### 8) 摄像头预测（实时）
- 路径：`GET /predictCamera`
- 入参（QueryString）：
  - `username` / `weight` / `kind` / `conf` / `startTime`
- 行为：
  - 从本地摄像头采集帧，以 MJPEG 流式返回。
  - 调用 `GET /stopCamera` 结束并保存，随后上传与上报 Spring。

---

### 9) 停止摄像头预测
- 路径：`GET /stopCamera`
- 作用：结束 `/predictCamera` 的采集与写入。

---

### 10) WebSocket（Socket.IO）
- 命名空间：默认
- 事件：
  - `connect`/`disconnect`：连接/断开
  - 服务端会推送：
    - `message`：文本提示
    - `progress`：视频转码进度（0-100）

---

## 使用示例（Windows cmd，可选）

仅作调试参考，实际以前端调用为准。

1. 读取权重
```cmd
curl "http://localhost:5000/flask/file_names"
```

2. 双模型检测（保存 JSON）
```cmd
curl -X POST "http://localhost:5000/flask/dualDetect" ^
  -H "Content-Type: application/json" ^
  -d "{\"inputImg\":\"http://localhost:5000/files/xxx.jpg\",\"save_json\":true}"
```

3. AI 分析（复用 *_behavior.json）
```cmd
curl -X POST "http://localhost:5000/flask/analyze" ^
  -H "Content-Type: application/json" ^
  -d "{\"behavior_json_path\":\"runs/dual_detect/input_behavior.json\",\"save_json_out\":true,\"out_stem\":\"input_analysis\"}"
```

4. 图片预测
```cmd
curl -X POST "http://localhost:5000/flask/predictImg" ^
  -H "Content-Type: application/json" ^
  -d "{\"weight\":\"best_student.pt\",\"inputImg\":\"http://localhost:5000/files/xxx.jpg\"}"
```

---

## 注意事项
- `/predictVideo` 与 `/predictCamera` 为流式接口，建议通过前端页面访问；完成后服务端会自动上传与上报记录。
- `/analyze` 在严格模式下需要先跑 `/dualDetect` 并提供 `behavior_json_path`，否则会拒绝直出（可设 `strict_pipeline=false` 放宽）。
- 记录上报失败时请优先查看 `runs/debug_img_records/` 保存的调试文件，或通过 `record_upload` 字段定位问题。
