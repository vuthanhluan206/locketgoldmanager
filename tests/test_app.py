import os
import plistlib
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

os.environ['ADMIN_TOKEN'] = 'test-only-secret-0123456789-abcdef-0123456789'
from app.config import Settings, get_settings
from app.database import get_accounts
from app.main import app
from app.models import AccountInput, subscriber_response
from app.profile import build_profile


@pytest.fixture
def client():
    get_settings.cache_clear()
    accounts = AsyncMock()
    app.dependency_overrides[get_accounts] = lambda: accounts
    # Without a context manager TestClient skips MongoDB lifespan: these are isolated HTTP tests.
    yield TestClient(app), accounts
    app.dependency_overrides.clear()


def test_admin_is_server_protected(client):
    http, accounts = client
    assert 'accountForm' not in http.get('/').text
    assert http.get('/?admin=wrong').status_code == 404
    response = http.get('/?admin=' + os.environ['ADMIN_TOKEN'])
    assert 'accountForm' in response.text
    assert response.headers['referrer-policy'] == 'no-referrer'
    assert http.post('/admin/add-account', json={}).status_code == 401
    assert http.delete('/admin/accounts/alice').status_code == 401
    assert http.get('/admin/accounts').status_code == 401
    accounts.update_one.assert_not_called()


def test_upsert_validation_and_subscriber(client):
    http, accounts = client
    headers = {'Authorization': 'Bearer ' + os.environ['ADMIN_TOKEN']}
    future = datetime.now(timezone.utc) + timedelta(days=30)
    body = {'locket_id': 'alice', 'expires_date': future.isoformat()}
    assert http.post('/admin/add-account', headers=headers, json=body).status_code == 200
    accounts.update_one.assert_awaited_once()
    body['expires_date'] = '2020-01-01T00:00:00Z'
    assert http.post('/admin/add-account', headers=headers, json=body).status_code == 422
    accounts.find_one.return_value = {'locket_id': 'alice', 'expires_date': future}
    assert 'Gold' in http.get('/v1/subscribers/alice').json()['subscriber']['entitlements']
    accounts.find_one.return_value = None
    assert http.get('/v1/subscribers/missing').json()['subscriber']['entitlements'] == {}


def test_expiry_boundary_and_timezone():
    now = datetime.now(timezone.utc)
    for account in [None, {'expires_date': now}, {'expires_date': now - timedelta(seconds=1)}]:
        assert subscriber_response('id', account, now)['subscriber']['entitlements'] == {}
    with pytest.raises(ValidationError):
        AccountInput(locket_id='alice', expires_date='2099-01-01T00:00:00')


def test_profile_has_nextdns_payload():
    config = Settings(nextdns_id='abc123', root_ca_path='')
    profile = plistlib.loads(build_profile(config))
    dns = profile['PayloadContent'][0]
    assert dns['PayloadType'] == 'com.apple.dnsSettings.managed'
    assert dns['DNSSettings']['ServerURL'] == 'https://dns.nextdns.io/abc123'
