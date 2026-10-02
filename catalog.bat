@echo off
rem Build catalog\index.html: every asset with its type, preview and the scenes it appears in.
setlocal
cd /d "%~dp0"
set PY=python
where py >nul 2>nul && set PY=py -3
%PY% urbz_catalog.py
if exist catalog\index.html start "" "catalog\index.html"
pause
