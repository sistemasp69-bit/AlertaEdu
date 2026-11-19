"""Integration smoke test: real endpoints/storage logic, simulated outbound email.
Uses temporary SQLite solely as a disposable test double, never in AlertaEdu production.
"""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import types
import unittest
from unittest.mock import patch

from app import correo_recuperacion as mail

class DummyConnection:
    def __init__(self,path):
        self.raw=sqlite3.connect(path)
        self.raw.row_factory=sqlite3.Row
    def execute(self,sql,*args):
        if 'information_schema.tables' in sql:
            class Nothing:
                @staticmethod
                def fetchone(): return None
            return Nothing()
        return self.raw.execute(sql,*args)
    def __enter__(self): return self
    def __exit__(self,typ,val,tb):
        if typ: self.raw.rollback()
        else: self.raw.commit()
        self.raw.close()

class RecoveryWorkflow(unittest.TestCase):
    def test_registro_confirmacion_solicitud_y_cambio(self):
        with tempfile.TemporaryDirectory() as folder:
            db_path=Path(folder)/'mock.db'
            con=sqlite3.connect(db_path)
            con.executescript('''
                CREATE TABLE users(username TEXT PRIMARY KEY, password_hash TEXT, salt TEXT, active INTEGER);
                CREATE TABLE sessions(token_hash TEXT PRIMARY KEY, username TEXT);
                CREATE TABLE gmail_verified_emails(username TEXT PRIMARY KEY, email TEXT UNIQUE, verified_at INTEGER);
                CREATE TABLE gmail_pending_emails(username TEXT PRIMARY KEY,email TEXT,token_hash TEXT UNIQUE,expires_at INTEGER);
                CREATE TABLE gmail_reset_tokens(username TEXT PRIMARY KEY,token_hash TEXT UNIQUE,password_hash_at_issue TEXT,expires_at INTEGER);
                CREATE TABLE gmail_request_attempts(id INTEGER PRIMARY KEY,action TEXT,address_digest TEXT,ip_digest TEXT,ts INTEGER);
            ''')
            def mock_hash(password,salt): return hashlib.sha256((salt+password).encode()).hexdigest()
            con.execute('INSERT INTO users VALUES (?,?,?,1)',('prueba',mock_hash('AnteriorMuySegura123','salt'),'salt'))
            con.execute('INSERT INTO sessions VALUES (?,?)', ('sessionhash', 'prueba'))
            con.commit(); con.close()
            main=types.SimpleNamespace(conn=lambda: DummyConnection(db_path),password_hash=mock_hash, COOKIE_NAME='alertaedu_session')
            req=types.SimpleNamespace(state=types.SimpleNamespace(user={'username':'prueba'}), client=types.SimpleNamespace(host='127.0.0.1'))
            sent=[]
            with patch.object(mail,'_m',return_value=main),patch.object(mail,'_send_mail',side_effect=lambda to,subject,body: sent.append((to,subject,body))),patch.dict(os.environ,{'ALERTAEDU_EMAIL_PROVIDER':'resend','RESEND_API_KEY':'test-key','RESEND_FROM_EMAIL':'pruebas@example.com','ALERTAEDU_BASE_URL':'https://alertaedu.example.com'}):
                r=mail.register_email(req,mail.MailRegistration(email='prueba@gmail.com',current_password='AnteriorMuySegura123'))
                self.assertTrue(r['sent']); self.assertEqual(len(sent),1)
                v=re.search(r'#verificar-correo=([^\s]+)', sent[-1][2]);self.assertIsNotNone(v)
                self.assertTrue(mail.verify_email(mail.MailToken(token=v.group(1)))['verified'])
                r=mail.forgot_password(req,mail.ForgotMail(email='prueba@gmail.com'))
                self.assertEqual(r['message'],mail.GENERIC_CONFIRMATION);self.assertEqual(len(sent),2)
                token=re.search(r'#restablecer-gmail=([^\s]+)',sent[-1][2]).group(1)
                result=mail.reset_password(mail.ResetMail(token=token,new_password='NuevaMuySegura123!'))
                self.assertEqual(result.status_code,200)
                self.assertIn('"changed":true',result.body.decode())
                c=sqlite3.connect(db_path)
                newhash,newsalt=c.execute('select password_hash,salt from users where username=?',('prueba',)).fetchone()
                self.assertEqual(newhash,mock_hash('NuevaMuySegura123!',newsalt))
                self.assertEqual(c.execute('select count(*) from sessions').fetchone()[0],0)
                self.assertEqual(c.execute('select count(*) from gmail_reset_tokens').fetchone()[0],0)
                c.close()
                with self.assertRaises(Exception):
                    mail.reset_password(mail.ResetMail(token=token,new_password='OtraNuevaMuySegura123!'))
if __name__=='__main__':unittest.main()
