import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from pymongo import ReturnDocument
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from .config import get_settings
from .middleware import client_ip

bearer = HTTPBearer(auto_error=False)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


async def require_subscriber_access(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
):
    unauthorized = HTTPException(401, "Invalid or missing subscriber API token", headers={"WWW-Authenticate": "Bearer"})
    if credentials is None:
        raise unauthorized

    settings = get_settings()
    configured = settings.subscriber_api_token
    if configured is not None and secrets.compare_digest(
        credentials.credentials.encode("utf-8"),
        configured.get_secret_value().encode("ascii"),
    ):
        return

    if re.fullmatch(r"[A-Za-z0-9_-]{64}", credentials.credentials):
        sessions = getattr(request.app.state, "sessions", None)
        admins = getattr(request.app.state, "admins", None)
        if sessions is not None and admins is not None:
            session = await sessions.find_one({
                "_id": token_digest(credentials.credentials),
                "expires_at": {"$gt": datetime.now(timezone.utc)},
            })
            if session is not None and session.get("admin_id") == "superadmin":
                admin = await admins.find_one({"_id": session["admin_id"]})
                if admin is not None and admin.get("auth_version") == session.get("auth_version"):
                    return

    raise unauthorized


async def require_admin(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
):
    now = datetime.now(timezone.utc)
    ip_key = hashlib.sha256(client_ip(request.scope).encode('utf-8')).hexdigest()
    bucket = await request.app.state.login_limits.find_one_and_update(
        {'_id': f'admin:{int(now.timestamp()) // 60}:{ip_key}'},
        {'$inc': {'count': 1}, '$setOnInsert': {'expires_at': now + timedelta(minutes=2)}},
        upsert=True, return_document=ReturnDocument.AFTER,
    )
    if bucket['count'] > 60:
        raise HTTPException(429, 'Too many admin requests', headers={'Retry-After': '60'})
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