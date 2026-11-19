"""No envía correos reales. Comprueba el proveedor y manejo de respuesta."""
import importlib, json, os, sys, types, unittest
from unittest.mock import patch, MagicMock
fake=types.ModuleType('app.db'); fake.IntegrityError=RuntimeError
sys.modules.setdefault('app.db',fake)
mail=importlib.import_module('app.correo_recuperacion')
URL='https://script.google.com/macros/s/AKfycb12345_TEST/exec'
SECRET='x'*48
class TestAppsScript(unittest.TestCase):
 def test_peticion_firmada(self):
  with patch.dict(os.environ, {'ALERTAEDU_EMAIL_PROVIDER':'apps_script','ALERTAEDU_APPS_SCRIPT_URL':URL,'ALERTAEDU_APPS_SCRIPT_SECRET':SECRET}):
   response=MagicMock(); response.__enter__.return_value.status=200
   response.__enter__.return_value.read.return_value=b'{"ok":true}'
   with patch.object(mail,'urlopen',return_value=response) as sender:
    mail._send_mail('prueba@gmail.com','AlertaEdu - recuperar','Codigo de prueba')
   sent=sender.call_args.args[0]
   self.assertEqual(sent.full_url,URL)
   self.assertEqual(json.loads(sent.data)['secret'],SECRET)
   self.assertEqual(json.loads(sent.data)['to'],'prueba@gmail.com')
 def test_no_acepta_respuesta_fallida(self):
  with patch.dict(os.environ, {'ALERTAEDU_EMAIL_PROVIDER':'apps_script','ALERTAEDU_APPS_SCRIPT_URL':URL,'ALERTAEDU_APPS_SCRIPT_SECRET':SECRET}):
   response=MagicMock(); response.__enter__.return_value.status=200
   response.__enter__.return_value.read.return_value=b'{"ok":false}'
   with patch.object(mail,'urlopen',return_value=response):
    with self.assertRaises(RuntimeError): mail._send_mail('prueba@gmail.com','AlertaEdu - recuperar','Prueba')
 def test_url_no_acepta_otro_dominio(self):
  with patch.dict(os.environ, {'ALERTAEDU_EMAIL_PROVIDER':'apps_script','ALERTAEDU_APPS_SCRIPT_URL':'https://bad.example/','ALERTAEDU_APPS_SCRIPT_SECRET':SECRET}):
   with self.assertRaises(RuntimeError): mail._validate_email_configuration()
 def test_secreto_corto_rechazado(self):
  with patch.dict(os.environ, {'ALERTAEDU_EMAIL_PROVIDER':'apps_script','ALERTAEDU_APPS_SCRIPT_URL':URL,'ALERTAEDU_APPS_SCRIPT_SECRET':'123'}):
   with self.assertRaises(RuntimeError): mail._validate_email_configuration()
if __name__=='__main__': unittest.main()
