@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Please follow README.md to create .venv and install requirements.
  pause
  exit /b 1
)
if "%~1"=="" (
  ".venv\Scripts\python.exe" -X utf8 recognize_opponent.py "例子.png"
) else (
  ".venv\Scripts\python.exe" -X utf8 recognize_opponent.py "%~1"
)
set "recognition_exit=%ERRORLEVEL%"
pause
exit /b %recognition_exit%
