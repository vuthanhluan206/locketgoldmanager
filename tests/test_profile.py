import plistlib
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509.oid import NameOID

from app.config import Settings
from app.profile import build_profile


@pytest.fixture
def settings():
    return Settings(
        _env_file=None, nextdns_id='abc123', root_ca_path='', root_ca_pem='',
        superadmin_email='admin@example.test', mongodb_uri='mongodb://localhost',
        superadmin_password_hash='pbkdf2_sha256$600000$' + '00' * 16 + '$' + '00' * 32,
    )


def certificate(*, ca=True, expired=False, intermediate=False):
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Test Root CA')])
    issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Other CA')]) if intermediate else subject
    now = datetime.now(timezone.utc)
    return (x509.CertificateBuilder().subject_name(subject).issuer_name(issuer)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=2))
            .not_valid_after(now + timedelta(days=-1 if expired else 30))
            .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))


@pytest.mark.parametrize('source', ['pem', 'escaped_pem', 'pem_file', 'der_file'])
def test_profile_contains_dns_and_der_root_ca(settings, tmp_path, source):
    cert = certificate()
    pem = cert.public_bytes(Encoding.PEM).decode('ascii')
    if source in ('pem', 'escaped_pem'):
        settings.root_ca_pem = pem if source == 'pem' else pem.replace('\n', '\\n')
    else:
        path = tmp_path / 'root-ca.cer'
        path.write_bytes(cert.public_bytes(Encoding.DER) if source == 'der_file' else pem.encode())
        settings.root_ca_path = str(path)
    raw = build_profile(settings)
    assert raw.startswith(b'<?xml')
    profile = plistlib.loads(raw)
    assert profile['PayloadScope'] == 'System'
    dns, root = profile['PayloadContent']
    assert dns['PayloadType'] == 'com.apple.dnsSettings.managed'
    assert dns['DNSSettings']['ServerURL'] == 'https://dns.nextdns.io/abc123'
    assert root['PayloadType'] == 'com.apple.security.root'
    assert root['PayloadContent'] == cert.public_bytes(Encoding.DER)
    uuids = [item['PayloadUUID'] for item in (profile, dns, root)]
    assert len(set(uuids)) == 3
    assert all(UUID(value).version == 4 for value in uuids)
    assert len({item['PayloadIdentifier'] for item in (profile, dns, root)}) == 3
    assert plistlib.loads(build_profile(settings))['PayloadUUID'] != profile['PayloadUUID']


@pytest.mark.parametrize('problem', ['expired', 'leaf', 'intermediate', 'private_key', 'chain', 'malformed', 'oversize', 'conflict'])
def test_profile_rejects_invalid_root_ca(settings, problem):
    pem = certificate(ca=problem != 'leaf', expired=problem == 'expired',
                      intermediate=problem == 'intermediate').public_bytes(Encoding.PEM).decode()
    settings.root_ca_pem = pem
    if problem == 'private_key':
        settings.root_ca_pem += '\n-----BEGIN PRIVATE KEY-----'
    elif problem == 'chain':
        settings.root_ca_pem += pem
    elif problem == 'malformed':
        settings.root_ca_pem = 'not a certificate'
    elif problem == 'oversize':
        settings.root_ca_pem = 'x' * 65537
    elif problem == 'conflict':
        settings.root_ca_path = 'another-certificate.pem'
    with pytest.raises(ValueError):
        build_profile(settings)
