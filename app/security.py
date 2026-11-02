import secrets
from typing import Annotated
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from .config import get_settings

bearer = HTTPBearer(auto_error=False)


def valid_token(value: str) -> bool:
    return secrets.compare_digest(value.encode('utf-8'), get_settings().admin_token.encode('utf-8'))


def require_admin(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
    if credentials is None or not valid_token(credentials.credentials):
        raise HTTPException(401, 'Invalid admin token', headers={'WWW-Authenticate': 'Bearer'})
