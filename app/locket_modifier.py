import asyncio
import json
import secrets
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import quote
from starlette.datastructures import Headers
from fastapi.encoders import jsonable_encoder
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from .config import get_settings
from .models import subscriber_response
from .routers.management import download_profile
from .security import token_digest

router = APIRouter(prefix="/proxy", tags=["Locket Proxy"])

UPSTREAM_TARGET = "https://api.locketcamera.com"


HOP_HEADERS = {'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
               'te', 'trailer', 'transfer-encoding', 'upgrade'}
MAX_RESPONSE = 50 * 1024 * 1024


def _clean_headers(headers):
    named = {key.strip().lower() for key in headers.get('connection', '').split(',')}
    return {key.lower(): value for key, value in headers.items()
            if key.lower() not in HOP_HEADERS | named | {'content-length'}}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _forward_upstream(url: str, body: bytes | None, headers: dict[str, str], method: str, timeout: float):
    req = urllib.request.Request(url, data=body if body else None, headers=headers, method=method)
    opener = urllib.request.build_opener(NoRedirect())
    try:
        response = opener.open(req, timeout=timeout)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        content = response.read(MAX_RESPONSE + 1)
        if len(content) > MAX_RESPONSE:
            raise ValueError('Upstream response exceeds limit')
        return response.code, dict(response.headers.items()), content


def _extract_locket_id(path: str, data: dict) -> str:
    sub = data.get('subscriber')
    if isinstance(sub, dict) and isinstance(sub.get('original_app_user_id'), str) and sub['original_app_user_id']:
        return sub['original_app_user_id']
    parts = [p for p in path.split("/") if p]
    if "subscribers" in parts:
        idx = parts.index("subscribers")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    if isinstance(data, dict):
        sub = data.get("subscriber")
        if isinstance(sub, dict) and sub.get("original_app_user_id"):
            return str(sub["original_app_user_id"])
        for key in ("locket_id", "uid", "user_id", "id"):
            if isinstance(data.get(key), str) and data[key]:
                return data[key]
        user_obj = data.get("user") or data.get("data")
        if isinstance(user_obj, dict):
            for key in ("uid", "user_id", "id", "locket_id"):
                if isinstance(user_obj.get(key), str) and user_obj[key]:
                    return user_obj[key]
    return ''


@router.get("/install", response_class=Response)
async def download_proxy_profile(request: Request):
    return await download_profile(request)


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def dynamic_reverse_proxy(request: Request, path: str):
    url = UPSTREAM_TARGET + "/" + quote(path, safe="/:@!$&'()*+,;=-._~")
    query_params = str(request.url.query)
    if query_params:
        url += f"?{query_params}"

    headers = _clean_headers(dict(request.headers))
    for key in list(headers):
        if key in {'host', 'cookie', 'forwarded', 'accept-encoding'} or key.startswith(('x-forwarded-', 'cf-')):
            del headers[key]
    headers['Host'] = 'api.locketcamera.com'
    headers['Accept-Encoding'] = 'identity'

    method = request.method
    content_type_header = headers.get("content-type", "")
    auth_header = headers.get("authorization", "")
    scheme, _, token = auth_header.partition(' ')
    user_token = token.strip() if scheme.lower() == 'bearer' else ''

    is_upload = method in ["POST", "PUT", "PATCH"] and (
        "multipart/form-data" in content_type_header
        or "octet-stream" in content_type_header
        or "video/" in content_type_header
        or "image/" in content_type_header
    )
    
    try:
        body = await request.body()
    except Exception:
        body = b''

    timeout_limit = 60.0 if is_upload else 30.0

    try:
        upstream_status, upstream_headers, upstream_content = await asyncio.to_thread(
            _forward_upstream, url, body, headers, method, timeout_limit
        )
    except Exception:
        return JSONResponse(status_code=502, content={'detail': 'Upstream unavailable'})

    upstream_headers = Headers({key.lower(): value for key, value in upstream_headers.items()})
    response_headers = _clean_headers(upstream_headers)
    response_headers.pop('set-cookie', None)
    
    if 300 <= upstream_status < 400:
        return JSONResponse({'detail': 'Upstream redirect blocked'}, status_code=502)

    if is_upload:
        return Response(
            content=upstream_content,
            status_code=upstream_status,
            headers=response_headers,
            media_type=upstream_headers.get("content-type"),
        )

    content_type = upstream_headers.get("content-type", "")
    accounts_col = getattr(request.app.state, "accounts", None)

    try:
        if 200 <= upstream_status < 300 and 'application/json' in content_type.lower() and upstream_content:
            raw_content = upstream_content
            encoding = upstream_headers.get('content-encoding', '').lower()
            if 'gzip' in encoding:
                import gzip
                try:
                    raw_content = gzip.decompress(upstream_content)
                except Exception:
                    pass

            data = json.loads(raw_content.decode("utf-8"))

            if isinstance(data, dict):
                segments = set(path.lower().split('/'))
                if segments & {'subscribers', 'user', 'users', 'entitlement', 'purchases'}:
                    candidate_id = _extract_locket_id(path, data)
                    account_record = None
                    if accounts_col is not None and candidate_id:
                        try:
                            account_record = await accounts_col.find_one(
                                {"locket_id": candidate_id}, {"_id": 0}
                            )
                        except Exception:
                            pass

                    if not account_record:
                        account_record = {
                            "locket_id": candidate_id or "locket_user",
                            "expires_date": datetime(2030, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
                        }

                    now = datetime.now(timezone.utc)
                    sub_payload = subscriber_response(candidate_id or "locket_user", account_record, now)
                    subscriber = data.get('subscriber')
                    if subscriber is None:
                        subscriber = data['subscriber'] = sub_payload['subscriber']
                    if isinstance(subscriber, dict):
                        for field, key in [('entitlements', 'Gold'), ('subscriptions', 'com.locket.gold.yearly')]:
                            values = subscriber.get(field)
                            if not isinstance(values, dict):
                                values = {}
                            values.pop(key, None)
                            values.update(sub_payload['subscriber'][field])
                            subscriber[field] = values

            for key in ('etag', 'content-md5', 'digest', 'content-encoding', 'content-length'):
                response_headers.pop(key, None)
            return JSONResponse(content=jsonable_encoder(data), status_code=upstream_status, headers=response_headers)
    except Exception:
        pass

    return Response(
        content=upstream_content,
        status_code=upstream_status,
        headers=response_headers,
        media_type=upstream_headers.get("content-type"),
    )
