@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Prima esegui INSTALLA_WINDOWS.bat
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt
if errorlevel 1 goto :error
python -m PyInstaller --noconfirm --clean --onefile --windowed --name GameCodeSentinel app.py
if errorlevel 1 goto :error

echo.
echo EXE creata in: %~dp0dist\GameCodeSentinel.exe
echo Aggiorno anche l'attivita' pianificata affinche' usi direttamente l'EXE...
"%~dp0dist\GameCodeSentinel.exe" --install-task --headless
if errorlevel 1 (
  echo ATTENZIONE: EXE creata correttamente, ma la pianificazione non e' stata aggiornata.
  echo Apri l'EXE e usa Impostazioni ^> Salva + attiva controllo giornaliero.
)
pause
exit /b 0

:error
echo.
echo Build fallita.
pause
exit /b 1
