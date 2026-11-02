import asyncio
import logging
import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from pymongo import ReturnDocument

from .config import get_settings
from .passwords import verify_password
from .security import require_admin, token_digest

router = APIRouter(prefix='/api/admin', tags=['Authentication'])
logger = logging.getLogger(__name__)


async def enforce_login_limit(request: Request):
    now = datetime.now(timezone.utc)
    window = int(now.timestamp()) // 60
    client_ip = request.client.host if request.client else 'unknown'
    ip_key = hashlib.sha256(client_ip.encode('utf-8')).hexdigest()
    # Shared counters survive serverless cold starts; local middleware also limits malformed requests.
    for key, limit in [(ip_key, 10), ('global', 30)]:
        bucket = await request.app.state.login_limits.find_one_and_update(
            {'_id': f'{window}:{key}'},
            {'$inc': {'count': 1}, '$setOnInsert': {'expires_at': now + timedelta(minutes=2)}},
            upsert=True, return_document=ReturnDocument.AFTER,
        )
        if bucket['count'] > limit:
            raise HTTPException(429, 'Too many login attempts', headers={'Retry-After': '60'})


class LoginInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email: str = Field(min_length=3, max_length=254, pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
    password: SecretStr = Field(min_length=1, max_length=256)

    @field_validator('email')
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()


@router.post('/login')
async def login(data: LoginInput, request: Request):
    await enforce_login_limit(request)
    settings = get_settings()
    admin = await request.app.state.admins.find_one({'_id': 'superadmin'})
    encoded = admin['password_hash'] if admin else settings.superadmin_password_hash.get_secret_value()
    # Also perform an expensive verification for unknown emails; keep the event loop responsive.
    valid = await asyncio.to_thread(verify_password, data.password.get_secret_value(), encoded)
    if not valid or admin is None or data.email != admin['email']:
        logger.warning(
            'ADMIN_LOGIN_REJECTED: credentials rejected',
        )
        raise HTTPException(401, 'Email hoặc mật khẩu không đúng')
    token = secrets.token_urlsafe(48)
    expires = datetime.now(timezone.utc) + timedelta(seconds=settings.session_ttl_seconds)
    await request.app.state.sessions.insert_one({
        '_id': token_digest(token), 'admin_id': admin['_id'],
        'auth_version': admin['auth_version'], 'expires_at': expires,
    })
    return {'access_token': token, 'token_type': 'bearer', 'expires_at': expires}


@router.get('/me')
async def me(admin: Annotated[dict, Depends(require_admin)]):
    return {'email': admin['email']}


@router.post('/logout', status_code=204)
async def logout(request: Request, admin: Annotated[dict, Depends(require_admin)]):
    await request.app.state.sessions.delete_one({'_id': admin['session_id']})
    return Response(status_code=204)
