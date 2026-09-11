@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "taskPython=.venv-ui\Scripts\python.exe"
if not exist "%taskPython%" set "taskPython=.venv\Scripts\python.exe"
if not exist "%taskPython%" (
  echo Please follow README.md to create .venv-ui and install requirements-ui.txt.
  pause
  exit /b 1
)
"%taskPython%" -X utf8 scripts/update_pokemon_data.py sync
set "update_exit=%ERRORLEVEL%"
pause
exit /b %update_exit%
