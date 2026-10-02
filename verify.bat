@echo off
rem Test the built ROM headlessly against the original game.
rem   verify.bat            smoke test build\Urbz Mod.nds
rem   verify.bat doctor     quick boot check
setlocal
cd /d "%~dp0"
set PY=python
where py >nul 2>nul && set PY=py -3
if "%~1"=="" (
  %PY% verify\urbz_verify.py smoke
) else (
  %PY% verify\urbz_verify.py %*
)
pause
