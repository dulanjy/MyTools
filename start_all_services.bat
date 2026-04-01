@echo off
setlocal

REM Resolve project root from this script location.
set "ROOT_DIR=%~dp0"
set "SPRING_DIR=%ROOT_DIR%yolo_studentBehavior_detection_web\yolo_studentBehavior_detection_springboot"
set "VUE_DIR=%ROOT_DIR%yolo_studentBehavior_detection_web\yolo_studentBehavior_detection_vue"
set "ML_DIR=%ROOT_DIR%yolo_studentBehavior_detection_web\yolo_studentBehavior_detection_flask"
set "CONDA_EXE=D:\Software\anaconda3\Scripts\conda.exe"
if not exist "%CONDA_EXE%" set "CONDA_EXE=%USERPROFILE%\anaconda3\Scripts\conda.exe"
if not exist "%CONDA_EXE%" set "CONDA_EXE=%USERPROFILE%\miniconda3\Scripts\conda.exe"
if not exist "%CONDA_EXE%" set "CONDA_EXE=conda"

echo Starting mysql(3306), backend(9999), frontend(8888), ml(5000)...

start "start:mysql (3306)" cmd /k "mysqld --console"

start "start:backend (9999)" cmd /k "cd /d ""%SPRING_DIR%"" && .\mvnw.cmd spring-boot:run -DskipTests -Dspring-boot.run.arguments=--server.port=9999"

start "start:frontend (8888)" cmd /k "cd /d ""%VUE_DIR%"" && (if not exist node_modules npm install) && set BROWSER=none && npm run dev -- --port 8888"

start "start:ml (5000)" cmd /k "cd /d ""%ML_DIR%"" && set ""CONDA_EXE=%CONDA_EXE%"" && call start_ml_task.bat"

echo All start commands have been sent.
echo Keep each opened CMD window running.

endlocal
