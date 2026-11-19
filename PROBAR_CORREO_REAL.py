"""Prueba optativa de envío real de AlertaEdu sin guardar credenciales.

Modo 1: Gmail SMTP desde tu PC (no funciona en Render Free).
Modo 2: Gmail mediante Google Apps Script (HTTPS, funciona en Render).
Modo 3: Resend HTTPS como alternativa opcional.
Este programa prueba envío/recepción, no modifica contraseñas ni la base de datos.
"""
from __future__ import annotations
import getpass
import json
import os
import re
import smtplib
import socket
import ssl
from email.message import EmailMessage
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlsplit


def correo(prompt: str) -> str:
    while True:
        value = input(prompt).strip()
        if re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', value):
            return value
        print('Introduce una direccion de correo valida.')


def gmail_smtp() -> None:
    sender = correo('Cuenta Gmail remitente: ')
    recipient = correo('Cuenta Gmail que recibira la prueba: ')
    password = getpass.getpass('Contrasena de aplicacion de Google (no se muestra): ').replace(' ', '').strip()
    if not password:
        print('CANCELADO: no se ingreso ninguna contrasena de aplicacion.')
        return
    message = EmailMessage()
    message['From'] = sender
    message['To'] = recipient
    message['Subject'] = 'AlertaEdu - prueba de entrega Gmail'
    message.set_content('Esta es una prueba de entrega del correo de AlertaEdu.\n'
                        'No es un enlace real de recuperacion y no cambia contrasenas.\n')
    try:
        with smtplib.SMTP('smtp.gmail.com', 587, timeout=20) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
            smtp.login(sender, password)
            smtp.send_message(message)
    except smtplib.SMTPAuthenticationError:
        print('FALLO: Google rechazo el acceso. Usa una contrasena de aplicacion, no tu clave normal.')
    except (socket.timeout, TimeoutError, OSError, smtplib.SMTPException) as exc:
        print('FALLO DE ENVIO:', type(exc).__name__, str(exc))
    else:
        print('ACEPTADO POR GMAIL SMTP. Revisa Recibidos y Spam de', recipient)
        print('La entrega a bandeja no se confirma hasta revisar el correo.')



def apps_script_gmail() -> None:
    """Envía un correo de prueba Gmail real mediante Apps Script, sin guardar el secreto."""
    recipient = correo('Gmail que recibira la prueba: ')
    url = input('URL /exec de tu Google Apps Script: ').strip()
    secret = getpass.getpass('ALERTAEDU_SHARED_SECRET (oculto): ').strip()
    parts = urlsplit(url)
    if (parts.scheme != 'https' or parts.hostname != 'script.google.com' or
            not re.fullmatch(r'/macros/s/[A-Za-z0-9_-]+/exec', parts.path) or
            parts.query or parts.fragment or parts.username or parts.password):
        print('ERROR: copia la URL exacta /exec de Apps Script, no /dev ni el editor.')
        return
    if len(secret) < 32:
        print('ERROR: el secreto de Apps Script debe tener 32 o mas caracteres.')
        return
    payload = json.dumps({
        'secret': secret,
        'to': recipient,
        'subject': 'AlertaEdu - prueba de entrega Gmail',
        'body': 'Esta prueba viene del remitente Gmail de AlertaEdu via Google Apps Script.\n'
                'No modifica usuarios ni contrasenas.\n'
    }, ensure_ascii=False).encode('utf-8')
    request = Request(url, data=payload, method='POST', headers={
        'Content-Type': 'application/json', 'User-Agent': 'AlertaEdu/1.0'})
    try:
        with urlopen(request, timeout=25) as response:
            data = json.loads(response.read(16000).decode('utf-8'))
            if response.status != 200 or not isinstance(data, dict) or data.get('ok') is not True:
                print('FALLO: Google Apps Script no confirmo el envio.')
                return
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, UnicodeError) as exc:
        # No mostrar cuerpos HTTP ni detalles con posibles credenciales.
        print('FALLO al enviar mediante Apps Script:', type(exc).__name__)
    else:
        print('ACEPTADO POR GOOGLE APPS SCRIPT. Revisa Recibidos y Spam de', recipient)
        print('La recepcion real se confirma mirando ese Gmail.')

def resend_https() -> None:
    sender = correo('Correo remitente verificado en Resend (p.ej. no-reply@tudominio.com): ')
    recipient = correo('Cuenta Gmail que recibira la prueba: ')
    key = getpass.getpass('Clave API de Resend (no se muestra): ').strip()
    if not key:
        print('CANCELADO: no se ingreso la clave API.')
        return
    body = json.dumps({'from':sender,'to':[recipient],
                       'subject':'AlertaEdu - prueba de entrega desde Render',
                       'text':'Prueba de envio HTTPS de AlertaEdu. No cambia ninguna contrasena.'}).encode('utf8')
    request = Request('https://api.resend.com/emails', data=body, headers={
        'Authorization':'Bearer '+key,
        'Content-Type':'application/json',
        'User-Agent':'AlertaEdu/1.0'
    }, method='POST')
    try:
        with urlopen(request, timeout=20) as response:
            data=json.loads(response.read().decode('utf8'))
            if response.status not in (200,201,202):
                print('FALLO DE ENVIO: HTTP',response.status)
                return
    except HTTPError as exc:
        try:
            details=json.loads(exc.read().decode('utf8'))
            error=str(details.get('message','Error HTTP'))
        except Exception:
            error='Error de solicitud'
        print('FALLO DE ENVIO: HTTP',exc.code, error)
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        print('FALLO DE ENVIO:', type(exc).__name__, str(exc))
    else:
        print('ACEPTADO POR RESEND. ID de solicitud:',str(data.get('id','no recibido')))
        print('Revisa Recibidos y Spam de',recipient)
        print('Resend puede aceptar la solicitud sin confirmar la entrega a bandeja.')


if __name__=='__main__':
    print('=== AlertaEdu: prueba REAL de correo ===')
    print('1) Gmail SMTP: ejecutar solo desde tu computadora')
    print('2) Gmail con Google Apps Script HTTPS: recomendado para Render')
    print('3) Resend HTTPS (alternativa)')
    option=input('Elige 1, 2 o 3: ').strip()
    if option=='1':gmail_smtp()
    elif option=='2':apps_script_gmail()
    elif option=='3':resend_https()
    else:print('Opcion no reconocida; no se envio ningun correo.')
