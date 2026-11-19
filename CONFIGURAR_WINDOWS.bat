@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0CONFIGURAR_LOCAL.ps1"
if errorlevel 1 (
  echo No se guardo la configuracion. Revisa el mensaje anterior.
  pause
  exit /b 1
)
echo.
echo Puedes comprobar la conexion con: python VERIFICAR_CONEXION.py
pause
