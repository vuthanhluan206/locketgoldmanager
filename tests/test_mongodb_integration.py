"""Opt in with TEST_MONGODB_URI; all writes use a disposable, uniquely named database."""
import asyncio
import os
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pymongo import AsyncMongoClient

from app.config import get_settings
from app.main import create_app
from app.passwords import hash_password


@pytest.mark.skipif(not os.environ.get('TEST_MONGODB_URI'), reason='Set TEST_MONGODB_URI for real MongoDB tests')
def test_real_mongodb_accounts_rotation_and_cold_starts(monkeypatch):
    from app.bootstrap import sync_admin
    uri = os.environ['TEST_MONGODB_URI']
    database = 'locket_test_' + uuid4().hex
    password, new_password = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    encoded = hash_password(password)
    values = {
        'MONGODB_URI': uri, 'MONGODB_DATABASE': database,
        'SUPERADMIN_EMAIL': 'admin@example.test', 'SUPERADMIN_PASSWORD_HASH': encoded,
        'ALLOWED_HOSTS': '["localhost"]', 'REQUIRE_HTTPS': 'false',
        'ROOT_CA_PEM': '', 'ROOT_CA_PATH': '', 'NEXTDNS_ID': 'abc123',
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()

    def login(http, value):
        result = http.post('/api/admin/login', json={'email': values['SUPERADMIN_EMAIL'], 'password': value})
        assert result.status_code == 200, result.text
        return {'Authorization': 'Bearer ' + result.json()['access_token']}

    async def cleanup():
        assert database.startswith('locket_test_') and len(database) == len('locket_test_') + 32
        client = AsyncMongoClient(uri, serverSelectionTimeoutMS=5000)
        try:
            await client.drop_database(database)
        finally:
            await client.close()

    try:
        with TestClient(create_app(), base_url='http://localhost') as http:
            headers = login(http, password)
            expiry = datetime.now(timezone.utc) + timedelta(days=30)
            for value in [expiry, expiry + timedelta(days=1)]:
                result = http.post('/admin/add-account', headers=headers, json={
                    'locket_id': 'internal_user_123', 'expires_date': value.isoformat(),
                })
                assert result.status_code == 200
            rows = http.get('/admin/accounts', headers=headers).json()
            assert len(rows) == 1
            response = http.get('/v1/subscribers/internal_user_123', headers=headers)
            assert 'Gold' in response.json()['subscriber']['entitlements']

            async def expire():
                await http.app.state.accounts.update_one({'locket_id': 'internal_user_123'}, {
                    '$set': {'expires_date': datetime.now(timezone.utc) - timedelta(seconds=1)},
                })

            http.portal.call(expire)
            assert http.get('/v1/subscribers/internal_user_123', headers=headers).json()['subscriber']['entitlements'] == {}

        # A different deployment must not overwrite the existing account at startup.
        monkeypatch.setenv('SUPERADMIN_PASSWORD_HASH', hash_password(new_password))
        get_settings.cache_clear()
        with TestClient(create_app(), base_url='http://localhost') as http:
            headers = login(http, password)
            http.portal.call(sync_admin, get_settings())
            assert http.get('/api/admin/me', headers=headers).status_code == 401
            headers = login(http, new_password)
            assert http.delete('/admin/accounts/internal_user_123', headers=headers).status_code == 204
            assert http.get('/admin/accounts', headers=headers).json() == []

        # Returning to old environment values must not roll back an explicit password update.
        monkeypatch.setenv('SUPERADMIN_PASSWORD_HASH', encoded)
        get_settings.cache_clear()
        with TestClient(create_app(), base_url='http://localhost') as http:
            headers = login(http, new_password)
            assert http.post('/api/admin/logout', headers=headers).status_code == 204
            assert http.get('/api/admin/me', headers=headers).status_code == 401
    finally:
        asyncio.run(cleanup())
        get_settings.cache_clear()
