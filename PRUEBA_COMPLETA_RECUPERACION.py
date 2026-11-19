"""Prueba guiada REAL del flujo de recuperacion de AlertaEdu.

No guarda credenciales, no usa Supabase de forma directa y no hace envios por su cuenta:
todas las peticiones pasan por la aplicacion AlertaEdu desplegada o local.
Requiere una cuenta existente y correo previamente verificado o accesible.
"""
import getpass
import re
import sys
from urllib.parse import urlsplit
import httpx

TIMEOUT = 30


def validar_url(value: str) -> str:
    p = urlsplit(value.strip().rstrip('/'))
    if p.scheme not in ('https', 'http') or not p.hostname or p.username or p.password or p.query or p.fragment or p.path not in ('', '/'):
        raise ValueError('Introduce una URL base valida, p. ej. https://tuapp.onrender.com')
    if p.scheme == 'http' and p.hostname not in ('localhost', '127.0.0.1', '::1'):
        raise ValueError('Las direcciones publicas necesitan HTTPS')
    return value.strip().rstrip('/')


def extraer_codigo(value: str, tipo: str) -> str:
    raw = value.strip()
    m = re.search(r'(?:#|&)' + re.escape(tipo) + r'=([A-Za-z0-9_-]{30,160})', raw)
    code = m.group(1) if m else raw
    if not re.fullmatch('[A-Za-z0-9_-]{30,160}', code):
        raise ValueError('Introduce el codigo o enlace completo recibido por correo')
    return code


def api(client: httpx.Client, method: str, path: str, *, data=None, csrf=None, required=200):
    headers = {'X-CSRF-Token': csrf} if csrf else {}
    response = client.request(method, path, json=data, headers=headers)
    try:
        body=response.json()
    except ValueError:
        raise RuntimeError(f'{path}: respuesta no JSON (HTTP {response.status_code})')
    if response.status_code != required:
        reason=body.get('detail', body.get('message','HTTP error')) if isinstance(body,dict) else 'HTTP error'
        raise RuntimeError(f'{path}: HTTP {response.status_code}: {reason}')
    return body


def solicitar_codigo(label: str, tipo: str) -> str:
    while True:
        entrada=getpass.getpass(label + ' (codigo o enlace, no se muestra): ')
        try: return extraer_codigo(entrada,tipo)
        except ValueError as exc: print(exc)


def diagnostico(base: str):
    with httpx.Client(base_url=base,timeout=TIMEOUT,follow_redirects=False) as client:
        try:
            salud=api(client,'GET','/healthz')
            estado=api(client,'GET','/api/auth/status')
        except (RuntimeError,httpx.HTTPError) as exc:
            print('No fue posible verificar el servidor:', str(exc))
            return 1
        print('Servidor responde:', salud)
        print('Cuenta inicial creada:', 'SI' if estado.get('initialized') else 'NO')
        print('Esto NO prueba entrega a Gmail ni conexion por una cuenta autenticada.')
    return 0


def ejecutar_completo(base: str):
    print('IMPORTANTE: Esta prueba CAMBIA la contrasena de una cuenta real.')
    print('Usa exclusivamente una cuenta DE PRUEBAS cuyo Gmail puedas abrir.')
    if input('Escribe CAMBIAR para autorizar la prueba: ').strip() != 'CAMBIAR':
        print('Cancelado. No se modifico ninguna contrasena.')
        return 2
    usuario=input('Usuario de prueba existente: ').strip()
    correo=input('Correo asociado y que puedes revisar (p. ej. usuario@gmail.com): ').strip().lower()
    anterior=getpass.getpass('Contrasena actual (oculta): ')
    if not usuario or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',correo):
        print('Usuario o correo no valido');return 2
    with httpx.Client(base_url=base, timeout=TIMEOUT, follow_redirects=False) as client:
        try:
            estado=api(client,'GET','/api/auth/status')
            if not estado.get('initialized'):
                print('No hay usuario inicial. Crea el administrador desde /setup antes de continuar.');return 2
            api(client,'POST','/api/auth/login',data={'username':usuario,'password':anterior})
            csrf=api(client,'GET','/api/auth/me')['csrf_token']
            estado_correo=api(client,'GET','/api/auth/email/mine')
            print('Proveedor de correo configurado en el servidor:', 'SI' if estado_correo.get('configured') else 'NO')
            if not estado_correo.get('configured'):
                print('Falta configurar el proveedor en Render/Windows. No es posible enviar un Gmail real.');return 2
            registrado=estado_correo.get('verified_email')
            if registrado and registrado.lower()!=correo:
                print('La cuenta ya tiene otro correo verificado. Utiliza ese correo o una cuenta de pruebas diferente.');return 2
            if not registrado:
                api(client,'POST','/api/auth/email/register',data={'email':correo,'current_password':anterior},csrf=csrf)
                print('Solicitud de verificacion enviada. Revisa Recibidos y Spam.')
                codigo=solicitar_codigo('Verificacion recibida', 'verificar-correo')
                api(client,'POST','/api/auth/email/verify',data={'token':codigo})
                print('Correo verificado correctamente.')
            api(client,'POST','/api/auth/logout',csrf=csrf)
            api(client,'POST','/api/auth/email/forgot',data={'email':correo})
            print('Solicitud de recuperacion registrada. Revisa Gmail/Spam (limite 15 minutos).')
            codigo=solicitar_codigo('Recuperacion recibida','restablecer-gmail')
            nueva=getpass.getpass('Nueva contrasena (minimo 12 caracteres): ')
            repite=getpass.getpass('Confirma nueva contrasena: ')
            if len(nueva)<12 or nueva!=repite or nueva==anterior:
                print('Contrasena no coincide, se repite o tiene menos de 12 caracteres. No hubo cambio.');return 2
            api(client,'POST','/api/auth/email/reset',data={'token':codigo,'new_password':nueva})
            fallido=client.post('/api/auth/login',json={'username':usuario,'password':anterior})
            if fallido.status_code!=401:
                print('ALERTA: la contrasena antigua no devolvio 401. Compruebalo antes de usar produccion.');return 1
            api(client,'POST','/api/auth/login',data={'username':usuario,'password':nueva})
            reused=client.post('/api/auth/email/reset',json={'token':codigo,'new_password':'ContrasenaNoReutilizable123'})
            if reused.status_code!=400:
                print('ALERTA: el codigo usado no fue rechazado (HTTP',reused.status_code,')');return 1
            print('EXITO: correo recibido, enlace valido, clave actualizada, clave antigua rechazada y token de un solo uso.')
            return 0
        except (httpx.HTTPError,RuntimeError,KeyError) as exc:
            print('FALLO en la prueba:',str(exc))
            print('No compartas contrasenas ni tokens al reportar el error.')
            return 1


def main():
    print('AlertaEdu - verificacion de recuperacion Gmail')
    print('1: Diagnostico sin cambiar nada')
    print('2: Prueba completa REAL (cambia la clave de cuenta de pruebas)')
    modo=input('Elige 1 o 2: ').strip()
    try: base=validar_url(input('Direccion de AlertaEdu [http://127.0.0.1:8000]: ').strip() or 'http://127.0.0.1:8000')
    except ValueError as exc: print(exc);return 2
    if modo=='1': return diagnostico(base)
    if modo=='2': return ejecutar_completo(base)
    print('Opcion no valida');return 2

if __name__=='__main__': sys.exit(main())
