#查看ai是否启用
http://localhost:5000/ai/status
# 项目运行手册（Windows PowerShell）

本手册指导在本地一次性跑起后端（Spring Boot 9999）、深度学习服务（Flask 5000）和前端（Vite 8888/8889），并完成端到端联调验证。

目录:
- 环境准备
- 数据库导入
- 启动 Flask（5000）
- 启动 Spring Boot（9999）
- 启动前端 Vite（8888/8889）
- 端到端联调验证
- 常见问题与排错

---

## 环境准备
- 操作系统：Windows，终端：PowerShell（默认）
- Node.js ≥ 16（你当前为 v22.x，可用）
- Maven Wrapper 已内置（无需单独安装 Maven）
- Python Conda 环境：`yolov8`（已存在）
- MySQL（用于导入 `cropdisease` 库）

建议将 PowerShell 输出编码设为 UTF-8 以避免中文乱码（可选）：
```powershell
chcp 65001 | Out-Null
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
```

## 数据库导入
- MySQL 创建数据库并导入 SQL：
  1. 创建库：`cropdisease`
  2. 导入文件：`yolo_cropDisease_detection_web/cropdisease.sql`
- Spring Boot 默认连接：
  - URL: `jdbc:mysql://localhost:3306/cropdisease`
  - 用户/密码：`root/123456`（如与你本地不同，请在 `yolo_cropDisease_detection_web/yolo_cropDisease_detection_web/yolo_cropDisease_detection_springboot/src/main/resources/application.properties` 中修改）

## 启动 Flask（5000）
在仓库根目录执行：
```powershell
(D:\Software\anaconda3\envs\yolo11) ; (conda activate yolo11)
cd /d D:\Software\yolo11\ultralytics-main\Web\yolo_cropDisease_detection_web\yolo_cropDisease_detection_web\yolo_cropDisease_detection_flask
python .\main.py
```
启动成功后，端口 5000 会处于 LISTENING。

## 启动 Spring Boot（9999）
在新的 PowerShell 窗口执行：
```powershell
cd /d D:\Software\yolo11\ultralytics-main\Web\yolo_cropDisease_detection_web\yolo_cropDisease_detection_web\yolo_cropDisease_detection_springboot
.\mvnw.cmd spring-boot:run -DskipTests
```
启动成功后，端口 9999 会处于 LISTENING。

> 如果提示 “Port 9999 is already in use”，说明已有实例在运行，可忽略或结束旧进程后重启。

## 启动前端 Vite（8888/若占用则 8889）
在新的 PowerShell 窗口执行：
```powershell
cd /d D:\Software\yolo11\ultralytics-main\Web\yolo_cropDisease_detection_web\yolo_cropDisease_detection_web\yolo_cropDisease_detection_vue
npm run dev
```
成功后终端会打印：
- Local: `http://localhost:8888/`
- 若 8888 被占用，会自动切换为 `http://localhost:8889/`

Vite 代理配置：
- `/api` → `http://localhost:9999/`
- `/flask` → `http://localhost:5000/`

`.env.development` 已设定：
```
VITE_API_DOMAIN = '/'
```
前端的 `axios` 会以根路径作为 baseURL，便于通过 Vite 代理转发。

## 端到端联调验证
确认三个端口均在监听：
```powershell
netstat -ano -p TCP | findstr ":5000"
netstat -ano -p TCP | findstr ":9999"
netstat -ano -p TCP | findstr ":8888"
```
如果 8888 没有监听，Vite 可能在 8889：
```powershell
netstat -ano -p TCP | findstr ":8889"
```

通过前端代理发起注册（在 PowerShell 中用一行命令）：
```powershell
$u = 'proxy' + [guid]::NewGuid().ToString('N').Substring(0,6); $payload = @{ username = $u; password = '123456' } | ConvertTo-Json -Compress; Invoke-RestMethod -Method Post -Uri 'http://localhost:8888/api/user/register' -ContentType 'application/json' -Body $payload | ConvertTo-Json -Depth 5
```
- 若 Vite 在 8889，请改为：
```powershell
$u = 'proxy' + [guid]::NewGuid().ToString('N').Substring(0,6); $payload = @{ username = $u; password = '123456' } | ConvertTo-Json -Compress; Invoke-RestMethod -Method Post -Uri 'http://localhost:8889/api/user/register' -ContentType 'application/json' -Body $payload | ConvertTo-Json -Depth 5
```
返回 `{"code":"0", ...}` 表示成功。

也可以直接在浏览器打开前端页面 `http://localhost:8888/`（或 `8889`）进行图形化操作测试。

## 常见问题与排错
- Vite 显示 Sass/Node deprecation 警告：
  - 不影响运行。后续可考虑用 `sass-embedded` 并将 `@import` 迁移为 `@use/@forward`。
- 端口占用：
  - 5000/9999/8888 如果冲突，请结束旧进程或调整端口。
- 中文显示乱码：
  - 先运行：
    ```powershell
    chcp 65001 | Out-Null
    $OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
    ```
- 直接打后端测试（绕过前端代理）：
  ```powershell
  # Spring Boot 注册直连
  Invoke-RestMethod -Method Post -Uri 'http://localhost:9999/user/register' -ContentType 'application/json' -Body '{"username":"testuser","password":"123456"}'
  # Flask 健康/接口根据你的路由自行调用
  ```

## 一键启动（可选）
如需在 VS Code 中一键同时起三端，我可以帮你添加 `.vscode/tasks.json` 任务配置，实现并行启动 Flask / Spring Boot / Vite。需要的话告诉我，我直接补上配置。
