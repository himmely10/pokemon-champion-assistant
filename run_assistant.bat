@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if not exist ".venv-ui\Scripts\pythonw.exe" (
  echo Please create .venv-ui and install requirements-ui.txt first. See README.md.
  pause
  exit /b 1
)
if "%~1"=="" (
  start "" ".venv-ui\Scripts\pythonw.exe" -X utf8 "launch_assistant.py"
) else (
  start "" ".venv-ui\Scripts\pythonw.exe" -X utf8 "launch_assistant.py" "%~1"
)

