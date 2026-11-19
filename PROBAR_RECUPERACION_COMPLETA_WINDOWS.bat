@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" PRUEBA_COMPLETA_RECUPERACION.py
) else (
  echo No se encontro el entorno Python del proyecto. Ejecuta primero INICIAR_WINDOWS.bat.
  pause
  exit /b 1
)
echo.
pause
