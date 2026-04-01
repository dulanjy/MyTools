# 多设备协作配置清单（路径与环境）

适用当前目录结构：

- `yolo_studentBehavior_detection_web/db`
- `yolo_studentBehavior_detection_web/yolo_studentBehavior_detection_flask`
- `yolo_studentBehavior_detection_web/yolo_studentBehavior_detection_springboot`
- `yolo_studentBehavior_detection_web/yolo_studentBehavior_detection_vue`

本文只关注“不同设备最容易不一致”的配置项：路径、端口、主机、数据库、Conda 环境。

## 1) 必改项（换机器后优先检查）

### 1.1 一键启动脚本（本地路径 + 端口）
文件：`start_all_services.bat`

需要检查：

- `CONDA_EXE` 默认路径（例如 `D:\Software\anaconda3\Scripts\conda.exe`）
- `mysqld --console` 是否在你的 PATH 中
- 端口是否冲突：
  - MySQL: `3306`
  - Spring Boot: `9999`
  - Vue Dev: `8888`
  - Flask: `5000`

说明：

- 该脚本已使用相对项目路径，不依赖固定盘符项目目录。
- 但 Conda 安装目录、MySQL 安装方式通常机器间不同。

### 1.2 Flask 启动脚本（Conda 环境名）
文件：`yolo_studentBehavior_detection_web/yolo_studentBehavior_detection_flask/start_ml_task.bat`

需要检查：

- Conda 可执行路径探测是否命中
- 环境名：`-n yolov8`（如果你的环境不是 `yolov8`，要改这里）
- `FLASK_PORT=5000` 是否需要调整

### 1.3 VSCode 任务启动目录
文件：`.vscode/tasks.json`

需要检查：

- `start:backend` 的 `cwd`
- `start:frontend` 的 `cwd`
- `start:ml` 的 `cwd`
- `start:mysql` 命令 `mysqld --console` 是否可用

说明：

- 如果你再次重命名项目目录（例如从 `yolo_studentBehavior_detection_web` 改成其他名），这里必须同步改。

### 1.4 后端数据库连接
文件：`yolo_studentBehavior_detection_web/yolo_studentBehavior_detection_springboot/src/main/resources/application.properties`

需要检查：

- `spring.datasource.url`
- `spring.datasource.username`
- `spring.datasource.password`
- `server.port`
- `file.ip`

建议：

- 团队协作时不要提交真实生产密码。
- 至少统一开发库名和端口，减少联调问题。

## 2) 常改项（联调失败优先看）

### 2.1 Vue 环境变量
文件：

- `yolo_studentBehavior_detection_web/yolo_studentBehavior_detection_vue/.env`
- `yolo_studentBehavior_detection_web/yolo_studentBehavior_detection_vue/.env.development`
- `yolo_studentBehavior_detection_web/yolo_studentBehavior_detection_vue/.env.production`

重点字段：

- `VITE_PORT`
- `VITE_API_DOMAIN`
- `VITE_FLASK_BASE_URL`
- `VITE_FLASK_SOCKET_URL`

### 2.2 Vite 代理目标
文件：`yolo_studentBehavior_detection_web/yolo_studentBehavior_detection_vue/vite.config.ts`

需要检查：

- `/api` 代理目标（默认 Spring）
- `/flask` 代理目标（默认 Flask）

如果你改了后端端口，这里要同步改。

### 2.3 前端 Socket 兜底地址
文件：`yolo_studentBehavior_detection_web/yolo_studentBehavior_detection_vue/src/utils/socket.ts`

说明：

- 默认兜底是 `http://localhost:5000`。
- 若 `.env.development` 已配置 `VITE_FLASK_SOCKET_URL`，优先用环境变量。

### 2.4 Flask 到 Spring 的回写地址
文件：`yolo_studentBehavior_detection_web/yolo_studentBehavior_detection_flask/main.py`

说明：

- 默认回写 Spring 使用 `http://localhost:9999`。
- 可通过环境变量 `SPRING_BASE_URL` 覆盖。
- 若部署在非本机，务必设置 `SPRING_BASE_URL`。

## 3) 可选项（开发体验相关）

### 3.1 VSCode 本地数据库连接
文件：`.vscode/settings.json`

`sqltools.connections` 是个人开发配置，通常每台机器不同，可按需改，不影响项目运行。

### 3.2 特殊 API 地址
文件：`yolo_studentBehavior_detection_web/yolo_studentBehavior_detection_vue/src/utils/api.ts`

当前存在固定外部地址（示例：`http://1.15.180.194:9090`）。  
若团队不共用该地址，建议改成环境变量，避免硬编码。

## 4) 新机器最小检查流程（推荐）

1. 执行 `where conda`、`where mysqld`，确认命令可用。  
2. 检查 `application.properties` 的 MySQL 账号密码和库名。  
3. 检查 `.env.development` 与 `vite.config.ts` 端口是否一致。  
4. 运行 `start_all_services.bat`。  
5. 用 `netstat -ano | findstr :8888`、`:9999`、`:5000`、`:3306` 确认四个服务都在监听。  

## 5) 协作建议

- 不同设备差异尽量放在 `.env.*` 或本地脚本，不要散落在业务代码里。
- 涉及路径/端口的变更，优先同步：
  - `start_all_services.bat`
  - `.vscode/tasks.json`
  - `application.properties`
  - Vue `.env.*` 和 `vite.config.ts`
