"""Admin-only certificate inventory. Never changes DNS trust or third-party TLS."""
from datetime import datetime, timezone
from hashlib import sha256

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.security import require_admin

router = APIRouter(prefix="/api/admin/certificates", dependencies=[Depends(require_admin)], tags=["Admin CA inventory"])


class CertificateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pem: str = Field(min_length=60, max_length=16384)


def inspect_certificate(pem: str) -> dict:
    if "PRIVATE KEY" in pem or pem.count("-----BEGIN CERTIFICATE-----") != 1 or pem.count("-----END CERTIFICATE-----") != 1:
        raise HTTPException(422, "Only one public PEM certificate is accepted; never submit a private key")
    try:
        cert = x509.load_pem_x509_certificate(pem.strip().encode("ascii"))
        if not cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
            raise ValueError("Certificate is not a CA")
        cert.verify_directly_issued_by(cert)
        if not cert.not_valid_before_utc <= datetime.now(timezone.utc) < cert.not_valid_after_utc:
            raise ValueError("Certificate is not currently valid")
        try:
            usage = cert.extensions.get_extension_for_class(x509.KeyUsage).value
            if not usage.key_cert_sign:
                raise ValueError("Certificate cannot sign certificates")
        except x509.ExtensionNotFound:
            pass
    except (ValueError, UnicodeError, x509.ExtensionNotFound, x509.InvalidVersion) as exc:
        raise HTTPException(422, "Invalid, expired or non-root CA certificate") from exc
    normalized = cert.public_bytes(serialization.Encoding.PEM).decode("ascii")
    return {
        "pem": normalized,
        "fingerprint_sha256": sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest(),
        "subject": cert.subject.rfc4514_string(),
        "not_before": cert.not_valid_before_utc,
        "not_after": cert.not_valid_after_utc,
    }


def inventory(request: Request):
    return request.app.state.accounts.database["certificate_inventory"]


def public_meta(doc: dict | None) -> dict:
    return {"configured": False} if not doc else {
        "configured": True,
        "fingerprint_sha256": doc["fingerprint_sha256"],
        "subject": doc["subject"],
        "not_before": doc["not_before"],
        "not_after": doc["not_after"],
        "updated_at": doc["updated_at"],
        "distribution_enabled": False,
    }


@router.get("/root")
async def get_root(request: Request):
    doc = await inventory(request).find_one({"_id": "admin_root_ca"}, {"pem": 0})
    return public_meta(doc)


@router.put("/root")
async def put_root(data: CertificateInput, request: Request):
    cert = inspect_certificate(data.pem)
    doc = {"_id": "admin_root_ca", **cert, "updated_at": datetime.now(timezone.utc)}
    await inventory(request).replace_one({"_id": "admin_root_ca"}, doc, upsert=True)
    return public_meta(doc)


@router.delete("/root", status_code=204)
async def delete_root(request: Request):
    await inventory(request).delete_one({"_id": "admin_root_ca"})
    return Response(status_code=204)
