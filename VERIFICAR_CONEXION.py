"""Prueba la conexión real a Supabase sin mostrar datos privados."""
from pathlib import Path
import os
import sys
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env', override=False)
from DIAGNOSTICAR_CONFIGURACION import ENV  # valida formato sin revelar secretos
try:
    import psycopg
except ImportError:
    sys.exit('ERROR: instala las dependencias: python -m pip install -r requirements.txt')
try:
    with psycopg.connect(os.environ['DATABASE_URL'], sslmode='require', connect_timeout=12, prepare_threshold=None) as c:
        with c.cursor() as cur:
            cur.execute('SELECT current_database(), current_user')
            db, user = cur.fetchone()
            cur.execute('SELECT count(*) FROM public.risk_settings')
            settings = cur.fetchone()[0]
    print('OK: conectado a Supabase PostgreSQL.')
    print('Tabla de configuraciones encontrada:', bool(settings))
except psycopg.OperationalError as exc:
    message = str(exc).lower()
    if 'password authentication failed' in message or 'authentication failed' in message:
        print('ERROR: la contraseña de PostgreSQL no coincide. Vuelve a ejecutar CONFIGURAR_WINDOWS.bat.')
    elif 'could not translate host' in message or 'name or service not known' in message:
        print('ERROR de DNS/red: comprueba Internet y copia Session pooler de Supabase > Connect.')
    elif 'no route to host' in message or 'network is unreachable' in message:
        print('ERROR de red: prueba Session pooler IPv4 (no Direct connection IPv6).')
    else:
        print('ERROR: no se conectó a PostgreSQL. Verifica contraseña, Session pooler y SSL.')
        print('Tipo:', type(exc).__name__)
    sys.exit(1)
except Exception as exc:
    print('ERROR al verificar el esquema de Supabase:', type(exc).__name__)
    print('Abre tu proyecto en Supabase y revisa que existan las tablas.')
    sys.exit(1)
