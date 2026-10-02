@echo off
rem One-time setup: install the Python packages the kit needs.
setlocal
cd /d "%~dp0"
set PY=python
where py >nul 2>nul && set PY=py -3

%PY% --version >nul 2>nul
if errorlevel 1 (
  echo Python 3 was not found. Install it from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH" during setup, then run setup.bat again.
  pause
  exit /b 1
)
%PY% -m pip install -r requirements.txt
echo.
echo Setup done. Next: build.bat --vanilla  (should print IDENTICAL to original)
pause
