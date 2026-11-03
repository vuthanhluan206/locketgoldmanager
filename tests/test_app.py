import asyncio
import hashlib
import json
import plistlib
import secrets
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pymongo.errors import PyMongoError

from app.config import Settings, get_settings
from app.database import get_accounts, lifespan
from app.main import create_app
from app.middleware import RateLimiter, SecurityMiddleware
from app.models import AccountInput, subscriber_response
from app.passwords import hash_password, verify_password
from app.profile import build_profile
from app.security import token_digest


@pytest.fixture(scope='module')
def password_pair():
    password = secrets.token_urlsafe(20)
    return password, hash_password(password)


@pytest.fixture
def client(monkeypatch, password_pair):
    password, encoded = password_pair
    monkeypatch.setenv('SUPERADMIN_EMAIL', 'admin@example.test')
    monkeypatch.setenv('SUPERADMIN_PASSWORD_HASH', encoded)
    monkeypatch.setenv('MONGODB_URI', 'mongodb://127.0.0.1:27017')
    monkeypatch.setenv('ALLOWED_HOSTS', '["localhost"]')
    monkeypatch.setenv('REQUIRE_HTTPS', 'false')
    monkeypatch.setenv('NEXTDNS_ID', 'abc123')
    monkeypatch.setenv('ROOT_CA_PATH', '')
    monkeypatch.setenv('ROOT_CA_PEM', '')
    monkeypatch.delenv('SUBSCRIBER_API_TOKEN', raising=False)
    monkeypatch.setenv('TURNSTILE_SITE_KEY', '')
    monkeypatch.setenv('TURNSTILE_SECRET_KEY', '')
    monkeypatch.setenv('TURNSTILE_HOSTNAME', '')
    get_settings.cache_clear()
    app = create_app()
    accounts, admins, sessions = AsyncMock(), AsyncMock(), AsyncMock()
    admin = {'_id': 'superadmin', 'email': 'admin@example.test', 'password_hash': encoded,
             'auth_version': hashlib.sha256(encoded.encode()).hexdigest()}
    admins.find_one.side_effect = lambda query: admin.copy() if query in [
        {'_id': 'superadmin', 'email': admin['email']}, {'_id': admin['_id']},
    ] else None
    stored = {}

    async def insert(document):
        stored[document['_id']] = document.copy()

    async def find(query):
        document = stored.get(query['_id'])
        return document.copy() if document and document['expires_at'] > query['expires_at']['$gt'] else None

    async def delete(query):
        stored.pop(query['_id'], None)

    sessions.insert_one.side_effect = insert
    sessions.find_one.side_effect = find
    sessions.delete_one.side_effect = delete
    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.skip.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.to_list = AsyncMock(return_value=[])
    accounts.find = MagicMock(return_value=cursor)
    app.dependency_overrides[get_accounts] = lambda: accounts
    app.state.admins, app.state.sessions = admins, sessions
    app.state.login_limits = AsyncMock()
    buckets = {}

    async def count_login(query, update, **kwargs):
        key = query['_id']
        buckets[key] = buckets.get(key, 0) + 1
        return {'count': buckets[key]}

    app.state.login_limits.find_one_and_update.side_effect = count_login
    app.state.profile = build_profile(get_settings())
    # HTTP tests deliberately skip real MongoDB lifespan.
    http = TestClient(app, base_url='http://localhost', raise_server_exceptions=False)
    yield http, accounts, admins, sessions, stored, password, app
    http.close()
    get_settings.cache_clear()


def sign_in(client):
    http, _, _, _, _, password, _ = client
    response = http.post('/api/admin/login', json={'email': 'admin@example.test', 'password': password})
    assert response.status_code == 200, response.text
    token = response.json()['access_token']
    return token, {'Authorization': 'Bearer ' + token}


def test_views_and_csp(client):
    http = client[0]
    public = http.get('/')
    assert public.status_code == 200
    class Elements(HTMLParser):
        def __init__(self):
            super().__init__()
            self.ids = set()
            self.scripts = []

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if 'id' in attrs:
                self.ids.add(attrs['id'])
            if tag == 'script':
                self.scripts.append(attrs)

    public_elements = Elements()
    public_elements.feed(public.text)
    assert not {'loginForm', 'accountForm'} & public_elements.ids
    assert 'installBtn' in public_elements.ids
    assert "const key = 'locket_admin_session'" not in public.text
    admin_path = '/admin-gmnWJ5nG3qZRcdku3eBtkIka'
    assert http.get('/admin').status_code == 404
    admin = http.get(admin_path)
    assert admin.status_code == 200
    admin_elements = Elements()
    admin_elements.feed(admin.text)
    assert {'loginForm', 'accountForm'} <= admin_elements.ids
    assert 'installBtn' not in admin_elements.ids
    assert '__NONCE__' not in admin.text
    csp = admin.headers['content-security-policy']
    assert 'unsafe-inline' not in csp and 'nonce-' in csp
    nonce = csp.split("script-src 'nonce-")[1].split("'")[0]
    assert f'nonce="{nonce}"' in admin.text
    assert nonce not in http.get(admin_path).headers['content-security-policy']
    assert all(script.get('nonce') == nonce for script in admin_elements.scripts)
    public_nonce = public.headers['content-security-policy'].split("script-src 'nonce-")[1].split("'")[0]
    assert all(script.get('nonce') == public_nonce for script in public_elements.scripts)
    assert admin.headers['x-frame-options'] == 'DENY'
    assert admin.headers['x-content-type-options'] == 'nosniff'
    assert http.get('/?admin=old-token').status_code == 400
    for path in ['/web/index.html', '/.env', '/app/config.py', '/%2e%2e/.env']:
        assert http.get(path).status_code == 404


def test_public_download_uses_server_profile(client):
    assert 'href="/profile.mobileconfig"' in client[0].get('/').text


@pytest.mark.parametrize('method,path', [
    ('post', '/admin/add-account'), ('get', '/admin/accounts'),
    ('delete', '/admin/accounts/alice'), ('get', '/api/admin/me'),
    ('post', '/api/admin/logout'),
])
def test_all_admin_data_routes_require_session(client, method, path):
    http, accounts, *_ = client
    for headers in [{}, {'Authorization': 'Bearer ' + 'x' * 64}, {'Authorization': 'Basic abc'}]:
        response = getattr(http, method)(path, headers=headers)
        assert response.status_code == 401
    accounts.update_one.assert_not_called()
    accounts.delete_one.assert_not_called()


def test_subscriber_requires_admin_or_separate_service_token(client, monkeypatch):
    http, accounts, *_ = client
    assert http.get('/v1/subscribers/alice').status_code == 401
    accounts.find_one.assert_not_awaited()
    token = secrets.token_urlsafe(48)
    monkeypatch.setenv('SUBSCRIBER_API_TOKEN', token)
    get_settings.cache_clear()
    accounts.find_one.return_value = None
    response = http.get('/v1/subscribers/alice', headers={'Authorization': 'Bearer ' + token})
    assert response.status_code == 200
    assert response.json()['subscriber']['entitlements'] == {}
    assert http.get('/v1/subscribers/alice', headers={'Authorization': 'Bearer wrong'}).status_code == 401


def test_session_login_expiry_revocation(client):
    http, _, _, _, stored, *_ = client
    token, headers = sign_in(client)
    document = stored[token_digest(token)]
    assert token not in json.dumps(document, default=str)
    assert 3500 < (document['expires_at'] - datetime.now(timezone.utc)).total_seconds() <= 3600
    assert http.get('/api/admin/me', headers=headers).json() == {'email': 'admin@example.test'}
    document['expires_at'] = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert http.get('/admin/accounts', headers=headers).status_code == 401
    token, headers = sign_in(client)
    stored[token_digest(token)]['auth_version'] = 'old-password-version'
    assert http.get('/api/admin/me', headers=headers).status_code == 401
    token, headers = sign_in(client)
    stored[token_digest(token)]['admin_id'] = 'non-superadmin'
    assert http.get('/api/admin/me', headers=headers).status_code == 401
    token, headers = sign_in(client)
    assert http.post('/api/admin/logout', headers=headers).status_code == 204
    assert http.get('/api/admin/me', headers=headers).status_code == 401


def test_bad_login_and_rate_limit(client):
    http = client[0]
    wrong = {'email': 'admin@example.test', 'password': 'incorrect-password'}
    assert http.post('/api/admin/login', json=wrong).status_code == 401
    wrong['email'] = 'missing@example.test'
    assert http.post('/api/admin/login', json=wrong).status_code == 401
    # Invalid schema still counts against login attempts, without expensive hashing.
    for _ in range(8):
        assert http.post('/api/admin/login', json={}).status_code == 422
    response = http.post('/api/admin/login', json={})
    assert response.status_code == 429 and response.headers['retry-after'] == '60'


def test_shared_login_limit_blocks_before_password_verification(client):
    http, _, admins, sessions, *_ = client
    client[-1].state.login_limits.find_one_and_update.side_effect = None
    client[-1].state.login_limits.find_one_and_update.return_value = {'count': 11}
    result = http.post('/api/admin/login', json={
        'email': 'admin@example.test', 'password': client[-2],
    })
    assert result.status_code == 429
    admins.find_one.assert_not_awaited()
    sessions.insert_one.assert_not_awaited()


def test_login_uses_database_credentials_after_environment_changes(client, monkeypatch):
    http, _, admins, sessions, _, password, _ = client
    monkeypatch.setenv('SUPERADMIN_PASSWORD_HASH', hash_password('different-config-password'))
    monkeypatch.setenv('SUPERADMIN_EMAIL', 'other@example.test')
    get_settings.cache_clear()
    sign_in(client)
    admins.find_one.side_effect = None
    admins.find_one.return_value = None
    sessions.insert_one.reset_mock()
    response = http.post('/api/admin/login', json={
        'email': 'admin@example.test', 'password': password,
    })
    assert response.status_code == 401
    sessions.insert_one.assert_not_awaited()


def test_upsert_injection_and_subscriber(client):
    http, accounts, *_ = client
    _, headers = sign_in(client)
    future = datetime.now(timezone.utc) + timedelta(days=30)
    body = {'locket_id': 'alice', 'expires_date': future.isoformat()}
    assert http.post('/admin/add-account', headers=headers, json=body).status_code == 200
    accounts.update_one.assert_awaited_once()
    for value in [{'$ne': None}, '<img src=x onerror=alert(1)>', '../.env', 'a' * 129]:
        body['locket_id'] = value
        response = http.post('/admin/add-account', headers=headers, json=body)
        assert response.status_code == 422
        assert '<img' not in response.text and '$ne' not in response.text
    body['locket_id'] = 'alice'
    for expiry in ['2020-01-01T00:00:00Z', '2099-01-01T00:00:00']:
        body['expires_date'] = expiry
        assert http.post('/admin/add-account', headers=headers, json=body).status_code == 422
    accounts.find_one.return_value = {'locket_id': 'alice', 'expires_date': future}
    assert 'Gold' in http.get('/v1/subscribers/alice', headers=headers).json()['subscriber']['entitlements']
    accounts.find_one.return_value = None
    assert http.get('/v1/subscribers/missing', headers=headers).json()['subscriber']['entitlements'] == {}
    assert http.get('/admin/accounts?skip=10001', headers=headers).status_code == 422


def test_request_limits_hosts_and_errors(client):
    http, accounts, *_ = client
    _, headers = sign_in(client)
    response = http.post('/api/admin/login', content=b'x' * 8193)
    assert response.status_code == 413 and response.headers['x-frame-options'] == 'DENY'
    response = http.post('/api/admin/login', content=iter([b'x' * 4000, b'y' * 5000]))
    assert response.status_code == 413
    assert http.get('/', headers={'Host': 'attacker.example'}).status_code == 400
    accounts.find_one.side_effect = PyMongoError('private-db-detail')
    response = http.get('/v1/subscribers/alice', headers=headers)
    assert response.status_code == 503 and 'private-db-detail' not in response.text
    accounts.find_one.side_effect = RuntimeError('private-traceback')
    response = http.get('/v1/subscribers/alice', headers=headers)
    assert response.status_code == 500 and 'private-traceback' not in response.text
    assert response.headers['x-frame-options'] == 'DENY'


def test_password_hash_and_settings(password_pair):
    password, encoded = password_pair
    assert password not in encoded
    assert verify_password(password, encoded)
    assert not verify_password('wrong-password', encoded)
    assert not verify_password(password, 'sha256$weak')
    assert hash_password(password) != encoded
    with pytest.raises(ValidationError):
        Settings(_env_file=None, superadmin_password_hash='plaintext-is-rejected')


def test_expiry_boundary():
    now = datetime.now(timezone.utc)
    for account in [None, {'expires_date': now}, {'expires_date': now - timedelta(seconds=1)}]:
        assert subscriber_response('id', account, now)['subscriber']['entitlements'] == {}


@pytest.mark.parametrize('days_remaining', [30, -1, None])
def test_subscriber_history_is_stable_without_mutating_account(days_remaining):
    now = datetime(2026, 11, 3, 12, tzinfo=timezone.utc)
    account = ({'locket_id': 'id', 'expires_date': now + timedelta(days=days_remaining)}
               if days_remaining is not None else None)
    original = deepcopy(account)
    first = subscriber_response('id', account, now)
    later = subscriber_response('id', account, now + timedelta(seconds=10))
    assert account == original
    assert first['subscriber'] == later['subscriber']
    assert first['request_date'] != later['request_date']
    assert later['request_date_ms'] - first['request_date_ms'] == 10000
    subscriber = first['subscriber']
    assert subscriber['first_seen'] is None
    assert subscriber['original_purchase_date'] is None
    assert bool(subscriber['entitlements']) == (days_remaining == 30)
    if days_remaining == 30:
        entitlement = subscriber['entitlements']['Gold']
        subscription = subscriber['subscriptions'][entitlement['product_identifier']]
        assert entitlement['purchase_date'] is None
        assert subscription['purchase_date'] is None
        assert subscription['original_purchase_date'] is None
        assert entitlement['expires_date'] == '2026-12-03T12:00:00Z'


def test_app_instances_keep_routes_and_state_isolated():
    first, second = create_app(), create_app()
    first.state.audit_marker = 'first'
    assert not hasattr(second.state, 'audit_marker')
    first.dependency_overrides[get_accounts] = lambda: None
    assert get_accounts not in second.dependency_overrides
    paths = first.openapi()['paths']
    assert paths == second.openapi()['paths']
    assert {'/api/admin/login', '/admin/accounts', '/v1/subscribers/{account_id}'} <= paths.keys()


def test_date_only_expiry_is_stored_as_mongodb_datetime(client):
    http, accounts, *_ = client
    _, headers = sign_in(client)
    expiry = (datetime.now(timezone.utc) + timedelta(days=30)).date()
    result = http.post('/admin/add-account', headers=headers, json={
        'locket_id': 'date_only_user', 'expires_date': expiry.isoformat(),
    })
    assert result.status_code == 200
    stored = accounts.update_one.call_args.args[1]['$set']['expires_date']
    assert isinstance(stored, datetime) and stored.tzinfo is not None
    assert stored.date() == expiry
    assert (stored.hour, stored.minute, stored.second) == (23, 59, 59)
    from bson import BSON
    BSON.encode({'expires_date': stored})


def test_legacy_expiry_and_invalid_records_fail_closed():
    now = datetime(2026, 11, 3, 12, tzinfo=timezone.utc)
    result = subscriber_response('id', {'expires_date': '2026-11-03'}, now)
    assert result['subscriber']['entitlements']['Gold']['expires_date'] == '2026-11-03T23:59:59Z'
    for value in ['not-a-date', None, '2026-11-03T12:00:00']:
        assert subscriber_response('id', {'expires_date': value}, now)['subscriber']['entitlements'] == {}


def test_rate_limiter_bound_and_expiry(monkeypatch):
    monkeypatch.setattr('app.middleware.time.monotonic', lambda: 100)
    limiter = RateLimiter(capacity=1)
    assert limiter.allow(('ip', 'all'), 2)
    assert limiter.allow(('ip', 'all'), 2)
    assert not limiter.allow(('ip', 'all'), 2)
    assert not limiter.allow(('other-ip', 'all'), 2)
    monkeypatch.setattr('app.middleware.time.monotonic', lambda: 161)
    assert limiter.allow(('other-ip', 'all'), 2)


def test_profile_and_missing_configuration(client):
    http, *_, app = client
    response = http.get('/profile.mobileconfig')
    profile = plistlib.loads(response.content)
    assert profile['PayloadContent'][0]['DNSSettings']['ServerURL'] == 'https://dns.nextdns.io/abc123'
    assert response.headers['content-disposition'].endswith('"locket.mobileconfig"')
    app.state.profile = None
    assert http.get('/profile.mobileconfig').status_code == 503


@pytest.mark.parametrize('invalid_profile', [False, True])
def test_startup_creates_hashed_admin_and_session_ttl(client, monkeypatch, invalid_profile):
    app = client[-1]
    db = MagicMock()
    db.accounts = AsyncMock()
    db.admins = AsyncMock()
    db.sessions = AsyncMock()
    db.login_limits = AsyncMock()
    mongo = MagicMock()
    mongo.admin = AsyncMock()
    mongo.close = AsyncMock()
    mongo.__getitem__.return_value = db
    monkeypatch.setattr('app.database.AsyncMongoClient', MagicMock(return_value=mongo))
    if invalid_profile:
        monkeypatch.setattr('app.database.build_profile', MagicMock(side_effect=ValueError('invalid CA')))

    async def run():
        async with lifespan(app):
            assert bool(app.state.profile) is not invalid_profile
            assert client[0].get('/').status_code == 200
            assert client[0].get('/profile.mobileconfig').status_code == (503 if invalid_profile else 200)

    asyncio.run(run())
    db.sessions.create_index.assert_awaited_once_with('expires_at', expireAfterSeconds=0)
    update = db.admins.update_one.call_args.args[1]
    assert '$set' not in update
    document = update['$setOnInsert']
    assert document['password_hash'].startswith('pbkdf2_sha256$600000$')
    assert client[-2] not in str(document)
    mongo.close.assert_awaited_once()


def test_https_enforcement(client, monkeypatch):
    monkeypatch.setenv('REQUIRE_HTTPS', 'true')
    get_settings.cache_clear()
    app = create_app()
    http = TestClient(app, base_url='http://localhost')
    assert http.get('/').status_code == 400
    response = http.get('https://localhost/')
    assert response.status_code == 200
    assert response.headers['strict-transport-security'] == 'max-age=31536000'


def test_vercel_manifest_has_runtime_dependencies():
    from pathlib import Path
    import importlib
    import tomllib
    from fastapi import FastAPI

    root = Path(__file__).resolve().parent.parent
    config = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))
    requirements = {
        line.strip() for line in (root / 'requirements.txt').read_text().splitlines()
        if line.strip() and not line.lstrip().startswith('#')
    }
    assert set(config['project']['dependencies']) == requirements
    module, name = config['tool']['vercel']['entrypoint'].split(':')
    assert isinstance(getattr(importlib.import_module(module), name), FastAPI)


@pytest.mark.parametrize('correct', [True, False])
def test_check_password_command(client, monkeypatch, capsys, correct):
    import runpy
    import sys

    password = client[-2]
    monkeypatch.setattr(sys, 'argv', ['app.bootstrap', '--check'])
    monkeypatch.setattr('getpass.getpass', lambda prompt: password if correct else 'wrong-password')
    with pytest.raises(SystemExit) as result:
        runpy.run_module('app.bootstrap', run_name='__main__')
    assert result.value.code == (0 if correct else 1)
    output = capsys.readouterr().out
    assert password not in output
    assert 'pbkdf2_sha256$' not in output
