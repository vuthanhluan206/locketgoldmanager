import gzip
import plistlib
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pymongo.errors import PyMongoError

from app.config import Settings, get_settings
from app.main import create_app
from app.middleware import MAX_PROXY_BODY
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
    app.state.viewers_history = MagicMock()
    cursor = app.state.viewers_history.find.return_value
    cursor.sort.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.to_list = AsyncMock(return_value=[])
    app.state.profile = build_profile(get_settings())
    transport = MagicMock(return_value=(200, {'Content-Type': 'application/json'}, b'{"subscriber":{"entitlements":{"Other":{}}}}'))
    monkeypatch.setattr('app.locket_modifier._forward_upstream', transport)
    http = TestClient(app, raise_server_exceptions=False)
    yield http, app, transport, cursor
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
    http, *_ = proxy
    assert http.get('/', headers={'Host': 'attacker.example'}).status_code == 400
    assert http.get('/secret-test').status_code == 200
    assert http.get('/admin').status_code == 404
    assert http.get('/openapi.json').status_code == 404
    assert '/secret-test' not in http.get('/').text
    assert 'access-control-allow-origin' not in http.get('/', headers={'Origin': 'https://attacker.example'}).headers


def test_upload_boundary_and_admin_limit(proxy):
    http, _, transport, _ = proxy
    payload = b'x' * MAX_PROXY_BODY
    assert http.post('/proxy/upload', content=payload, headers={'Content-Type': 'video/mp4'}).status_code == 200
    assert len(transport.call_args.args[1]) == MAX_PROXY_BODY
    transport.reset_mock()
    assert http.post('/proxy/upload', content=b'', headers={'Content-Length': str(MAX_PROXY_BODY + 1)}).status_code == 413
    assert http.post('/api/admin/login', content=b'x' * 8193).status_code == 413
    assert http.post('/proxy/upload', content=iter([payload, b'x'])).status_code == 413
    transport.assert_not_called()


def test_proxy_uses_admin_account_expiry_and_preserves_other_entitlements(proxy):
    http, app, transport, _ = proxy
    expiry = datetime.now(timezone.utc) + timedelta(days=10)
    app.state.accounts.find_one.return_value = {'locket_id': 'alice', 'expires_date': expiry}
    response = http.get('/proxy/v1/subscribers/alice', headers={'Authorization': 'Bearer upstream-token',
                        'Cookie': 'admin=secret', 'X-Forwarded-Host': 'attacker.example'})
    subscriber = response.json()['subscriber']
    assert subscriber['entitlements']['Gold']['expires_date'] == expiry.isoformat().replace('+00:00', 'Z')
    assert 'Other' in subscriber['entitlements']
    app.state.accounts.find_one.assert_awaited_once_with({'locket_id': 'alice'}, {'_id': 0})
    headers = transport.call_args.args[2]
    assert headers['Host'] == 'api.locketcamera.com'
    assert 'cookie' not in headers and 'x-forwarded-host' not in headers
    app.state.accounts.find_one.return_value['expires_date'] = expiry - timedelta(days=20)
    assert 'Gold' not in http.get('/proxy/v1/subscribers/alice', headers={'Authorization': 'Bearer upstream-token'}).json()['subscriber']['entitlements']


def test_viewers_datetime_and_database_failure(proxy):
    http, app, transport, cursor = proxy
    transport.return_value = (200, {'Content-Type': 'application/json'}, b'{"moments":[]}')
    cursor.to_list.return_value = [{'viewer_id': 'friend', 'viewed_at': datetime.now(timezone.utc)}]
    response = http.get('/proxy/moments', headers={'Authorization': 'Bearer upstream-token'})
    assert response.json()['viewers'][0]['user_id'] == 'friend'
    app.state.viewers_history.find.assert_called_with({'token': 'upstream-token'})
    cursor.to_list.side_effect = PyMongoError('private-db-data')
    response = http.get('/proxy/moments', headers={'Authorization': 'Bearer upstream-token'})
    assert response.status_code == 503 and 'private-db-data' not in response.text


def test_passthrough_compression_errors_and_redirects(proxy):
    http, app, transport, _ = proxy
    raw = b'{"error":"upstream"}'
    transport.return_value = (401, {'Content-Type': 'application/json', 'Content-Encoding': 'gzip'}, gzip.compress(raw))
    response = http.get('/proxy/user', headers={'Authorization': 'Bearer upstream-token'})
    assert response.status_code == 401 and response.content == raw
    app.state.accounts.find_one.assert_not_awaited()
    transport.return_value = (302, {'Location': 'https://attacker.example'}, b'')
    assert http.get('/proxy/user').status_code == 502
    transport.side_effect = TimeoutError('private-error')
    response = http.get('/proxy/user')
    assert response.status_code == 502 and 'private-error' not in response.text


def test_profiles_identical_and_fail_closed(proxy):
    http, app, _, _ = proxy
    for path in ['/profile.mobileconfig', '/proxy/install']:
        response = http.get(path)
        assert response.headers['content-type'] == 'application/x-apple-aspen-config'
        assert plistlib.loads(response.content)['PayloadType'] == 'Configuration'
    app.state.profile = None
    assert http.get('/proxy/install').status_code == 503


def test_local_credentials_never_reach_upstream(proxy):
    http, app, transport, _ = proxy
    app.state.sessions.find_one.return_value = {'_id': 'admin-session'}
    assert http.get('/proxy/user', headers={'Authorization': 'Bearer ' + 'a' * 64}).status_code == 401
    transport.assert_not_called()


def test_real_transport_does_not_follow_redirect():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    from app.locket_modifier import _forward_upstream

    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.path)
            self.send_response(302)
            self.send_header('Location', '/must-not-follow')
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, _ = _forward_upstream(f'http://127.0.0.1:{server.server_port}/start', None,
                                       {'Authorization': 'Bearer test'}, 'GET', 2)
        assert status == 302 and seen == ['/start']
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
