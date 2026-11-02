import hashlib
import re
import secrets
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from .config import get_settings

bearer = HTTPBearer(auto_error=False)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


async def require_subscriber_access(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
):
    configured = get_settings().subscriber_api_token
    if credentials is not None and configured is not None:
        if secrets.compare_digest(credentials.credentials.encode('utf-8'),
                                  configured.get_secret_value().encode('ascii')):
            return
    # Admin sessions can inspect records; a separate token is only for trusted servers.
    await require_admin(request, credentials)


async def require_admin(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
):
    unauthorized = HTTPException(401, "Invalid or expired session", headers={"WWW-Authenticate": "Bearer"})
    if credentials is None or not re.fullmatch(r"[A-Za-z0-9_-]{64}", credentials.credentials):
        raise unauthorized
    session = await request.app.state.sessions.find_one({
        "_id": token_digest(credentials.credentials),
        "expires_at": {"$gt": datetime.now(timezone.utc)},
    })
    if session is None or session.get("admin_id") != "superadmin":
        raise unauthorized
    admin = await request.app.state.admins.find_one({"_id": session["admin_id"]})
    if admin is None or admin.get("auth_version") != session["auth_version"]:
        raise unauthorized
    return {"session_id": session["_id"], "email": admin["email"]}
