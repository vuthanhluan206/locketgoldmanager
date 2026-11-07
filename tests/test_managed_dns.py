"""Simple regression tests for iOS DoH profile generation and DNS matching."""
import plistlib
from datetime import datetime, timedelta, timezone

from app.dns_profile import build_dns_profile
from vps.doh_gateway import denied_domain


def test_profile_is_encrypted_dns_without_root_ca_or_vpn():
    raw = build_dns_profile("https://dns.example.com/dns-query/abcdefghijklmnopqrstuvwxyzABCDEF12345678")
    profile = plistlib.loads(raw)
    assert profile["PayloadType"] == "Configuration"
    assert len(profile["PayloadContent"]) == 1
    payload = profile["PayloadContent"][0]
    assert payload["PayloadType"] == "com.apple.dnsSettings.managed"
    assert payload["DNSSettings"]["DNSProtocol"] == "HTTPS"
    assert payload["DNSSettings"]["ServerURL"].startswith("https://")


def test_domain_matching_is_exact_or_subdomain_only():
    assert denied_domain("ads.example.com.", ["example.com"])
    assert denied_domain("EXAMPLE.COM", ["example.com"])
    assert not denied_domain("notexample.com.", ["example.com"])


def test_profile_rejects_untrusted_scheme():
    import pytest
    with pytest.raises(ValueError):
        build_dns_profile("http://dns.example.com/dns-query")


def test_unregistered_device_cannot_use_doh(monkeypatch):
    import base64
    import time
    import dns.message
    from fastapi.testclient import TestClient
    from vps.doh_gateway import app

    monkeypatch.setenv("MANAGER_API_ORIGIN", "https://manager.example.com")
    monkeypatch.setenv("DNS_GATEWAY_API_TOKEN", "x" * 64)
    token = "A" * 43
    query = dns.message.make_query("example.com", "A")
    encoded = base64.urlsafe_b64encode(query.to_wire()).rstrip(b"=").decode("ascii")
    with TestClient(app) as client:
        client.app.state.cache[token] = (
            time.monotonic() + 60, {"known": False, "block_domains": []}
        )
        response = client.get(f"/dns-query/{token}?dns={encoded}")
        assert response.status_code == 403


def test_known_device_blocks_matching_domain(monkeypatch):
    import base64
    import time
    import dns.message
    import dns.rcode
    from fastapi.testclient import TestClient
    from vps.doh_gateway import app

    monkeypatch.setenv("MANAGER_API_ORIGIN", "https://manager.example.com")
    monkeypatch.setenv("DNS_GATEWAY_API_TOKEN", "x" * 64)
    token = "A" * 43
    query = dns.message.make_query("tracker.example", "A")
    encoded = base64.urlsafe_b64encode(query.to_wire()).rstrip(b"=").decode("ascii")
    with TestClient(app) as client:
        client.app.state.cache[token] = (
            time.monotonic() + 60,
            {"known": True, "block_domains": ["tracker.example"]},
        )
        response = client.get(f"/dns-query/{token}?dns={encoded}")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/dns-message"
        assert dns.message.from_wire(response.content).rcode() == dns.rcode.NXDOMAIN
