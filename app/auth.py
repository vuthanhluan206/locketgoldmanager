import asyncio
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from .config import get_settings
from .passwords import verify_password
from .security import require_admin, token_digest

router = APIRouter(prefix='/api/admin', tags=['Authentication'])
logger = logging.getLogger(__name__)


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
    settings = get_settings()
    admin = await request.app.state.admins.find_one({'_id': 'superadmin'})
    configured_hash = settings.superadmin_password_hash.get_secret_value()
    if admin is None or (
        admin.get('email') != settings.superadmin_email
        or admin.get('password_hash') != configured_hash
    ):
        logger.error('ADMIN_CONFIG_MISMATCH: MongoDB admin differs from this deployment configuration; check shared database and old deployments')
        raise HTTPException(503, 'Cấu hình Admin trên server chưa đồng bộ. Kiểm tra Vercel Runtime Logs: ADMIN_CONFIG_MISMATCH.')
    encoded = admin['password_hash']
    # Also perform an expensive verification for unknown emails; keep the event loop responsive.
    valid = await asyncio.to_thread(verify_password, data.password.get_secret_value(), encoded)
    if not valid or data.email != admin['email']:
        logger.warning(
            'ADMIN_LOGIN_REJECTED: email_matches_config=%s password_matches_config=%s',
            data.email == settings.superadmin_email, valid,
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
