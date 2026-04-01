@echo off
setlocal

for /f "tokens=5" %%p in ('netstat -ano ^| findstr :5000 ^| findstr LISTENING') do (
  taskkill /F /PID %%p >nul 2>&1
)

set KMP_DUPLICATE_LIB_OK=TRUE
set OMP_NUM_THREADS=1
set FLASK_PORT=5000

if not defined CONDA_EXE set "CONDA_EXE=D:\Software\anaconda3\Scripts\conda.exe"
if not exist "%CONDA_EXE%" set "CONDA_EXE=%USERPROFILE%\anaconda3\Scripts\conda.exe"
if not exist "%CONDA_EXE%" set "CONDA_EXE=%USERPROFILE%\miniconda3\Scripts\conda.exe"
if not exist "%CONDA_EXE%" set "CONDA_EXE=conda"

echo [ML] Using conda: %CONDA_EXE%
if /I "%CONDA_EXE%"=="conda" (
  conda run --no-capture-output -n yolov8 python -u main.py
) else (
  "%CONDA_EXE%" run --no-capture-output -n yolov8 python -u main.py
)

endlocal
