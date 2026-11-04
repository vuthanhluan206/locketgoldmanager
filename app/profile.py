import plistlib
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone
from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding
from fastapi import HTTPException
from .config import Settings


def payload(kind: str, name: str) -> dict:
    identifier = 'local.license-manager.' + name.lower().replace(' ', '-')
    return {'PayloadType': kind, 'PayloadVersion': 1, 'PayloadIdentifier': identifier,
            'PayloadUUID': str(uuid4()).upper(), 'PayloadDisplayName': name}


def build_profile(settings: Settings) -> bytes:
    if not settings.nextdns_id:
        raise HTTPException(503, 'Chưa cấu hình NEXTDNS_ID trên server.')
    dns = payload('com.apple.dnsSettings.managed', 'NextDNS')
    dns['DNSSettings'] = {'DNSProtocol': 'HTTPS',
                          'ServerURL': f'https://dns.nextdns.io/{settings.nextdns_id}'}
    contents = [dns]
    if settings.root_ca_path and settings.root_ca_pem:
        raise ValueError('Set only one of ROOT_CA_PATH or ROOT_CA_PEM')
    if settings.root_ca_path or settings.root_ca_pem:
        if settings.root_ca_pem:
            # Accept both pasted multiline PEM and literal backslash-n from environment UIs.
            raw = settings.root_ca_pem.replace('\\n', '\n').strip().encode('utf-8')
        else:
            path = Path(settings.root_ca_path).resolve(strict=True)
            if not path.is_file():
                raise ValueError('ROOT_CA_PATH must be a certificate file')
            with path.open('rb') as certificate_file:
                raw = certificate_file.read(65537)
        if not raw or len(raw) > 65536:
            raise ValueError('Root CA must be a certificate no larger than 64 KiB')
        if b'PRIVATE KEY' in raw:
            raise ValueError('Root CA must never contain a private key')
        if b'-----BEGIN CERTIFICATE' in raw and raw.count(b'-----BEGIN CERTIFICATE') != 1:
            raise ValueError('Provide exactly one root CA certificate, not a certificate chain')
        cert = (x509.load_pem_x509_certificate(raw) if b'-----BEGIN CERTIFICATE' in raw
                else x509.load_der_x509_certificate(raw))
        if not cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
            raise ValueError('Root CA must contain a CA certificate')
        # An intermediate CA is not a self-signed root trust anchor.
        cert.verify_directly_issued_by(cert)
        try:
            usage = cert.extensions.get_extension_for_class(x509.KeyUsage).value
        except x509.ExtensionNotFound:
            usage = None
        if usage is not None and not usage.key_cert_sign:
            raise ValueError('Root CA must allow certificate signing')
        now = datetime.now(timezone.utc)
        if not cert.not_valid_before_utc <= now < cert.not_valid_after_utc:
            raise ValueError('The CA certificate is expired or not yet valid')
        ca = payload('com.apple.security.root', 'Root CA')
        ca['PayloadCertificateFileName'] = 'root-ca.cer'
        ca['PayloadContent'] = cert.public_bytes(Encoding.DER)
        contents.append(ca)
    profile = payload('Configuration', 'Locket Gold DNS')
    profile.update(PayloadContent=contents, PayloadRemovalDisallowed=False, PayloadScope='System',
                   PayloadOrganization='vuthanhluan.bond',
                   PayloadDescription='Cấu hình DNS được cung cấp bởi nhà phát triển vuthanhluan.bond. '
                   'Dành cho trải nghiệm chia sẻ ảnh, quay và đăng video, xem lại khoảnh khắc trên Locket. '
                   'Các tính năng phụ thuộc ứng dụng và quyền tài khoản đang sử dụng.')
    return plistlib.dumps(profile, fmt=plistlib.FMT_XML)
