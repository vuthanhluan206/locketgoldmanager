import plistlib
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.main import create_app
from app.profile import build_profile


@pytest.fixture
def proxy(monkeypatch):
    for name, value in {
        'SUPERADMIN_EMAIL': 'admin@example.test',
        'SUPERADMIN_PASSWORD_HASH': 'pbkdf2_sha256$600000$' + '00' * 16 + '$' + '00' * 32,
        'MONGODB_URI': 'mongodb://localhost', 'ALLOWED_HOSTS': '["testserver"]',
        'REQUIRE_HTTPS': 'false', 'NEXTDNS_ID': 'abc123', 'ROOT_CA_PATH': '', 'ROOT_CA_PEM': '',
        'ADMIN_PATH': '/secret-test', 'TURNSTILE_SITE_KEY': '', 'TURNSTILE_SECRET_KEY': '',
    }.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    app = create_app()
    app.state.accounts = AsyncMock()
    app.state.accounts.find_one.return_value = None
    app.state.sessions = AsyncMock()
    app.state.sessions.find_one.return_value = None
    app.state.profile = build_profile(get_settings())
    http = TestClient(app, raise_server_exceptions=False)
    yield http, app
    http.close()
    get_settings.cache_clear()


def test_vercel_hosts_are_exact_and_explicit(proxy):
    settings = get_settings().model_dump()
    settings.update(vercel='1', vercel_url='preview-123-team.vercel.app',
                    vercel_project_production_url='project-team.vercel.app')
    configured = Settings(_env_file=None, **settings)
    assert 'preview-123-team.vercel.app' in configured.allowed_hosts
    assert 'project-team.vercel.app' in configured.allowed_hosts
    assert '*.vercel.app' not in configured.allowed_hosts
    custom = Settings(_env_file=None, **{**settings, 'vercel_project_production_url': 'custom.example'})
    assert 'custom.example' not in custom.allowed_hosts
    assert 'testserver' not in Settings(_env_file=None, **{**settings, 'allowed_hosts': ['localhost']}).allowed_hosts
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{**settings, 'vercel_url': 'attacker.example'})


def test_vercel_host_middleware_allows_only_configured_deployment(proxy, monkeypatch):
    from fastapi import FastAPI
    from app.middleware import SecurityMiddleware

    monkeypatch.setenv('VERCEL', '1')
    monkeypatch.setenv('VERCEL_URL', 'preview-123-team.vercel.app')
    get_settings.cache_clear()
    app = FastAPI()
    app.add_middleware(SecurityMiddleware)

    @app.get('/')
    async def home():
        return {'ok': True}

    with TestClient(app, base_url='https://preview-123-team.vercel.app') as http:
        assert http.get('/').status_code == 200
        assert http.get('/', headers={'Host': 'unrelated.vercel.app'}).status_code == 400
        assert http.get('/', headers={'Host': 'preview-123-team.vercel.app.attacker.example'}).status_code == 400


def test_hosts_custom_admin_and_no_schema_leak(proxy):
    http, _ = proxy
    assert http.get('/', headers={'Host': 'attacker.example'}).status_code == 400
    assert http.get('/secret-test').status_code == 200
    assert http.get('/admin').status_code == 404
    assert http.get('/openapi.json').status_code == 404
    assert '/secret-test' not in http.get('/').text
    assert 'access-control-allow-origin' not in http.get('/', headers={'Origin': 'https://attacker.example'}).headers


def test_body_limit_and_removed_proxy_routes(proxy):
    http, _ = proxy
    assert http.post('/api/admin/login', content=b'x' * 8193).status_code == 413
    # The legacy reverse proxy is gone: nothing is forwarded or rewritten.
    for path in ['/proxy/user', '/proxy/install', '/proxy.pac', '/ping']:
        assert http.get(path).status_code == 404
    assert http.get('/v1/subscribers/alice').status_code == 401


def test_deleting_account_removes_account_and_linked_dns_devices(proxy):
    from unittest.mock import MagicMock
    from app.security import token_digest
    http, app = proxy
    token = 'a' * 64
    app.state.login_limits = AsyncMock()
    app.state.login_limits.find_one_and_update.return_value = {'count': 1}
    app.state.sessions.find_one.return_value = {
        '_id': token_digest(token), 'admin_id': 'superadmin', 'auth_version': 'v1'}
    app.state.admins = AsyncMock()
    app.state.admins.find_one.return_value = {'email': 'admin@example.test', 'auth_version': 'v1'}
    devices = AsyncMock()
    app.state.accounts = MagicMock()
    app.state.accounts.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))
    app.state.accounts.database.__getitem__.return_value = devices
    devices.delete_many.return_value = MagicMock(deleted_count=2)
    headers = {'Authorization': 'Bearer ' + token}
    assert http.delete('/admin/accounts/alice', headers=headers).status_code == 204
    app.state.accounts.delete_one.assert_awaited_once_with({'locket_id': 'alice'})
    devices.delete_many.assert_awaited_once_with({'locket_id': 'alice'})
    # Nothing to delete anywhere -> 404.
    app.state.accounts.delete_one.return_value = MagicMock(deleted_count=0)
    devices.delete_many.return_value = MagicMock(deleted_count=0)
    assert http.delete('/admin/accounts/ghost', headers=headers).status_code == 404
    # A DNS device is deleted outright, not merely disabled.
    devices.delete_one.return_value = MagicMock(deleted_count=1)
    assert http.delete('/api/admin/dns/devices/' + 'a' * 24, headers=headers).status_code == 204
    devices.delete_one.assert_awaited_once_with({'_id': 'a' * 24})
    devices.update_one.assert_not_awaited()
    assert http.post('/api/admin/dns/devices/' + 'b' * 24 + '/revoke', headers=headers).status_code == 204
    assert devices.delete_one.await_count == 2


def test_profile_fails_closed(proxy):
    http, app = proxy
    for path in ['/profile.mobileconfig']:
        response = http.get(path)
        assert response.headers['content-type'] == 'application/x-apple-aspen-config'
        assert plistlib.loads(response.content)['PayloadType'] == 'Configuration'
    app.state.profile = None
    assert http.get('/profile.mobileconfig').status_code == 503
