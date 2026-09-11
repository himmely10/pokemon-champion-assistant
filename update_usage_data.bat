@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if not exist ".venv-ui\Scripts\python.exe" (
  echo Please install requirements-ui.txt in .venv-ui first. See README.md.
  pause
  exit /b 1
)
".venv-ui\Scripts\python.exe" -X utf8 "scripts\update_usage_data.py" %*
set "taskExitCode=%ERRORLEVEL%"
pause
exit /b %taskExitCode%
