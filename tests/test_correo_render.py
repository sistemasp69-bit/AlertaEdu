"""Pruebas de preparación de correo; no hacen llamadas externas ni usan credenciales reales."""
import importlib, json, os, sys, types, unittest
from unittest.mock import patch, MagicMock

# El módulo de correo no necesita conectarse a PostgreSQL para probar formato y transporte.
# Una dependencia falsa impide cualquier acceso a datos durante estas pruebas.
fake=types.ModuleType('app.db')
fake.IntegrityError=RuntimeError
sys.modules.setdefault('app.db', fake)
mail=importlib.import_module('app.correo_recuperacion')

class MailConfigTests(unittest.TestCase):
    def test_render_url_automatica(self):
        with patch.dict(os.environ, {'ALERTAEDU_BASE_URL':'', 'RENDER_EXTERNAL_URL':'https://alertaedu.onrender.com', 'ALERTAEDU_ENV':'production'}):
            self.assertEqual(mail._app_base_url(),'https://alertaedu.onrender.com')

    def test_exige_https_en_produccion(self):
        with patch.dict(os.environ, {'ALERTAEDU_BASE_URL':'http://inseguro.test', 'RENDER_EXTERNAL_URL':'', 'ALERTAEDU_ENV':'production'}):
            with self.assertRaises(RuntimeError): mail._app_base_url()

    def test_peticion_resend_simulada(self):
        with patch.dict(os.environ, {'ALERTAEDU_EMAIL_PROVIDER':'resend', 'RESEND_API_KEY':'re_clave_de_prueba', 'RESEND_FROM_EMAIL':'no-reply@ejemplo.test'}):
            response=MagicMock();response.__enter__.return_value.status=200
            with patch.object(mail,'urlopen',return_value=response) as send:
                mail._send_mail('usuario@gmail.com','Recupera AlertaEdu','Enlace de prueba')
            request=send.call_args.args[0]
            self.assertEqual(request.full_url,'https://api.resend.com/emails')
            data=json.loads(request.data)
            self.assertEqual(data['to'],['usuario@gmail.com'])
            self.assertEqual(data['subject'],'Recupera AlertaEdu')
            self.assertTrue(request.get_header('Authorization').startswith('Bearer re_'))

    def test_peticion_brevo_simulada(self):
        env = {
            'ALERTAEDU_EMAIL_PROVIDER':'brevo',
            'BREVO_API_KEY':'xkeysib-prueba',
            'BREVO_FROM_EMAIL':'no-reply@ejemplo.test',
            'BREVO_FROM_NAME':'AlertaEdu',
        }
        with patch.dict(os.environ, env):
            response=MagicMock();response.__enter__.return_value.status=201
            with patch.object(mail,'urlopen',return_value=response) as send:
                mail._send_mail('usuario@gmail.com','Recupera AlertaEdu','Enlace de prueba')
            request=send.call_args.args[0]
            self.assertEqual(request.full_url,'https://api.brevo.com/v3/smtp/email')
            self.assertEqual(request.get_header('Api-key'),'xkeysib-prueba')
            data=json.loads(request.data)
            self.assertEqual(data['sender']['email'],'no-reply@ejemplo.test')
            self.assertEqual(data['to'],[{'email':'usuario@gmail.com'}])
            self.assertEqual(data['subject'],'Recupera AlertaEdu')
            self.assertEqual(data['textContent'],'Enlace de prueba')

    def test_brevo_requiere_clave_y_remitente(self):
        with patch.dict(os.environ, {'ALERTAEDU_EMAIL_PROVIDER':'brevo'}, clear=True):
            with self.assertRaisesRegex(RuntimeError,'BREVO_API_KEY y BREVO_FROM_EMAIL'):
                mail._validate_email_configuration()

if __name__=='__main__': unittest.main()
