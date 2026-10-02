@echo off
rem Build "build\Urbz Mod.nds" from project\ plus the mods enabled in mods.json,
rem then open it in your emulator if emulator.txt names one.
rem   build.bat            build with enabled mods
rem   build.bat --vanilla  build the original game (should say IDENTICAL)
setlocal
cd /d "%~dp0"
set PY=python
where py >nul 2>nul && set PY=py -3

%PY% urbz_build.py %*
if errorlevel 1 (
  echo.
  echo Build failed - see the message above. Nothing was written.
  pause
  exit /b 1
)

if exist emulator.txt (
  set /p EMU=<emulator.txt
  call :launch
) else (
  echo.
  echo Tip: put the full path of your emulator .exe in emulator.txt
  echo      and build.bat will open the new ROM in it automatically.
)
exit /b 0

:launch
if not exist "%EMU%" (
  echo emulator.txt points to "%EMU%" but that file does not exist.
  exit /b 0
)
start "" "%EMU%" "%~dp0build\Urbz Mod.nds"
exit /b 0
