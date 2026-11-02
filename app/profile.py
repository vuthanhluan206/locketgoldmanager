import plistlib
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5
from datetime import datetime, timezone
from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding
from fastapi import HTTPException
from .config import Settings


def payload(kind: str, name: str) -> dict:
    identifier = 'local.license-manager.' + name.lower().replace(' ', '-')
    return {'PayloadType': kind, 'PayloadVersion': 1, 'PayloadIdentifier': identifier,
            'PayloadUUID': str(uuid5(NAMESPACE_URL, identifier)), 'PayloadDisplayName': name}


def build_profile(settings: Settings) -> bytes:
    if not settings.nextdns_id:
        raise HTTPException(503, 'Chưa cấu hình NEXTDNS_ID trên server.')
    dns = payload('com.apple.dnsSettings.managed', 'NextDNS')
    dns['DNSSettings'] = {'DNSProtocol': 'HTTPS',
                          'ServerURL': f'https://dns.nextdns.io/{settings.nextdns_id}'}
    contents = [dns]
    if settings.root_ca_path:
        path = Path(settings.root_ca_path).resolve(strict=True)
        if not path.is_file() or path.stat().st_size > 65536:
            raise ValueError('ROOT_CA_PATH must be a certificate file smaller than 64 KiB')
        raw = path.read_bytes()
        if b'PRIVATE KEY' in raw:
            raise ValueError('ROOT_CA_PATH must never contain a private key')
        cert = (x509.load_pem_x509_certificate(raw) if b'-----BEGIN CERTIFICATE' in raw
                else x509.load_der_x509_certificate(raw))
        if not cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
            raise ValueError('ROOT_CA_PATH must contain a CA certificate')
        now = datetime.now(timezone.utc)
        if not cert.not_valid_before_utc <= now < cert.not_valid_after_utc:
            raise ValueError('The CA certificate is expired or not yet valid')
        ca = payload('com.apple.security.root', 'Root CA')
        ca['PayloadContent'] = cert.public_bytes(Encoding.DER)
        contents.append(ca)
    profile = payload('Configuration', 'Locket Gold DNS')
    profile.update(PayloadContent=contents, PayloadRemovalDisallowed=False,
                   PayloadDescription='Cấu hình NextDNS. Không tự cấp quyền trong ứng dụng Locket.')
    return plistlib.dumps(profile)
