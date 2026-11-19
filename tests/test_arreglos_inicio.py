"""Comprobaciones de regresión: envío por Apps Script y transacciones PostgreSQL."""
import ast
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]

class TestArreglos(unittest.TestCase):
    def test_conn_exige_rollback_al_fallar(self):
        source = (ROOT / 'app' / 'main.py').read_text(encoding='utf-8')
        tree = ast.parse(source)
        conn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'conn')
        calls = [n.func.attr for n in ast.walk(conn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
        self.assertIn('rollback', calls)
        self.assertIn('commit', calls)

    def test_prueba_apps_script_espera_secreto_oculto(self):
        source = (ROOT / 'PROBAR_CORREO_REAL.py').read_text(encoding='utf-8')
        self.assertIn('def apps_script_gmail()', source)
        self.assertIn("getpass.getpass('ALERTAEDU_SHARED_SECRET", source)
        self.assertIn("data.get('ok') is not True", source)

    def test_render_configura_brevo_y_conserva_apps_script(self):
        text = (ROOT / 'render.yaml').read_text(encoding='utf-8')
        self.assertIn('value: brevo', text)
        for key in ('BREVO_API_KEY','BREVO_FROM_EMAIL','DATABASE_URL','ALERTAEDU_APPS_SCRIPT_URL','ALERTAEDU_APPS_SCRIPT_SECRET','ALERTAEDU_BOOTSTRAP_TOKEN'):
            self.assertIn('key: '+key, text)

if __name__ == '__main__': unittest.main()
