import struct
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware import SecurityMiddleware
from app.routes import router


@pytest.fixture
def icon_client(monkeypatch):
    settings = SimpleNamespace(
        allowed_hosts=['testserver'], require_https=False,
        trusted_proxy_cidrs=[], turnstile_site_key='',
    )
    monkeypatch.setattr('app.middleware.get_settings', lambda: settings)
    monkeypatch.setattr('app.routes.get_settings', lambda: settings)
    app = FastAPI()
    app.include_router(router)
    app.add_middleware(SecurityMiddleware)
    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize('path,mime,size', [
    ('/favicon.ico', 'image/vnd.microsoft.icon', 32),
    ('/apple-touch-icon.png', 'image/png', 180),
    ('/apple-touch-icon-precomposed.png', 'image/png', 180),
])
def test_icons(icon_client, path, mime, size):
    response = icon_client.get(path)
    assert response.status_code == 200
    assert response.headers['content-type'] == mime
    assert "img-src 'self'" in response.headers['content-security-policy']
    data = response.content
    if path.endswith('.ico'):
        assert struct.unpack('<HHH', data[:6]) == (0, 1, 1)
        length, offset = struct.unpack('<II', data[14:22])
        assert len(data[offset:]) == length
        data = data[offset:]
    assert data.startswith(b'\x89PNG\r\n\x1a\n')
    assert struct.unpack('>II', data[16:24]) == (size, size)


def test_icon_links_and_private_paths(icon_client):
    response = icon_client.get('/')
    assert response.status_code == 200
    assert 'href="/favicon.ico"' in response.text
    assert 'href="/apple-touch-icon.png"' in response.text
    for path in ['/web/index.html', '/web/favicon.ico', '/.env']:
        assert icon_client.get(path).status_code == 404
