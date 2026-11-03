from unittest.mock import AsyncMock, MagicMock
from urllib.error import URLError

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import router
from app.config import get_settings
from app.middleware import SecurityMiddleware, client_ip
from app.passwords import hash_password
from app.routes import router as pages


@pytest.fixture
def protected(monkeypatch):
    monkeypatch.setenv('SUPERADMIN_EMAIL', 'admin@example.test')
    monkeypatch.setenv('SUPERADMIN_PASSWORD_HASH', hash_password('test-password'))
    monkeypatch.setenv('MONGODB_URI', 'mongodb://localhost')
    monkeypatch.setenv('ALLOWED_HOSTS', '["testserver"]')
    monkeypatch.setenv('REQUIRE_HTTPS', 'false')
    monkeypatch.setenv('TURNSTILE_SITE_KEY', 'test-site-key')
    monkeypatch.setenv('TURNSTILE_SECRET_KEY', 'test-secret')
    monkeypatch.setenv('TURNSTILE_HOSTNAME', 'admin.example.test')
    monkeypatch.setenv('TRUSTED_PROXY_CIDRS', '[]')
    get_settings.cache_clear()
    app = FastAPI()
    app.add_middleware(SecurityMiddleware)
    app.include_router(router)
    app.include_router(pages)
    app.state.login_limits = AsyncMock()
    app.state.login_limits.find_one_and_update.return_value = {'count': 1}
    app.state.admins = AsyncMock()
    app.state.admins.find_one.return_value = {
        '_id': 'superadmin', 'email': 'admin@example.test',
        'password_hash': get_settings().superadmin_password_hash.get_secret_value(),
        'auth_version': 'test',
    }
    app.state.sessions = AsyncMock()
    verifier = MagicMock(return_value={
        'success': True, 'hostname': 'admin.example.test', 'action': 'admin-login',
    })
    monkeypatch.setattr('app.turnstile.siteverify', verifier)
    with TestClient(app) as http:
        yield http, app, verifier
    get_settings.cache_clear()


def login(http, token='test-token'):
    return http.post('/api/admin/login', json={
        'email': 'admin@example.test', 'password': 'test-password', 'turnstile_token': token,
    })


def test_verified_login_and_widget(protected):
    http, app, verifier = protected
    assert login(http).status_code == 200
    verifier.assert_called_once_with('test-secret', 'test-token')
    app.state.sessions.insert_one.assert_awaited_once()
    page = http.get('/admin-gmnWJ5nG3qZRcdku3eBtkIka')
    assert 'data-sitekey="test-site-key"' in page.text
    assert 'test-secret' not in page.text
    assert 'frame-src https://challenges.cloudflare.com' in page.headers['content-security-policy']
    assert 'onTurnstileReady' not in http.get('/').text


@pytest.mark.parametrize('result', [
    {'success': False}, [],
    {'success': True, 'hostname': 'wrong.test', 'action': 'admin-login'},
    {'success': True, 'hostname': 'admin.example.test', 'action': 'wrong'},
])
def test_invalid_verification_never_checks_password(protected, result):
    http, app, verifier = protected
    verifier.return_value = result
    assert login(http).status_code == 403
    app.state.admins.find_one.assert_not_awaited()
    app.state.sessions.insert_one.assert_not_awaited()


def test_missing_token_and_outage(protected):
    http, app, verifier = protected
    assert login(http, '').status_code == 403
    verifier.assert_not_called()
    verifier.side_effect = URLError('unavailable')
    assert login(http).status_code == 503
    app.state.admins.find_one.assert_not_awaited()


@pytest.mark.parametrize('hostname,status', [
    ('locketgold.vuthanhluan.bond', 200),
    ('locketgold-premium.vercel.app', 200),
    ('locketgold.vuthanhluan.bond.attacker.test', 403),
    ('other.vercel.app', 403),
    ('', 403),
])
def test_multiple_hostnames(protected, monkeypatch, hostname, status):
    http, app, verifier = protected
    monkeypatch.setenv('TURNSTILE_HOSTNAME',
                       'locketgold.vuthanhluan.bond, locketgold-premium.vercel.app ')
    get_settings.cache_clear()
    verifier.return_value['hostname'] = hostname
    assert login(http).status_code == status
    if status == 403:
        app.state.sessions.insert_one.assert_not_awaited()


def test_disabled_and_incomplete_config(protected, monkeypatch):
    http, _, verifier = protected
    monkeypatch.setenv('TURNSTILE_SECRET_KEY', '')
    get_settings.cache_clear()
    assert login(http).status_code == 503
    monkeypatch.setenv('TURNSTILE_SITE_KEY', '')
    get_settings.cache_clear()
    assert login(http, '').status_code == 200
    verifier.assert_not_called()


def test_login_and_admin_shared_limits(protected):
    http, app, verifier = protected
    app.state.login_limits.find_one_and_update.return_value = {'count': 11}
    assert login(http).status_code == 429
    verifier.assert_not_called()
    app.state.login_limits.find_one_and_update.return_value = {'count': 61}
    result = http.get('/api/admin/me')
    assert result.status_code == 429
    assert result.headers['retry-after'] == '60'
    app.state.sessions.find_one.assert_not_awaited()


def test_ip_headers_only_from_trusted_proxy(protected, monkeypatch):
    scope = {'client': ('192.0.2.10', 1000), 'headers': [
        (b'cf-connecting-ip', b'203.0.113.42'), (b'x-forwarded-for', b'198.51.100.1'),
    ]}
    assert client_ip(scope) == '192.0.2.10'
    monkeypatch.setenv('TRUSTED_PROXY_CIDRS', '["192.0.2.0/24"]')
    get_settings.cache_clear()
    assert client_ip(scope) == '203.0.113.42'
    scope['headers'] = [(b'cf-connecting-ip', b'invalid')]
    assert client_ip(scope) == '192.0.2.10'


def test_local_ip_login_limit(protected):
    http, _, verifier = protected
    for _ in range(10):
        assert http.post('/api/admin/login', json={}).status_code == 422
    assert http.post('/api/admin/login', json={}).status_code == 429
    verifier.assert_not_called()


def test_siteverify_posts_token_with_timeout(monkeypatch):
    from app.turnstile import siteverify
    response = MagicMock()
    response.__enter__.return_value.read.return_value = b'{"success":true}'
    transport = MagicMock(return_value=response)
    monkeypatch.setattr('app.turnstile.urlopen', transport)
    assert siteverify('private-secret', 'token+value') == {'success': True}
    request = transport.call_args.args[0]
    assert request.full_url == 'https://challenges.cloudflare.com/turnstile/v0/siteverify'
    assert request.method == 'POST'
    assert request.data == b'secret=private-secret&response=token%2Bvalue'
    assert transport.call_args.kwargs['timeout'] == 5
