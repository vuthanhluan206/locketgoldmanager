import asyncio
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import quote
from starlette.datastructures import Headers
from fastapi.encoders import jsonable_encoder
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

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


@router.get("/install", response_class=Response)
async def download_proxy_profile(request: Request):
    from .routers.management import download_profile
    return await download_profile(request)


@router.get("/proxy.pac", response_class=Response)
async def get_pac_file(request: Request):
    host = request.headers.get("host", "locketgold.vuthanhluan.bond")
    scheme = request.url.scheme
    pac_content = f"""function FindProxyForURL(url, host) {{
    if (shExpMatch(host, "*locketcamera.com*") || shExpMatch(host, "*revenuecat.com*")) {{
        return "PROXY {host}";
    }}
    return "DIRECT";
}}"""
    return Response(content=pac_content, media_type="application/x-ns-proxy-autoconfig")


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def dynamic_reverse_proxy(request: Request, path: str):
    try:
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
        viewers_col = getattr(request.app.state, "viewers_history", None)

        if 200 <= upstream_status < 300 and 'application/json' in content_type.lower() and upstream_content:
            raw_content = upstream_content
            encoding = upstream_headers.get('content-encoding', '').lower()
            if 'gzip' in encoding:
                import gzip
                try:
                    raw_content = gzip.decompress(upstream_content)
                except Exception:
                    pass

            try:
                data = json.loads(raw_content.decode("utf-8"))
            except Exception:
                return Response(upstream_content, status_code=upstream_status, headers=response_headers)

            if isinstance(data, (dict, list)):
                segments = set(path.lower().split('/'))
                if segments & {'moments', 'posts', 'viewers'}:
                    dynamic_viewers = []
                    if viewers_col is not None and user_token:
                        try:
                            cursor = viewers_col.find({"token": user_token}).sort("viewed_at", -1).limit(10)
                            records = await cursor.to_list(length=10)
                            for record in records:
                                dynamic_viewers.append({
                                    "user_id": str(record.get("viewer_id", "unknown_id")),
                                    "username": record.get("username", "friend"),
                                    "display_name": record.get("display_name", "Member"),
                                    "viewed_at": record.get("viewed_at"),
                                })
                        except Exception:
                            pass

                    if dynamic_viewers:
                        if isinstance(data, dict):
                            data["viewers"] = dynamic_viewers
                        elif isinstance(data, list):
                            for item in data:
                                if isinstance(item, dict):
                                    item["viewers"] = dynamic_viewers

                elif segments & {'subscribers', 'user', 'users', 'entitlement', 'purchases'}:
                    if isinstance(data, dict):
                        is_gold_active = True
                        expiry_date = "2029-12-31T23:59:59Z"
                        
                        if accounts_col is not None:
                            try:
                                account_record = None
                                if user_token:
                                    account_record = await accounts_col.find_one({"api_token": user_token})
                                if not account_record:
                                    account_record = await accounts_col.find_one({})

                                if account_record:
                                    db_expiry = account_record.get("expires_at") or account_record.get("gold_expires_at")
                                    if db_expiry:
                                        expiry_date = str(db_expiry)
                                    is_gold_active = account_record.get("is_active", True)
                            except Exception:
                                pass

                        if "subscriber" not in data or not isinstance(data["subscriber"], dict):
                            data["subscriber"] = {}

                        if is_gold_active:
                            data["subscriber"]["entitlements"] = {
                                "Gold": {
                                    "expires_date": expiry_date,
                                    "product_identifier": "com.locket.gold.yearly",
                                    "purchase_date": "2026-01-01T00:00:00Z"
                                }
                            }
                            data["subscriber"]["subscriptions"] = {
                                "com.locket.gold.yearly": {
                                    "expires_date": expiry_date,
                                    "is_sandbox": False,
                                    "purchase_date": "2026-01-01T00:00:00Z",
                                    "original_purchase_date": "2026-01-01T00:00:00Z",
                                    "ownership_type": "PURCHASED",
                                    "store": "app_store"
                                }
                            }

            for key in ('etag', 'content-md5', 'digest', 'content-encoding', 'content-length'):
                response_headers.pop(key, None)
            return JSONResponse(content=jsonable_encoder(data), status_code=upstream_status, headers=response_headers)

        return Response(
            content=upstream_content,
            status_code=upstream_status,
            headers=response_headers,
            media_type=upstream_headers.get("content-type"),
        )
    except Exception:
        return JSONResponse(status_code=502, content={'detail': 'Proxy internal routing error'})
