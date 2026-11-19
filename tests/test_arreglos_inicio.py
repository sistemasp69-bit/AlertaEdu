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

    def test_render_usa_supabase_auth_y_no_exige_brevo_api(self):
        text = (ROOT / 'render.yaml').read_text(encoding='utf-8')
        self.assertIn('key: ALERTAEDU_AUTH_PROVIDER\n        value: supabase', text)
        self.assertNotIn('key: BREVO_API_KEY', text)
        for key in ('DATABASE_URL','SUPABASE_PUBLISHABLE_KEY'):
            self.assertIn('key: '+key, text)

if __name__ == '__main__': unittest.main()
