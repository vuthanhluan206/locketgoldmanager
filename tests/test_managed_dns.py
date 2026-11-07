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
