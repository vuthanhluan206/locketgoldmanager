import asyncio
import json
import urllib.error
import urllib.request
from urllib.parse import quote
from starlette.datastructures import Headers
from fastapi.encoders import jsonable_encoder
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from datetime import datetime, timezone

from .models import subscriber_response

router = APIRouter(tags=["Locket Proxy"])

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

def _extract_locket_id(path: str, data: dict, request_headers: dict) -> str:
    headers_lower = {k.lower(): v for k, v in request_headers.items()}
    for hk in ["x-app-user-id", "x-revenuecat-app-user-id", "x-locket-user-id"]:
        if hk in headers_lower and headers_lower[hk]:
            return headers_lower[hk]
    sub = data.get('subscriber')
    if isinstance(sub, dict) and isinstance(sub.get('original_app_user_id'), str) and sub['original_app_user_id']:
        return sub['original_app_user_id']
    parts = [p for p in path.split("/") if p]
    if "subscribers" in parts:
        idx = parts.index("subscribers")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return ''

@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def dynamic_reverse_proxy(request: Request, path: str):
    original_host = request.headers.get("host", "")
    if "revenuecat.com" in original_host:
        upstream_host = "api.revenuecat.com"
    else:
        upstream_host = "api.locketcamera.com"
        
    url = f"https://{upstream_host}/" + quote(path, safe="/:@!$&'()*+,;=-._~")
    
    query_params = str(request.url.query)
    if query_params:
        url += f"?{query_params}"

    headers = _clean_headers(dict(request.headers))
    
    for key in list(headers):
        if key in {'host', 'cookie', 'forwarded', 'accept-encoding', 'x-revenuecat-etag'} or key.startswith(('x-forwarded-', 'cf-')):
            del headers[key]
            
    headers['Host'] = upstream_host
    headers['Accept-Encoding'] = 'identity'

    method = request.method
    content_type_header = headers.get("content-type", "")
    is_upload = method in ["POST", "PUT", "PATCH"] and (
        "multipart/form-data" in content_type_header.lower()
        or "octet-stream" in content_type_header.lower()
        or "image/" in content_type_header.lower()
    )
    
    body = await request.body()
    timeout_limit = 60.0 if is_upload else 30.0

    try:
        upstream_status, upstream_headers, upstream_content = await asyncio.to_thread(
            _forward_upstream, url, body, headers, method, timeout_limit
        )
    except (OSError, ValueError):
        return JSONResponse(status_code=502, content={'detail': 'Upstream unavailable'})

    upstream_headers = Headers({key.lower(): value for key, value in upstream_headers.items()})
    response_headers = _clean_headers(upstream_headers)
    response_headers.pop('set-cookie', None)
    
    if 300 <= upstream_status < 400:
        return JSONResponse({'detail': 'Upstream redirect blocked'}, status_code=502)

    if is_upload:
        return Response(content=upstream_content, status_code=upstream_status, headers=response_headers, media_type=upstream_headers.get("content-type"))

    content_type = upstream_headers.get("content-type", "")
    accounts_col = getattr(request.app.state, "accounts", None)

    if (200 <= upstream_status < 300 and 
            'application/json' in content_type.lower() and upstream_content and
            upstream_headers.get('content-encoding', 'identity').lower() == 'identity'):
        try:
            data = json.loads(upstream_content.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return Response(upstream_content, status_code=upstream_status, headers=response_headers)
        
        if isinstance(data, (dict, list)):
            segments = set(path.split('/'))
            
            if segments & {'subscribers', 'user', 'users'} and isinstance(data, dict):
                candidate_id = _extract_locket_id(path, data, dict(request.headers))
                
                if candidate_id:
                    account_record = None
                    if accounts_col is not None:
                        account_record = await accounts_col.find_one({"locket_id": candidate_id, "status": "active"}, {"_id": 0})
                        if not account_record:
                            account_record = await accounts_col.find_one({"locket_id": candidate_id}, {"_id": 0})
                    
                    if account_record:
                        now = datetime.now(timezone.utc)
                        sub_payload = subscriber_response(candidate_id, account_record, now)
                        subscriber = data.get('subscriber')
                        
                        if subscriber is None:
                            subscriber = data['subscriber'] = sub_payload['subscriber']
                            
                        if isinstance(subscriber, dict):
                            for field, key in [
                                ('entitlements', 'Gold'), 
                                ('entitlements', 'pro'), 
                                ('entitlements', 'gold'), 
                                ('subscriptions', 'com.locket.gold.yearly')
                            ]:
                                values = subscriber.get(field)
                                if not isinstance(values, dict):
                                    values = {}
                                values.pop(key, None)
                                if key in sub_payload['subscriber'][field]:
                                    values[key] = sub_payload['subscriber'][field][key]
                                subscriber[field] = values

            for key in ('etag', 'content-md5', 'digest', 'content-encoding'):
                response_headers.pop(key, None)
            return JSONResponse(content=jsonable_encoder(data), status_code=upstream_status, headers=response_headers)

    return Response(
        content=upstream_content,
        status_code=upstream_status,
        headers=response_headers,
        media_type=upstream_headers.get("content-type"),
    )