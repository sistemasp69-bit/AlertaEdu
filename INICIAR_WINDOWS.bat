@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  python --version >nul 2>nul
  if not errorlevel 1 (python -m venv .venv) else (py -3 -m venv .venv)
)
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: instala Python 3.12 o superior.
  pause
  exit /b 1
)
echo Instalando o verificando dependencias...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 ( echo ERROR al instalar dependencias. & pause & exit /b 1 )
echo.
echo [1/2] Diagnosticando .env ...
".venv\Scripts\python.exe" DIAGNOSTICAR_CONFIGURACION.py
if errorlevel 1 ( echo Ejecuta CONFIGURAR_WINDOWS.bat para reparar .env. & pause & exit /b 1 )
echo [2/2] Probando la conexion real con Supabase...
".venv\Scripts\python.exe" VERIFICAR_CONEXION.py
if errorlevel 1 ( echo Revisa la contraseña o el host Session pooler. & pause & exit /b 1 )
echo.
echo Abre http://127.0.0.1:8000 cuando aparezca Application startup complete.
".venv\Scripts\python.exe" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
echo El servidor se detuvo.
pause
