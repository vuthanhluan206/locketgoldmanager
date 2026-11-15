from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.locket_modifier import router
from app.middleware import MAX_PROXY_BODY, SecurityMiddleware


@pytest.fixture
def read_proxy(monkeypatch):
    settings = SimpleNamespace(allowed_hosts=['testserver'], require_https=False,
                               trusted_proxy_cidrs=[])
    monkeypatch.setattr('app.middleware.get_settings', lambda: settings)
    app = FastAPI()
    app.add_middleware(SecurityMiddleware)

    @app.post('/api/admin/login')
    async def local_login():
        return {'local': True}

    app.include_router(router)
    app.state.accounts = AsyncMock()
    upstream = MagicMock(return_value=(204, {}, b''))
    monkeypatch.setattr('app.locket_modifier._forward_upstream', upstream)
    with TestClient(app) as client:
        yield client, upstream, app


@pytest.mark.parametrize('prefix', ['', '/proxy'])
def test_read_update_preserves_request_and_upstream_status(read_proxy, prefix):
    client, upstream, app = read_proxy
    # Representative path: the real Locket endpoint must be confirmed from device logs.
    body = b'{"message_id":"test","read":true}'
    response = client.post(prefix + '/messages/read?sync=1', content=body,
                           headers={'Authorization': 'Bearer upstream-token',
                                    'Content-Type': 'application/json'})
    assert response.status_code == 204
    url, forwarded_body, headers, method, _ = upstream.call_args.args
    assert url == 'https://api.locketcamera.com/messages/read?sync=1'
    assert forwarded_body == body
    assert method == 'POST'
    assert headers['authorization'] == 'Bearer upstream-token'
    app.state.accounts.find_one.assert_not_called()


@pytest.mark.parametrize('prefix', ['', '/proxy'])
def test_proxy_burst_does_not_block_read_update_or_login(read_proxy, prefix):
    client, upstream, _ = read_proxy
    for _ in range(121):
        assert client.get(prefix + '/messages').status_code == 204
    assert client.post(prefix + '/messages/read', json={'read': True}).status_code == 204
    assert client.post('/api/admin/login', json={}).status_code == 200


def test_local_api_keeps_small_body_and_login_limits(read_proxy):
    client, upstream, _ = read_proxy
    assert client.post('/api/admin/login', content=b'x' * 8193).status_code == 413
    for _ in range(9):
        assert client.post('/api/admin/login', json={}).status_code == 200
    assert client.post('/api/admin/login', json={}).status_code == 429
    upstream.assert_not_called()


@pytest.mark.parametrize('prefix', ['', '/proxy'])
def test_proxy_request_above_local_body_limit_is_forwarded(read_proxy, prefix):
    client, upstream, _ = read_proxy
    body = b'x' * 8193
    assert client.post(prefix + '/messages/read', content=body).status_code == 204
    assert upstream.call_args.args[1] == body


def test_read_flags_and_upstream_errors_are_not_fabricated(read_proxy):
    client, upstream, _ = read_proxy
    payload = b'{"read":false,"unread_count":2}'
    upstream.return_value = (200, {'Content-Type': 'application/json'}, payload)
    assert client.get('/messages').json() == {'read': False, 'unread_count': 2}
    upstream.return_value = (401, {'Content-Type': 'application/json'}, b'{"error":"expired"}')
    assert client.post('/messages/read', json={}).status_code == 401


@pytest.mark.parametrize('prefix', ['', '/proxy'])
def test_proxy_still_rejects_oversized_requests_and_untrusted_hosts(read_proxy, prefix):
    client, upstream, _ = read_proxy
    assert client.post(prefix + '/messages/read', content=b'',
                       headers={'Content-Length': str(MAX_PROXY_BODY + 1)}).status_code == 413
    assert client.post(prefix + '/messages/read', content=b'',
                       headers={'Host': 'untrusted.example'}).status_code == 400
    upstream.assert_not_called()
