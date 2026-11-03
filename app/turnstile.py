import asyncio
import json
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request as URLRequest, urlopen

from fastapi import HTTPException

from .config import get_settings


def siteverify(secret: str, token: str) -> dict:
    body = urlencode({'secret': secret, 'response': token}).encode('ascii')
    request = URLRequest(
        'https://challenges.cloudflare.com/turnstile/v0/siteverify', data=body,
        headers={'Content-Type': 'application/x-www-form-urlencoded'}, method='POST',
    )
    with urlopen(request, timeout=5) as response:
        return json.loads(response.read(65536))


async def verify_turnstile(token: str):
    settings = get_settings()
    secret = settings.turnstile_secret_key.get_secret_value()
    hostnames = [host.strip().lower() for host in settings.turnstile_hostname.split(',') if host.strip()]
    if not settings.turnstile_site_key and not secret:
        return
    if not settings.turnstile_site_key or not secret or not hostnames:
        raise HTTPException(503, 'Cloudflare Turnstile chưa được cấu hình đầy đủ.')
    if not token:
        raise HTTPException(403, 'Vui lòng hoàn tất xác minh Cloudflare.')
    try:
        result = await asyncio.to_thread(siteverify, secret, token)
    except (URLError, OSError, ValueError):
        raise HTTPException(503, 'Không thể xác minh Cloudflare. Vui lòng thử lại.') from None
    if (not isinstance(result, dict) or result.get('success') is not True
            or result.get('hostname') not in hostnames
            or result.get('action') != 'admin-login'):
        raise HTTPException(403, 'Xác minh Cloudflare không hợp lệ hoặc đã hết hạn.')
