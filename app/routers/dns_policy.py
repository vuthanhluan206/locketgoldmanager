"""Private policy endpoint for the user's own encrypted DNS gateway."""
import hashlib
import os
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from fastapi import Depends

router = APIRouter(tags=["Managed DNS Internal"])
bearer = HTTPBearer(auto_error=False)


class PolicyLookup(BaseModel):
    token: str = Field(min_length=32, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


@router.post("/api/internal/dns/policy", include_in_schema=False)
async def policy(
    data: PolicyLookup,
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
):
    secret = os.environ.get("DNS_GATEWAY_API_TOKEN", "")
    if len(secret) < 32:
        raise HTTPException(503, "Gateway authentication not configured")
    if credentials is None or not secrets.compare_digest(
        credentials.credentials.encode("utf-8"), secret.encode("utf-8")
    ):
        raise HTTPException(401, "Unauthorized", headers={"WWW-Authenticate": "Bearer"})
    coll = request.app.state.accounts.database["dns_devices"]
    token_hash = hashlib.sha256(data.token.encode("ascii")).hexdigest()
    doc = await coll.find_one({"token_hash": token_hash}, {
        "enabled": 1, "expires_at": 1, "block_domains": 1
    })
    expiry = doc.get("expires_at") if doc else None
    if isinstance(expiry, datetime) and expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    active = bool(
        doc and doc.get("enabled") is True and expiry
        and expiry > datetime.now(timezone.utc)
    )
    # Expired/unknown devices use ordinary DNS rather than causing a network outage.
    return {
        "known": bool(doc),
        "active": active,
        "expires_at": expiry.isoformat() if expiry else None,
        "block_domains": doc.get("block_domains", []) if active else [],
    }
