@echo off
rem The mod manager window: tick mods, Build, Play, Add mod...
setlocal
cd /d "%~dp0"
set PY=pythonw
where pyw >nul 2>nul && set PY=pyw -3
start "" %PY% mod_manager.py
