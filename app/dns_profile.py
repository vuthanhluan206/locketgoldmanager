"""Produce an iOS encrypted-DNS configuration profile without installing a root CA."""
import plistlib
import uuid
from urllib.parse import urlsplit


def build_dns_profile(server_url: str, display_name: str = "Managed DNS") -> bytes:
    parsed = urlsplit(server_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("ServerURL must be a valid HTTPS URL")
    dns_payload = {
        "PayloadType": "com.apple.dnsSettings.managed",
        "PayloadVersion": 1,
        "PayloadIdentifier": "com.example.manageddns.settings",
        "PayloadUUID": str(uuid.uuid4()).upper(),
        "PayloadDisplayName": display_name,
        "DNSSettings": {
            "DNSProtocol": "HTTPS",
            "ServerURL": server_url,
        },
    }
    config = {
        "PayloadType": "Configuration",
        "PayloadVersion": 1,
        "PayloadIdentifier": "com.example.manageddns",
        "PayloadUUID": str(uuid.uuid4()).upper(),
        "PayloadDisplayName": display_name,
        "PayloadDescription": "Encrypted DNS configuration managed by your account.",
        "PayloadOrganization": "DNS Manager",
        "PayloadRemovalDisallowed": False,
        "PayloadScope": "System",
        "PayloadContent": [dns_payload],
    }
    return plistlib.dumps(config, fmt=plistlib.FMT_XML)
