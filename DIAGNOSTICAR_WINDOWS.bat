@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" DIAGNOSTICAR_CONFIGURACION.py
) else (
  python DIAGNOSTICAR_CONFIGURACION.py
)
pause
