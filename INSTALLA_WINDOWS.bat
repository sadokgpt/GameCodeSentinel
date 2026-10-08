@echo off
setlocal
cd /d "%~dp0"
title Installazione GameCode Sentinel

echo ======================================================
echo   GameCode Sentinel - installazione Windows
echo ======================================================
echo.

set "PY_CMD="
where py >nul 2>&1
if not errorlevel 1 set "PY_CMD=py -3"
if not defined PY_CMD (
  where python >nul 2>&1
  if not errorlevel 1 set "PY_CMD=python"
)
if not defined PY_CMD (
  echo ERRORE: Python non trovato.
  echo Installa Python 3.11 o superiore da https://www.python.org/downloads/windows/
  echo Durante l'installazione seleziona "Add Python to PATH".
  pause
  exit /b 1
)

%PY_CMD% -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)"
if errorlevel 1 (
  echo ERRORE: serve Python 3.11 o superiore.
  %PY_CMD% --version
  pause
  exit /b 1
)

%PY_CMD% -m venv .venv
if errorlevel 1 goto :error
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
if errorlevel 1 goto :error
python -m pip install -r requirements.txt
if errorlevel 1 goto :error

REM Attiva subito il controllo giornaliero predefinito alle 08:00.
set "TASK_WARNING="
python app.py --install-task > "%TEMP%\GameCodeSentinel_task.txt" 2>&1
if errorlevel 1 set "TASK_WARNING=1"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws=New-Object -ComObject WScript.Shell; $s=$ws.CreateShortcut([Environment]::GetFolderPath('Desktop')+'\GameCode Sentinel.lnk'); $s.TargetPath='%~dp0.venv\Scripts\pythonw.exe'; $s.Arguments='\"%~dp0app.py\"'; $s.WorkingDirectory='%~dp0'; $s.Save()"
if errorlevel 1 (
  echo ATTENZIONE: non sono riuscito a creare il collegamento sul Desktop.
)

echo.
echo Installazione completata.
if defined TASK_WARNING (
  echo ATTENZIONE: la pianificazione automatica non e' stata creata.
  type "%TEMP%\GameCodeSentinel_task.txt"
  echo Puoi riprovare da Impostazioni nel programma.
) else (
  echo Controllo giornaliero impostato alle 08:00.
)
echo Apro il programma. Da Impostazioni puoi cambiare orario e configurare il telefono.
start "" .venv\Scripts\pythonw.exe "%~dp0app.py"
exit /b 0

:error
echo.
echo Installazione non riuscita. Controlla la connessione Internet e riprova.
pause
exit /b 1
