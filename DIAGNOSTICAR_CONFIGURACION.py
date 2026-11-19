"""Diagnóstico seguro de .env. No imprime contraseñas ni cadenas de conexión."""
from pathlib import Path
from urllib.parse import urlsplit, unquote
import os
import sys
from dotenv import load_dotenv, dotenv_values

ROOT = Path(__file__).resolve().parent
ENV = ROOT / '.env'
PROJECT = 'lwjnmebmotcnkjrhhbyl'
print('Directorio del proyecto: AlertaEdu')
print('Archivo .env:', 'EXISTE' if ENV.is_file() else 'NO EXISTE')
if not ENV.is_file():
    sys.exit('FALTA .env: ejecuta CONFIGURAR_WINDOWS.bat dentro de AlertaEdu.')
vals = dotenv_values(ENV)
load_dotenv(ENV, override=False)
url = (os.getenv('DATABASE_URL') or '').strip()
if not vals.get('DATABASE_URL'):
    sys.exit('El .env existe pero NO contiene DATABASE_URL. Ejecuta CONFIGURAR_WINDOWS.bat.')
if os.environ.get('DATABASE_URL', '') != vals.get('DATABASE_URL', ''):
    print('AVISO: una variable DATABASE_URL del sistema tiene prioridad sobre .env.')
if not url.startswith(('postgresql://', 'postgres://')):
    sys.exit('DATABASE_URL no es una cadena PostgreSQL válida. Reconfigura Supabase.')
try:
    info = urlsplit(url)
    password = unquote(info.password or '')
except ValueError:
    sys.exit('DATABASE_URL tiene un formato incorrecto. Ejecuta CONFIGURAR_WINDOWS.bat.')
if not password or any(x in password.upper() for x in ('YOUR-', 'YOUR_', 'PON_', 'PASSWORD]', 'CONTRASENA')):
    sys.exit('DATABASE_URL no tiene una contraseña REAL; ejecuta CONFIGURAR_WINDOWS.bat.')
host = info.hostname or ''
if host == 'db.'+PROJECT+'.supabase.co':
    mode='Direct connection (IPv6)'
elif host.endswith('.pooler.supabase.com') and (info.username or '') == 'postgres.'+PROJECT and info.port == 5432:
    mode='Session pooler (IPv4)'
else:
    sys.exit('La URL no corresponde al proyecto AlertaEdu o al Session pooler correcto.')
print('Contraseña PostgreSQL: CONFIGURADA (valor oculto)')
print('Tipo de conexión:', mode)
print('Configuración local: OK; falta probar el acceso real con VERIFICAR_CONEXION.py')
