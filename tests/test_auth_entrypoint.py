from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from app.passwords import hash_password


def test_entrypoint_checks_turnstile_before_login(monkeypatch):
    monkeypatch.setenv('SUPERADMIN_EMAIL', 'admin@example.test')
    monkeypatch.setenv('SUPERADMIN_PASSWORD_HASH', hash_password('test-password'))
    monkeypatch.setenv('MONGODB_URI', 'mongodb://localhost')
    monkeypatch.setenv('ALLOWED_HOSTS', '["testserver"]')
    monkeypatch.setenv('REQUIRE_HTTPS', 'false')
    monkeypatch.setenv('TURNSTILE_SITE_KEY', 'test-site-key')
    monkeypatch.setenv('TURNSTILE_SECRET_KEY', 'test-secret')
    monkeypatch.setenv('TURNSTILE_HOSTNAME', 'admin.example.test')
    get_settings.cache_clear()
    try:
        app = create_app()
        app.state.login_limits = AsyncMock()
        app.state.login_limits.find_one_and_update.return_value = {'count': 1}
        app.state.admins = AsyncMock()
        app.state.admins.find_one.return_value = {
            '_id': 'superadmin', 'email': 'admin@example.test', 'auth_version': 'test',
            'password_hash': get_settings().superadmin_password_hash.get_secret_value(),
        }
        app.state.sessions = AsyncMock()
        verifier = MagicMock(return_value={
            'success': True, 'hostname': 'admin.example.test', 'action': 'admin-login',
        })
        monkeypatch.setattr('app.turnstile.siteverify', verifier)
        # Skip startup to use the fake collections instead of connecting to MongoDB.
        http = TestClient(app)
        try:
            payload = {'email': 'admin@example.test', 'password': 'test-password'}
            assert http.post('/api/admin/login', json=payload).status_code == 403
            verifier.assert_not_called()
            app.state.admins.find_one.assert_not_awaited()
            payload['turnstile_token'] = 'test-token'
            assert http.post('/api/admin/login', json=payload).status_code == 200
            verifier.assert_called_once_with('test-secret', 'test-token')
            app.state.sessions.insert_one.assert_awaited_once()
        finally:
            http.close()
    finally:
        get_settings.cache_clear()
