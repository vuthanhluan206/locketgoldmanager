"""Admin-managed device DNS profiles. Never handles third-party purchase receipts."""
import hashlib
from pathlib import Path
import os
import re
import secrets
from datetime import datetime, timezone
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.dns_profile import build_dns_profile
from app.models import AccountId
from app.managed_access import device_active
from app.security import require_admin

router = APIRouter(tags=["Managed DNS"])
admin_router = APIRouter(prefix="/api/admin/dns", dependencies=[Depends(require_admin)], tags=["Managed DNS"])

TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
DOMAIN_RE = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))*$")


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def dns_origin() -> str:
    value = os.environ.get("DNS_PUBLIC_ORIGIN", "").rstrip("/")
    u = urlsplit(value)
    if u.scheme != "https" or not u.hostname or u.username or u.password or u.query or u.fragment or u.path:
        raise HTTPException(503, "Configure DNS_PUBLIC_ORIGIN as https://dns.example.com")
    return value


def collection(request: Request):
    return request.app.state.accounts.database["dns_devices"]


class DeviceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=80)
    locket_id: AccountId | None = None
    expires_at: AwareDatetime
    block_domains: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("block_domains")
    @classmethod
    def clean_domains(cls, values: list[str]) -> list[str]:
        normalized = []
        for value in values:
            name = value.strip().lower().rstrip(".")
            if len(name) > 253 or not DOMAIN_RE.fullmatch(name):
                raise ValueError("Invalid DNS domain")
            normalized.append(name)
        return sorted(set(normalized))


def render(doc: dict) -> dict:
    return {
        "id": doc["_id"], "label": doc["label"], "locket_id": doc.get("locket_id"),
        "enabled": bool(doc["enabled"]),
        "expires_at": doc["expires_at"],
        "block_domains": doc.get("block_domains", []),
    }


@admin_router.post("/devices", status_code=201)
async def create_device(data: DeviceInput, request: Request):
    if data.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(422, "expires_at must be in the future")
    origin = dns_origin()
    if data.locket_id:
        account = await request.app.state.accounts.find_one({"locket_id": data.locket_id}, {"_id": 1})
        if account is None:
            raise HTTPException(422, "Linked Locket ID not found in managed accounts")
    token = secrets.token_urlsafe(32)
    device_id = secrets.token_hex(12)
    doc = {
        "_id": device_id, "token_hash": digest(token),
        "label": data.label, "locket_id": data.locket_id, "expires_at": data.expires_at,
        "enabled": True, "block_domains": data.block_domains,
        "created_at": datetime.now(timezone.utc),
    }
    coll = collection(request)
    await coll.create_index("token_hash", unique=True)
    await coll.insert_one(doc)
    return {
        **render(doc),
        "profile_download_url": f"/dns/profiles/{token}.mobileconfig",
        "dns_endpoint": f"{origin}/dns-query/{token}",
        "notice": "The download URL contains a secret. Share only with this device.",
    }


@admin_router.post("/devices/linked", status_code=201)
async def create_linked_device(data: DeviceInput, request: Request):
    """One admin action: create/extend the managed account and issue its DNS profile.

    MongoDB account expiry is not a third-party subscription or purchase.
    Retry is safe for the account, but each successful request issues a new DNS token.
    """
    if not data.locket_id:
        raise HTTPException(422, "Locket ID is required for linked profile")
    if data.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(422, "expires_at must be in the future")
    dns_origin()  # Fail before changing the account when gateway is not configured.
    await request.app.state.accounts.update_one(
        {"locket_id": data.locket_id},
        {
            "$setOnInsert": {"locket_id": data.locket_id},
            "$max": {"expires_date": data.expires_at},
        },
        upsert=True,
    )
    # Reuse the existing secure token generation / download route.
    return await create_device(data, request)


class RenewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    days: int = Field(default=30, ge=1, le=365)


@admin_router.post("/devices/{device_id}/renew")
async def renew_device(device_id: str, data: RenewInput, request: Request):
    """Renew a DNS token and its linked managed account without reinstalling."""
    from datetime import timedelta
    if not re.fullmatch(r"[0-9a-f]{24}", device_id):
        raise HTTPException(404, "Device not found")
    coll = collection(request)
    doc = await coll.find_one({"_id": device_id, "enabled": True})
    if not doc:
        raise HTTPException(404, "Device not found")
    existing = doc.get("expires_at")
    if not isinstance(existing, datetime):
        raise HTTPException(409, "Device expiry invalid")
    if existing.tzinfo is None:
        existing = existing.replace(tzinfo=timezone.utc)
    new_expiry = max(existing, datetime.now(timezone.utc)) + timedelta(days=data.days)
    if doc.get("locket_id"):
        account = await request.app.state.accounts.find_one(
            {"locket_id": doc["locket_id"]}, {"_id": 1}
        )
        if not account:
            raise HTTPException(409, "Linked managed account missing")
        await request.app.state.accounts.update_one(
            {"locket_id": doc["locket_id"]},
            {"$max": {"expires_date": new_expiry}},
        )
    updated = await coll.find_one_and_update(
        {"_id": device_id, "enabled": True},
        {"$max": {"expires_at": new_expiry}},
        return_document=True,
    )
    if not updated:
        raise HTTPException(404, "Device not found")
    return render(updated)


class SetExpiryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expires_at: AwareDatetime


@admin_router.post("/devices/{device_id}/set-expiry")
async def set_device_expiry(device_id: str, data: SetExpiryInput, request: Request):
    """Set an exact DNS expiry, including a past date for controlled testing.

    Linked managed accounts share an expiry, so changing their date can also
    affect other linked devices. It never changes third-party subscriptions.
    """
    if not re.fullmatch(r"[0-9a-f]{24}", device_id):
        raise HTTPException(404, "Device not found")
    coll = collection(request)
    doc = await coll.find_one({"_id": device_id, "enabled": True})
    if not doc:
        raise HTTPException(404, "Device not found")
    if doc.get("locket_id"):
        account = await request.app.state.accounts.find_one(
            {"locket_id": doc["locket_id"]}, {"_id": 1}
        )
        if not account:
            raise HTTPException(409, "Linked managed account missing")
        await request.app.state.accounts.update_one(
            {"locket_id": doc["locket_id"]},
            {"$set": {"expires_date": data.expires_at}},
        )
    updated = await coll.find_one_and_update(
        {"_id": device_id, "enabled": True},
        {"$set": {"expires_at": data.expires_at}},
        return_document=True,
    )
    if not updated:
        raise HTTPException(404, "Device not found")
    return render(updated)


@admin_router.put("/devices/{device_id}")
async def update_device(device_id: str, data: DeviceInput, request: Request):
    if not re.fullmatch(r"[0-9a-f]{24}", device_id):
        raise HTTPException(404, "Device not found")
    if data.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(422, "expires_at must be in the future")
    if data.locket_id:
        account = await request.app.state.accounts.find_one({"locket_id": data.locket_id}, {"_id": 1})
        if account is None:
            raise HTTPException(422, "Linked Locket ID not found in managed accounts")
    coll = collection(request)
    doc = await coll.find_one_and_update(
        {"_id": device_id, "enabled": True},
        {"$set": {
            "label": data.label,
            "locket_id": data.locket_id,
            "expires_at": data.expires_at,
            "block_domains": data.block_domains,
        }},
        return_document=True,
    )
    if doc is None:
        raise HTTPException(404, "Device not found")
    return render(doc)


@admin_router.get("/devices")
async def list_devices(request: Request):
    records = await collection(request).find({}, {"token_hash": 0}).sort("created_at", -1).limit(100).to_list(100)
    return [render(x) for x in records]


@admin_router.post("/devices/{device_id}/revoke", status_code=204)
async def revoke_device(device_id: str, request: Request):
    if not re.fullmatch(r"[0-9a-f]{24}", device_id):
        raise HTTPException(404, "Device not found")
    result = await collection(request).update_one({"_id": device_id}, {"$set": {"enabled": False}})
    if not result.matched_count:
        raise HTTPException(404, "Device not found")
    return Response(status_code=204)


@router.get("/dns/profiles/{token}.mobileconfig", include_in_schema=False)
async def download_profile(token: str, request: Request):
    if not TOKEN_RE.fullmatch(token):
        raise HTTPException(404, "Profile not found")
    doc = await collection(request).find_one({"token_hash": digest(token), "enabled": True})
    if not await device_active(doc, request.app.state.accounts):
        raise HTTPException(404, "Profile not found")
    content = build_dns_profile(f"{dns_origin()}/dns-query/{token}", "Managed Encrypted DNS")
    return Response(content, media_type="application/x-apple-aspen-config", headers={
        "Content-Disposition": 'attachment; filename="managed-dns.mobileconfig"',
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
    })


@router.get("/dns/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def dns_dashboard(request: Request):
    page = (Path(__file__).resolve().parents[2] / "web" / "dns-dashboard.html").read_text(encoding="utf-8")
    return HTMLResponse(page.replace("__NONCE__", request.state.csp_nonce), headers={"Cache-Control": "no-store"})
