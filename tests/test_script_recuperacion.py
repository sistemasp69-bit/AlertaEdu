"""Validaciones del asistente interactivo, sin conexiones o contrasenas reales."""
import unittest
from PRUEBA_COMPLETA_RECUPERACION import validar_url, extraer_codigo

class ScriptRecoveryTests(unittest.TestCase):
    def test_https_en_dominio(self):
        self.assertEqual(validar_url('https://alertaedu.onrender.com/'),'https://alertaedu.onrender.com')
    def test_no_http_publico(self):
        with self.assertRaises(ValueError): validar_url('http://alertaedu.onrender.com')
    def test_localhost_permitido(self):
        self.assertEqual(validar_url('http://127.0.0.1:8000'),'http://127.0.0.1:8000')
    def test_token_desde_enlace_fragmento(self):
        tok='x'*42
        self.assertEqual(extraer_codigo('https://app.example.com/login#restablecer-gmail='+tok,'restablecer-gmail'),tok)
    def test_token_invalido(self):
        with self.assertRaises(ValueError): extraer_codigo('hola','verificar-correo')

if __name__=='__main__':unittest.main()
