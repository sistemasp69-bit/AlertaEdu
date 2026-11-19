"""Diagnóstico remoto seguro. No requiere ni imprime credenciales."""
import os, sys, json
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from pathlib import Path

if __name__ == '__main__':
    root=Path(__file__).resolve().parent
    for f in ['render.yaml','app/main.py','app/correo_recuperacion.py','app/db.py']:
        print(('OK' if (root/f).is_file() else 'FALTA'), f)
    raw=(sys.argv[1] if len(sys.argv)>1 else os.getenv('ALERTAEDU_BASE_URL','')).strip().rstrip('/')
    if not raw:
        print('FALTA URL REMOTA: python VERIFICAR_PUBLICACION.py https://tu-app.onrender.com')
        sys.exit(2)
    parsed=urlsplit(raw)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('','/'):
        sys.exit('ERROR: escribe únicamente el origen HTTPS, sin ruta, credenciales ni parámetros')
    for path in ['/healthz','/api/auth/status','/login']:
        try:
            with urlopen(Request(raw+path,headers={'User-Agent':'AlertaEdu-HealthCheck/1.0'}),timeout=20) as response:
                payload=response.read(1024).decode('utf-8','replace')
                print(('OK' if response.status==200 else 'REVISAR'),path,'HTTP',response.status)
                if path=='/healthz' and 'ok' not in payload:
                    print('ATENCIÓN: respuesta de salud inesperada')
        except (HTTPError,URLError,TimeoutError) as exc:
            print('ERROR',path,exc)
    print('Nota: esta prueba NO verifica la entrega de correo ni el inicio de sesión.')
