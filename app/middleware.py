"""Bounded requests and throttling with explicitly trusted proxy addresses."""
import asyncio
from ipaddress import ip_address, ip_network
import secrets
import time

from fastapi.responses import JSONResponse
from starlette.datastructures import Headers, MutableHeaders
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.routing import Match

from .config import get_settings
from .locket_modifier import dynamic_reverse_proxy, router as proxy_router

MAX_BODY = 8192
MAX_PROXY_BODY = 50 * 1024 * 1024


def client_ip(scope) -> str:
    peer = scope['client'][0] if scope.get('client') else 'unknown'
    try:
        address = ip_address(peer)
        if any(address in ip_network(cidr) for cidr in get_settings().trusted_proxy_cidrs):
            forwarded = Headers(scope=scope).get('cf-connecting-ip', '')
            return str(ip_address(forwarded))
        return str(address)
    except ValueError:
        return peer


def security_headers(nonce: str, https: bool) -> dict[str, str]:
    headers = {
        'Cache-Control': 'no-store',
        'Referrer-Policy': 'no-referrer',
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'DENY',
        'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
        'Content-Security-Policy': (
            f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; "
            "img-src 'self' data:; connect-src 'self' https://challenges.cloudflare.com; frame-src https://challenges.cloudflare.com; "
            "form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
        ),
    }
    if https:
        headers['Strict-Transport-Security'] = 'max-age=31536000'
    return headers


class RateLimiter:
    def __init__(self, capacity: int = 10000):
        self.buckets = {}
        self.capacity = capacity
        self.next_cleanup = 0.0

    def allow(self, key: tuple, limit: int) -> bool:
        now = time.monotonic()
        if now >= self.next_cleanup:
            self.buckets = {k: v for k, v in self.buckets.items() if v[0] > now}
            self.next_cleanup = now + 60
        bucket = self.buckets.get(key)
        if bucket is None or bucket[0] <= now:
            if bucket is None and len(self.buckets) >= self.capacity:
                return False
            self.buckets[key] = [now + 60, 1]
            return True
        if bucket[1] >= limit:
            return False
        bucket[1] += 1
        return True


class SecurityMiddleware:
    def __init__(self, app):
        self.settings = get_settings()
        self.app = TrustedHostMiddleware(
            app, allowed_hosts=self.settings.allowed_hosts, www_redirect=False,
        )
        self.limiter = RateLimiter()

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)

        # Use the actual matched route so local admin/API routes keep their limits.
        is_proxy = False
        for route in scope['app'].router.routes:
            if route.matches(scope)[0] == Match.FULL:
                is_proxy = (getattr(route, 'endpoint', None) is dynamic_reverse_proxy
                            or getattr(route, 'original_router', None) is proxy_router)
                break
        body_limit = MAX_PROXY_BODY if is_proxy else MAX_BODY

        nonce = secrets.token_urlsafe(24)
        scope.setdefault('state', {})['csp_nonce'] = nonce
        headers = Headers(scope=scope)
        https = scope['scheme'] == 'https' or headers.get('x-forwarded-proto') == 'https'

        async def secured_send(message):
            if message['type'] == 'http.response.start':
                MutableHeaders(scope=message).update(security_headers(nonce, https))
            await send(message)

        async def reject(status, detail, retry=False):
            response = JSONResponse(
                {'detail': detail}, status_code=status,
                headers={'Retry-After': '60'} if retry else None,
            )
            await response(scope, receive, secured_send)

        if self.settings.require_https and not https:
            return await reject(400, 'HTTPS is required')
        ip = client_ip(scope)
        bucket, request_limit = ('proxy', 600) if is_proxy else ('all', 120)
        if not self.limiter.allow((ip, bucket), request_limit):
            return await reject(429, 'Too many requests', True)
        if scope['path'].rstrip('/') == '/api/admin/login':
            if (not self.limiter.allow((ip, 'login'), 10)
                    or not self.limiter.allow(('global', 'login'), 30)):
                return await reject(429, 'Too many login attempts', True)
        length = headers.get('content-length')
        if length is not None:
            if not length.isascii() or not length.isdecimal():
                return await reject(400, 'Invalid Content-Length')
            if len(length) > 10 or int(length) > body_limit:
                return await reject(413, 'Request body exceeds limit')

        body = bytearray()
        try:
            async with asyncio.timeout(60 if is_proxy else 5):
                while True:
                    message = await receive()
                    if message['type'] == 'http.disconnect':
                        return
                    body.extend(message.get('body', b''))
                    if len(body) > body_limit:
                        return await reject(413, 'Request body exceeds limit')
                    if not message.get('more_body', False):
                        break
        except TimeoutError:
            return await reject(408, 'Request body timed out')

        delivered = False

        async def buffered_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
            return await receive()

        await self.app(scope, buffered_receive, secured_send)
