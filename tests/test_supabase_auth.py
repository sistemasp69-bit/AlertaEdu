import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app import supabase_auth


class FakeAsyncClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.call = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url, **kwargs):
        self.call = (url, kwargs)
        if self.error:
            raise self.error
        return self.response


class SupabaseRecoveryTests(unittest.TestCase):
    def test_forgot_usa_redirect_y_respuesta_generica(self):
        client = FakeAsyncClient(SimpleNamespace(status_code=200))
        with patch.dict('os.environ', {
            'ALERTAEDU_BASE_URL': 'https://alertaedu.example.com',
            'SUPABASE_PUBLISHABLE_KEY': 'public-test-key',
        }), patch.object(supabase_auth.httpx, 'AsyncClient', return_value=client):
            result = asyncio.run(supabase_auth.forgot(
                supabase_auth.EmailOnly(email='persona@example.com')
            ))

        self.assertIn('Si el correo tiene una cuenta', result['message'])
        request_url, request = client.call
        self.assertTrue(request_url.endswith('/auth/v1/recover'))
        self.assertEqual(request['params'], {'redirect_to': 'https://alertaedu.example.com/reset-password'})
        self.assertEqual(request['json'], {'email': 'persona@example.com'})

    def test_forgot_informa_error_del_proveedor_sin_confirmar_envio(self):
        client = FakeAsyncClient(SimpleNamespace(status_code=500))
        with patch.dict('os.environ', {'SUPABASE_PUBLISHABLE_KEY': 'public-test-key'}), \
                patch.object(supabase_auth.httpx, 'AsyncClient', return_value=client):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(supabase_auth.forgot(
                    supabase_auth.EmailOnly(email='persona@example.com')
                ))

        self.assertEqual(raised.exception.status_code, 503)
