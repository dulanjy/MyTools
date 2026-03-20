# yolo_studentBehavior_detection_web 运行手册（Windows PowerShell）

本文档对应当前仓库状态，覆盖以下服务的本地联调：

- Flask（`5000`）
- Spring Boot（`9999`）
- Vue + Vite（`8888`，冲突时常见 `8889`）

## 1. 环境准备

- Windows + PowerShell
- Node.js 16+（当前项目在 Node 22 也可运行）
- Java（建议 17 或 21）
- Python + Conda（推荐环境名：`yolo11`）
- MySQL（用于 `student_behavior`）

可选：解决 PowerShell 中文乱码

```powershell
chcp 65001 | Out-Null
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
```

## 2. 数据库导入

1. 创建数据库：`student_behavior`
2. 导入脚本：`yolo_studentBehavior_detection_web/student_behavior.sql`

Spring 默认连接配置在：

`yolo_studentBehavior_detection_springboot/src/main/resources/application.properties`

默认值（可通过环境变量覆盖）：

- `SPRING_DATASOURCE_URL=jdbc:mysql://127.0.0.1:3306/student_behavior?...`
- `SPRING_DATASOURCE_USERNAME=root`
- `SPRING_DATASOURCE_PASSWORD=123456`

## 3. 分别启动三端

### 3.1 启动 Flask（5000）

```powershell
cd g:\MyCode\MyTools\yolo_studentBehavior_detection_web\yolo_studentBehavior_detection_flask
C:\Users\hp1\anaconda3\Scripts\conda.exe run -n yolo11 python main.py
```

说明：推荐 `conda run`，比 `conda activate` 更稳定，且不依赖 shell profile。

### 3.2 启动 Spring Boot（9999）

```powershell
cd g:\MyCode\MyTools\yolo_studentBehavior_detection_web\yolo_studentBehavior_detection_springboot
.\mvnw.cmd spring-boot:run -DskipTests
```

若出现 `Port 9999 is already in use`，先结束旧进程或改端口再启动。

### 3.3 启动 Vue + Vite（8888/8889）

```powershell
cd g:\MyCode\MyTools\yolo_studentBehavior_detection_web\yolo_studentBehavior_detection_vue
npm install
npm run dev
```

Vite 代理：

- `/api` -> Spring（默认 `http://localhost:9999`）
- `/flask` -> Flask（默认 `http://localhost:5000`）

## 4. VS Code 一键启动（推荐）

项目已提供任务文件：`yolo_studentBehavior_detection_web/.vscode/tasks.json`

可直接运行任务：

- `Flask: Serve (5000)`
- `Spring: Run (9999)`
- `Vite: Dev (8888)`
- `All: Dev (Flask+Spring+Vite)`

任务逻辑已包含：

- 端口占用检测（已占用时跳过重复启动）
- Flask 使用 `conda run`
- 三服务并行启动

可通过环境变量覆盖 Flask conda 环境名：

```powershell
$env:YOLO_CONDA_ENV='yolov8'
```

## 5. 联调检查

### 5.1 端口监听

```powershell
netstat -ano -p TCP | findstr ":5000"
netstat -ano -p TCP | findstr ":9999"
netstat -ano -p TCP | findstr ":8888"
netstat -ano -p TCP | findstr ":8889"
```

### 5.2 Flask 健康检查

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:5000/ai/status'
```

### 5.3 Spring 登录接口检查

后端兼容两套路径（都可用）：

- `POST /user/login`
- `POST /user/signIn`

示例：

```powershell
$payload = @{ username = 'admin'; password = 'admin' } | ConvertTo-Json -Compress
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:9999/user/signIn' -ContentType 'application/json' -Body $payload
```

### 5.4 通过前端代理调用后端（验证 Vite 代理）

```powershell
$u = 'proxy' + [guid]::NewGuid().ToString('N').Substring(0,6)
$payload = @{ username = $u; password = '123456' } | ConvertTo-Json -Compress
Invoke-RestMethod -Method Post -Uri 'http://localhost:8888/api/user/register' -ContentType 'application/json' -Body $payload
```

如果 Vite 在 `8889`，把 URL 改成 `http://localhost:8889/...`。

## 6. 常见问题

### 6.1 `Must provide a proper URL as target`

这是 Vite 代理目标非法导致。当前项目已在 `vite.config.ts` 中加了目标地址标准化与回退。

仍报错时请检查 `.env*`：

- `VITE_SPRING_BASE_URL`
- `VITE_FLASK_BASE_URL`

建议使用合法 URL（例如 `http://localhost:9999`），不要填 `/`。

### 6.2 Spring 启动失败但编译通过

常见是端口冲突而非代码错误，重点看日志中的 `Port 9999 is already in use`。

### 6.3 Conda 激活失败或权限报错

优先改用：

```powershell
C:\Users\hp1\anaconda3\Scripts\conda.exe run -n yolo11 python main.py
```

## 7. 数据库索引优化（可选）

在 `yolo_studentBehavior_detection_web/db` 目录执行：

```powershell
.\apply_optimize_student_behavior_schema.ps1 -DbHost 127.0.0.1 -Port 3306 -Database student_behavior -User root -Password 123456
```
