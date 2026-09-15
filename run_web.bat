@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if not exist ".venv-ui\Scripts\python.exe" (
  echo Please create .venv-ui and install requirements-ui.txt first. See README.md.
  pause
  exit /b 1
)
".venv-ui\Scripts\python.exe" -X utf8 "launch_assistant.py" --web
