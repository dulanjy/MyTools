@echo off
setlocal

REM Resolve project root from this script location.
set "ROOT_DIR=%~dp0"
set "SPRING_DIR=%ROOT_DIR%yolo_cropDisease_detection_web\yolo_cropDisease_detection_web\yolo_cropDisease_detection_springboot"
set "VUE_DIR=%ROOT_DIR%yolo_cropDisease_detection_web\yolo_cropDisease_detection_web\yolo_cropDisease_detection_vue"
set "ML_DIR=%ROOT_DIR%yolo_cropDisease_detection_web\yolo_cropDisease_detection_web\yolo_cropDisease_detection_flask"

echo Starting mysql(3306), backend(9999), frontend(8888), ml(5000)...

start "start:mysql (3306)" cmd /k "mysqld --console"

start "start:backend (9999)" cmd /k "cd /d ""%SPRING_DIR%"" && .\mvnw.cmd spring-boot:run -DskipTests -Dspring-boot.run.arguments=--server.port=9999"

start "start:frontend (8888)" cmd /k "cd /d ""%VUE_DIR%"" && set BROWSER=none&& npm install && npm run dev -- --port 8888"

start "start:ml (5000)" cmd /k "cd /d ""%ML_DIR%"" && set KMP_DUPLICATE_LIB_OK=TRUE&& set OMP_NUM_THREADS=1&& set FLASK_PORT=5000&& D:\Software\anaconda3\Scripts\conda.exe run --no-capture-output -n yolov8 python -u main.py"

echo All start commands have been sent.
echo Keep each opened CMD window running.

endlocal
