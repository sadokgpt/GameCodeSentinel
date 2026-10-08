@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\pythonw.exe (
  echo Prima esegui INSTALLA_WINDOWS.bat
  pause
  exit /b 1
)
start "" .venv\Scripts\pythonw.exe "%~dp0app.py"
