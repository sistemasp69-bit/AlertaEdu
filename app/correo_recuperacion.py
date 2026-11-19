"""AlertaEdu: recuperación por correo verificado.

Soporta Brevo, Google Apps Script (MailApp mediante HTTPS), Resend y Gmail SMTP local.
Las URL de recuperación llevan tokens en fragmentos (#), evitando registrarlos en la ruta del servidor.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import secrets
import smtplib
import json
from urllib.request import Request as UrlRequest, urlopen
from app import db as database
import ssl
import time
from email.message import EmailMessage
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

router = APIRouter()
_DB: Optional[Path] = None
LOG = logging.getLogger('alertaedu.correo_recuperacion')
SMTP_TIMEOUT = 15
VERIFY_TTL_SECONDS = 30 * 60
RESET_TTL_SECONDS = 15 * 60
WINDOW_SECONDS = 60 * 60
# Límite de peticiones a correos e IP. No es un servicio anti-abuso público.
MAX_BY_ADDRESS = 5
MAX_BY_IP = 15
GENERIC_CONFIRMATION = 'Si la dirección está verificada en AlertaEdu, recibirás instrucciones por correo.'


def configure(db_path: Path):
    global _DB
    _DB = str(db_path)
    with database.connect(_DB, timeout=10) as c:
        c.execute('''CREATE TABLE IF NOT EXISTS gmail_verified_emails (
            username TEXT PRIMARY KEY,
            email TEXT NOT NULL COLLATE NOCASE UNIQUE,
            verified_at INTEGER NOT NULL,
            FOREIGN KEY (username) REFERENCES users(username)
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS gmail_pending_emails (
            username TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            expires_at INTEGER NOT NULL,
            FOREIGN KEY (username) REFERENCES users(username)
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS gmail_reset_tokens (
            username TEXT PRIMARY KEY,
            token_hash TEXT NOT NULL UNIQUE,
            password_hash_at_issue TEXT NOT NULL,
            expires_at INTEGER NOT NULL,
            FOREIGN KEY (username) REFERENCES users(username)
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS gmail_request_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            address_digest TEXT NOT NULL,
            ip_digest TEXT NOT NULL,
            ts INTEGER NOT NULL
        )''')
        c.execute('CREATE INDEX IF NOT EXISTS idx_gmail_attempts_ts ON gmail_request_attempts(ts)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_gmail_attempts_address ON gmail_request_attempts(action,address_digest,ts)')


def _m():
    from app import main as m
    return m


def _digest(raw: str) -> str:
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _clean_email(raw: str) -> str:
    s = raw.strip().lower()
    # Evitar encabezados maliciosos, espacios y caracteres de control.
    if len(s) > 254 or not re.fullmatch(r'[a-z0-9.!#$%&\'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,63}', s):
        raise HTTPException(422, 'Introduce un correo electrónico válido')
    if '..' in s or s.startswith('.') or '.@' in s or '@.' in s:
        raise HTTPException(422, 'Introduce un correo electrónico válido')
    return s


def _sender_configuration():
    user = os.environ.get('ALERTAEDU_SMTP_USER', '').strip().lower()
    password = os.environ.get('ALERTAEDU_SMTP_APP_PASSWORD', '').replace(' ', '').strip()
    if not user or not password:
        raise RuntimeError('Gmail SMTP no configurado. Ejecuta CONFIGURAR_WINDOWS.bat.')
    _clean_email(user)
    return user, password


def _app_base_url() -> str:
    # URL personalizada si existe; en Render se usa automáticamente su dominio HTTPS.
    raw = (os.environ.get('ALERTAEDU_BASE_URL', '').strip()
           or os.environ.get('RENDER_EXTERNAL_URL', '').strip()
           or 'http://127.0.0.1:8000').rstrip('/')
    parts = urlsplit(raw)
    if parts.username or parts.password or parts.query or parts.fragment or parts.path not in ('', '/'):
        raise RuntimeError('ALERTAEDU_BASE_URL no es una dirección base válida')
    if parts.scheme == 'http' and parts.hostname not in ('localhost', '127.0.0.1'):
        raise RuntimeError('Solo se permite HTTP en localhost; fuera del PC utiliza HTTPS')
    if parts.scheme not in ('http', 'https') or not parts.hostname:
        raise RuntimeError('ALERTAEDU_BASE_URL no es válida')
    if os.environ.get('ALERTAEDU_ENV', '').strip().lower() == 'production' and parts.scheme != 'https':
        raise RuntimeError('En producción es obligatorio HTTPS para los enlaces de recuperación')
    return raw


def _email_provider() -> str:
    provider = os.environ.get('ALERTAEDU_EMAIL_PROVIDER', 'gmail').strip().lower()
    if provider not in ('gmail', 'resend', 'apps_script', 'brevo'):
        raise RuntimeError('Proveedor de correo no soportado (gmail/resend/apps_script/brevo)')
    return provider


def _email_configured() -> bool:
    provider = _email_provider()
    if provider == 'apps_script':
        return bool(os.environ.get('ALERTAEDU_APPS_SCRIPT_URL') and os.environ.get('ALERTAEDU_APPS_SCRIPT_SECRET'))
    if provider == 'resend':
        return bool(os.environ.get('RESEND_API_KEY') and os.environ.get('RESEND_FROM_EMAIL'))
    if provider == 'brevo':
        return bool(os.environ.get('BREVO_API_KEY') and os.environ.get('BREVO_FROM_EMAIL'))
    return bool(os.environ.get('ALERTAEDU_SMTP_USER') and os.environ.get('ALERTAEDU_SMTP_APP_PASSWORD'))


def _validate_email_configuration() -> None:
    provider = _email_provider()
    if provider == 'apps_script':
        endpoint = os.environ.get('ALERTAEDU_APPS_SCRIPT_URL', '').strip()
        secret = os.environ.get('ALERTAEDU_APPS_SCRIPT_SECRET', '').strip()
        parts = urlsplit(endpoint)
        if parts.scheme != 'https' or parts.hostname != 'script.google.com' or not re.fullmatch(r'/macros/s/[A-Za-z0-9_-]+/exec', parts.path) or parts.username or parts.password or parts.query or parts.fragment:
            raise RuntimeError('ALERTAEDU_APPS_SCRIPT_URL debe ser la URL /exec oficial del despliegue de Apps Script')
        if len(secret) < 32:
            raise RuntimeError('ALERTAEDU_APPS_SCRIPT_SECRET debe tener al menos 32 caracteres aleatorios')
        return
    if provider == 'resend':
        api_key = os.environ.get('RESEND_API_KEY', '').strip()
        sender = os.environ.get('RESEND_FROM_EMAIL', '').strip().lower()
        if not api_key or not sender:
            raise RuntimeError('Configura RESEND_API_KEY y RESEND_FROM_EMAIL en el servidor')
        _clean_email(sender)
    elif provider == 'brevo':
        api_key = os.environ.get('BREVO_API_KEY', '').strip()
        sender = os.environ.get('BREVO_FROM_EMAIL', '').strip().lower()
        if not api_key or not sender:
            raise RuntimeError('Configura BREVO_API_KEY y BREVO_FROM_EMAIL en el servidor')
        _clean_email(sender)
    else:
        _sender_configuration()


def _send_mail(recipient: str, subject: str, body: str):
    provider = _email_provider()
    if provider == 'apps_script':
        _validate_email_configuration()
        payload = json.dumps({'secret': os.environ['ALERTAEDU_APPS_SCRIPT_SECRET'].strip(),
                              'to': _clean_email(recipient), 'subject': subject, 'body': body},
                             ensure_ascii=False).encode('utf-8')
        req = UrlRequest(os.environ['ALERTAEDU_APPS_SCRIPT_URL'].strip(),
                         data=payload, headers={'Content-Type':'application/json',
                         'User-Agent':'AlertaEdu/1.0'}, method='POST')
        with urlopen(req, timeout=SMTP_TIMEOUT) as response:
            if response.status != 200:
                raise RuntimeError('Google Apps Script no aceptó la solicitud')
            try:
                result=json.loads(response.read(16000))
            except (ValueError, UnicodeError) as exc:
                raise RuntimeError('Respuesta inválida de Google Apps Script') from exc
        if not isinstance(result, dict) or result.get('ok') is not True:
            raise RuntimeError('Google Apps Script no confirmó el envío')
        return
    if provider == 'resend':
        _validate_email_configuration()
        api_key = os.environ['RESEND_API_KEY'].strip()
        sender = os.environ['RESEND_FROM_EMAIL'].strip()
        payload = json.dumps({'from': sender, 'to': [recipient], 'subject': subject, 'text': body}, ensure_ascii=False).encode('utf-8')
        req = UrlRequest('https://api.resend.com/emails', data=payload, headers={
            'Authorization': 'Bearer ' + api_key,
            'Content-Type': 'application/json',
            'User-Agent': 'AlertaEdu/1.0',
        }, method='POST')
        with urlopen(req, timeout=SMTP_TIMEOUT) as response:
            if response.status not in (200, 201, 202):
                raise RuntimeError('No se pudo enviar el correo mediante Resend')
        return
    if provider == 'brevo':
        _validate_email_configuration()
        payload = json.dumps({
            'sender': {
                'email': os.environ['BREVO_FROM_EMAIL'].strip(),
                'name': os.environ.get('BREVO_FROM_NAME', 'AlertaEdu').strip() or 'AlertaEdu',
            },
            'to': [{'email': _clean_email(recipient)}],
            'subject': subject,
            'textContent': body,
        }, ensure_ascii=False).encode('utf-8')
        req = UrlRequest('https://api.brevo.com/v3/smtp/email', data=payload, headers={
            'api-key': os.environ['BREVO_API_KEY'].strip(),
            'Content-Type': 'application/json',
            'User-Agent': 'AlertaEdu/1.0',
        }, method='POST')
        with urlopen(req, timeout=SMTP_TIMEOUT) as response:
            if response.status not in (200, 201, 202):
                raise RuntimeError('No se pudo enviar el correo mediante Brevo')
        return

    sender, app_password = _sender_configuration()
    message = EmailMessage()
    message['From'] = sender
    message['To'] = recipient
    message['Subject'] = subject
    message.set_content(body)
    ctx = ssl.create_default_context()
    with smtplib.SMTP('smtp.gmail.com', 587, timeout=SMTP_TIMEOUT) as client:
        client.ehlo()
        client.starttls(context=ctx)
        client.ehlo()
        client.login(sender, app_password)
        client.send_message(message)


def _rate_ok(conn, request: Request, action: str, address: str, now: int) -> bool:
    # Registra incluso cuando la cuenta no existe (evita consultas ilimitadas).
    ip = request.client.host if request.client else 'unknown'
    i_hash = _digest('ip:' + ip)
    a_hash = _digest('email:' + address)
    conn.execute('DELETE FROM gmail_request_attempts WHERE ts < ?', (now-WINDOW_SECONDS,))
    per_ip = conn.execute('SELECT COUNT(*) FROM gmail_request_attempts WHERE ip_digest=? AND action=?', (i_hash, action)).fetchone()[0]
    per_email = conn.execute('SELECT COUNT(*) FROM gmail_request_attempts WHERE address_digest=? AND action=?', (a_hash, action)).fetchone()[0]
    if per_ip >= MAX_BY_IP or per_email >= MAX_BY_ADDRESS:
        return False
    conn.execute('INSERT INTO gmail_request_attempts(action,address_digest,ip_digest,ts) VALUES(?,?,?,?)', (action, a_hash, i_hash, now))
    return True


def _change_password(conn, m, username: str, password: str):
    salt = secrets.token_hex(16)
    conn.execute('UPDATE users SET password_hash=?, salt=? WHERE username=?',
                 (m.password_hash(password, salt), salt, username))
    conn.execute('DELETE FROM sessions WHERE username=?', (username,))
    conn.execute('DELETE FROM gmail_reset_tokens WHERE username=?', (username,))
    # Integración opcional con códigos de recuperación anteriores, si existen.
    exists = conn.execute("SELECT table_name AS name FROM information_schema.tables WHERE table_schema='public' AND table_name='password_recovery_codes'").fetchone()
    if exists:
        conn.execute('DELETE FROM password_recovery_codes WHERE username=?', (username,))


class MailRegistration(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    current_password: str = Field(min_length=1, max_length=128)

class MailToken(BaseModel):
    token: str = Field(min_length=30, max_length=160)

class ForgotMail(BaseModel):
    email: str = Field(min_length=5, max_length=254)

class ResetMail(BaseModel):
    token: str = Field(min_length=30, max_length=160)
    new_password: str = Field(min_length=12, max_length=128)


@router.get('/api/auth/email/mine')
def email_status(request: Request):
    username = request.state.user['username']
    with _m().conn() as c:
        row = c.execute('SELECT email FROM gmail_verified_emails WHERE username=?', (username,)).fetchone()
    return {'configured': _email_configured(),
            'verified_email': row['email'] if row else None}


@router.post('/api/auth/email/register')
def register_email(request: Request, payload: MailRegistration):
    m = _m()
    username = request.state.user['username']
    email = _clean_email(payload.email)
    _validate_email_configuration()
    now = int(time.time())
    token = secrets.token_urlsafe(40)
    token_hash = _digest(token)
    with m.conn() as c:
        c.execute('BEGIN IMMEDIATE')
        user = c.execute('SELECT password_hash,salt FROM users WHERE username=? AND active=1',(username,)).fetchone()
        if not user or not hmac.compare_digest(m.password_hash(payload.current_password, user['salt']), user['password_hash']):
            raise HTTPException(401, 'La contraseña actual no es correcta')
        exists = c.execute('SELECT username FROM gmail_verified_emails WHERE LOWER(email)=LOWER(?)',(email,)).fetchone()
        if exists and exists['username'] != username:
            raise HTTPException(409, 'Ese correo ya está asociado a otra cuenta')
        if not _rate_ok(c,request,'register',email,now):
            raise HTTPException(429, 'Límite de correos alcanzado. Inténtalo más tarde.')
        c.execute('''INSERT INTO gmail_pending_emails(username,email,token_hash,expires_at)
                     VALUES(?,?,?,?) ON CONFLICT(username) DO UPDATE
                     SET email=excluded.email, token_hash=excluded.token_hash, expires_at=excluded.expires_at''',
                  (username,email,token_hash,now+VERIFY_TTL_SECONDS))
    link = _app_base_url()+'/login#verificar-correo='+token
    body = (f'Hola, {username}.\n\nHas solicitado registrar {email} para recuperar tu contraseña de AlertaEdu.\n'
            'Para confirmar tu correo, abre este enlace desde cualquier dispositivo con internet:\n'
            f'{link}\n\n'
            f'Si lees el mensaje en otro dispositivo, puedes copiar este código en la pantalla de verificación:\n{token}\n\n'
            'Este código vence en 30 minutos y sirve una sola vez.\n'
            'Si no solicitaste esto, ignora el mensaje.\n')
    try:
        _send_mail(email,'AlertaEdu — confirma tu correo',body)
    except Exception:
        LOG.exception('No pudo enviarse el correo de verificación (credenciales SMTP no registradas en logs)')
        with m.conn() as c:
            c.execute('DELETE FROM gmail_pending_emails WHERE username=? AND token_hash=?',(username, token_hash))
        raise HTTPException(503, 'No se pudo enviar el correo. Verifica el proveedor de correo configurado.')
    return {'sent': True, 'message': 'Te enviamos un enlace de verificación. Revisa Gmail y también Spam.'}


@router.post('/api/auth/email/verify')
def verify_email(payload: MailToken):
    now = int(time.time())
    m = _m()
    with m.conn() as c:
        c.execute('BEGIN IMMEDIATE')
        pending = c.execute('SELECT username,email FROM gmail_pending_emails WHERE token_hash=? AND expires_at>=?',
                            (_digest(payload.token),now)).fetchone()
        if not pending:
            raise HTTPException(400, 'Enlace inválido, utilizado o vencido')
        try:
            c.execute('''INSERT INTO gmail_verified_emails(username,email,verified_at) VALUES(?,?,?)
                         ON CONFLICT(username) DO UPDATE SET email=excluded.email,verified_at=excluded.verified_at''',
                      (pending['username'],pending['email'],now))
        except database.IntegrityError as exc:
            raise HTTPException(409, 'Este correo ya corresponde a otra cuenta') from exc
        c.execute('DELETE FROM gmail_pending_emails WHERE username=?',(pending['username'],))
        c.execute('DELETE FROM gmail_reset_tokens WHERE username=?',(pending['username'],))
    return {'verified': True, 'message': 'Gmail verificado. Ya puedes recuperar tu contraseña mediante correo.'}


@router.post('/api/auth/email/forgot')
def forgot_password(request: Request, payload: ForgotMail):
    email = _clean_email(payload.email)
    now = int(time.time())
    m = _m()
    user = None
    token = None
    token_hash = None
    with m.conn() as c:
        c.execute('BEGIN IMMEDIATE')
        allowed = _rate_ok(c,request,'forgot',email,now)
        if allowed:
            user = c.execute('''SELECT u.username, u.password_hash FROM gmail_verified_emails e
                                JOIN users u ON e.username=u.username
                                WHERE LOWER(e.email)=LOWER(?) AND u.active=1''',(email,)).fetchone()
            if user:
                token=secrets.token_urlsafe(40)
                token_hash=_digest(token)
                c.execute('''INSERT INTO gmail_reset_tokens(username,token_hash,password_hash_at_issue,expires_at)
                             VALUES(?,?,?,?) ON CONFLICT(username) DO UPDATE
                             SET token_hash=excluded.token_hash,password_hash_at_issue=excluded.password_hash_at_issue,
                             expires_at=excluded.expires_at''',
                          (user['username'],token_hash,user['password_hash'],now+RESET_TTL_SECONDS))
    if user and token:
        link = _app_base_url()+'/login#restablecer-gmail='+token
        body = (f'Se solicitó recuperar la contraseña de AlertaEdu para el usuario {user["username"]}.\n\n'
                'Abre este enlace desde cualquier dispositivo con internet:\n'
                f'{link}\n\n'
                'También puedes copiar este código en el formulario de recuperación de AlertaEdu:\n'
                f'{token}\n\n'
                'Caduca a los 15 minutos, es de un solo uso y no muestra tu contraseña anterior.\n'
                'Si no solicitaste el cambio, ignora este mensaje.\n')
        try:
            _send_mail(email, 'AlertaEdu — recuperar contraseña', body)
        except Exception:
            LOG.exception('No se pudo enviar el enlace de recuperación (token oculto)')
            with m.conn() as c:
                c.execute('DELETE FROM gmail_reset_tokens WHERE username=? AND token_hash=?',(user['username'],token_hash))
    # Nunca revelar existencia del correo ni error SMTP en endpoint público.
    return {'message': GENERIC_CONFIRMATION}


@router.post('/api/auth/email/reset')
def reset_password(payload: ResetMail):
    password = payload.new_password
    if not password.strip() or password.isspace():
        raise HTTPException(422,'Contraseña inválida')
    now=int(time.time())
    m=_m()
    with m.conn() as c:
        c.execute('BEGIN IMMEDIATE')
        entry=c.execute('''SELECT t.username, t.password_hash_at_issue, u.password_hash FROM gmail_reset_tokens t
                           JOIN users u ON u.username=t.username
                           WHERE t.token_hash=? AND t.expires_at>=? AND u.active=1''',(_digest(payload.token), now)).fetchone()
        if not entry or not hmac.compare_digest(entry['password_hash_at_issue'],entry['password_hash']):
            raise HTTPException(400,'Código inválido, utilizado o vencido')
        if hmac.compare_digest(m.password_hash(password, c.execute('SELECT salt FROM users WHERE username=?',(entry['username'],)).fetchone()['salt']), entry['password_hash']):
            raise HTTPException(422,'La contraseña nueva debe ser diferente de la anterior')
        _change_password(c,m,entry['username'],password)
    response=JSONResponse({'changed':True,'message':'Contraseña nueva guardada. Inicia sesión de nuevo.'})
    response.delete_cookie(m.COOKIE_NAME,path='/')
    return response
