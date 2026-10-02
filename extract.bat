@echo off
rem Unpack your Urbz DS ROM into project\ (only needed once, or to start fresh).
rem   extract.bat "C:\path\to\Urbz, The - Sims in the City (USA).nds"
setlocal
cd /d "%~dp0"
set PY=python
where py >nul 2>nul && set PY=py -3

if "%~1"=="" (
  echo Usage: extract.bat "path\to\Urbz.nds"
  echo        ^(unzip the ROM first if it is in a .zip^)
  pause
  exit /b 1
)
if exist project\manifest.json (
  echo project\ already exists. Rename or delete it first if you want a fresh extract.
  echo Your mods\ folder is separate and is not affected either way.
  pause
  exit /b 1
)
%PY% urbz_extract.py "%~1" project
pause
