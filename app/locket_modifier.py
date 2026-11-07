import asyncio
import json
import secrets
import urllib.error
import urllib.request
import httpx
import os
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


async def process_image_with_ai(image_bytes: bytes, prompt: str) -> bytes:
    """
    Gửi ảnh lên Hugging Face Inference API để xử lý filter chỉnh màu / instruct-pix2pix.
    Giới hạn thời gian chờ dưới 9.5 giây để khớp với giới hạn Serverless của Vercel.
    """
    api_token = os.getenv("HUGGINGFACE_API_TOKEN", "")
    if not api_token:
        raise ValueError("Thiếu cấu hình HUGGINGFACE_API_TOKEN")

    hf_endpoint = "https://api-inference.huggingface.co/models/timbrooks/instruct-pix2pix"
    
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/octet-stream",
        "X-Wait-For-Model": "true"
    }

    async with httpx.AsyncClient(timeout=9.5) as client:
        resp = await client.post(hf_endpoint, headers=headers, content=image_bytes)
        
        if resp.status_code == 200:
            return resp.content
        elif resp.status_code == 503:
            raise ValueError("Hugging Face Model đang khởi động (Cold Boot), vui lòng thử lại sau vài giây")
        else:
            raise ValueError(f"Hugging Face API lỗi: {resp.status_code} - {resp.text}")


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
    
    if user_token:
        configured = get_settings().subscriber_api_token
        if configured is not None and secrets.compare_digest(
            user_token.encode('utf-8'), configured.get_secret_value().encode('ascii'),
        ):
            raise HTTPException(401, 'Use an upstream access token')
        sessions = getattr(request.app.state, 'sessions', None)
        if sessions is not None and len(user_token) == 64 and user_token.isascii():
            if await sessions.find_one({'_id': token_digest(user_token)}):
                raise HTTPException(401, 'Use an upstream access token')

    is_upload = method in ["POST", "PUT", "PATCH"] and (
        "multipart/form-data" in content_type_header
        or "octet-stream" in content_type_header
        or "video/" in content_type_header
        or "image/" in content_type_header
    )
    body = await request.body()
    timeout_limit = 60.0 if is_upload else 30.0

    # ================= LOGIC ĐÁNH CHẶN AI FILTER QUA HUGGING FACE =================
    if "filter" in path.lower() and "multipart/form-data" in content_type_header.lower():
        try:
            form = await request.form()
            image_bytes = None
            for key, value in form.multi_items():
                if hasattr(value, "file"):
                    image_bytes = await value.read()
                    break
            
            if image_bytes:
                ai_prompt = "enhance lighting, warm cinematic gold filter, high quality"
                modified_bytes = await process_image_with_ai(image_bytes, ai_prompt)
                
                if modified_bytes:
                    return Response(
                        content=modified_bytes,
                        status_code=200,
                        headers={"Content-Type": "image/jpeg"}
                    )
        except Exception as e:
            print(f"[AI Filter Error] {e}")
            # Nếu HF lỗi hoặc timeout, tự động rơi xuống luồng forward ảnh gốc bên dưới để app không văng
    # ==============================================================================

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
        return Response(
            content=upstream_content,
            status_code=upstream_status,
            headers=response_headers,
            media_type=upstream_headers.get("content-type"),
        )

    content_type = upstream_headers.get("content-type", "")
    accounts_col = getattr(request.app.state, "accounts", None)
    viewers_col = getattr(request.app.state, "viewers_history", None)

    if (200 <= upstream_status < 300 and user_token and
            'application/json' in content_type.lower() and upstream_content and
            upstream_headers.get('content-encoding', 'identity').lower() == 'identity'):
        try:
            data = json.loads(upstream_content.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return Response(upstream_content, status_code=upstream_status, headers=response_headers)
        if isinstance(data, (dict, list)):
            segments = set(path.split('/'))
            if segments & {'moments', 'posts', 'viewers'}:
                dynamic_viewers = []
                if viewers_col is None:
                    raise HTTPException(503, 'Database unavailable')
                cursor = viewers_col.find({"token": user_token}).sort("viewed_at", -1).limit(10)
                records = await cursor.to_list(length=10)
                for record in records:
                    dynamic_viewers.append({
                        "user_id": str(record.get("viewer_id", "unknown_id")),
                        "username": record.get("username", "friend"),
                        "display_name": record.get("display_name", "Member"),
                        "viewed_at": record.get("viewed_at"),
                    })

                if dynamic_viewers:
                    if isinstance(data, dict):
                        data["viewers"] = dynamic_viewers
                    elif isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict):
                                item["viewers"] = dynamic_viewers

            elif segments & {'subscribers', 'user', 'users'}:
                if isinstance(data, dict):
                    candidate_id = _extract_locket_id(path, data)
                    account_record = None
                    if accounts_col is None:
                        raise HTTPException(503, 'Database unavailable')
                    if candidate_id:
                        account_record = await accounts_col.find_one(
                            {"locket_id": candidate_id}, {"_id": 0}
                        )

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

            for key in ('etag', 'content-md5', 'digest', 'content-encoding'):
                response_headers.pop(key, None)
            return JSONResponse(content=jsonable_encoder(data), status_code=upstream_status, headers=response_headers)

    return Response(
        content=upstream_content,
        status_code=upstream_status,
        headers=response_headers,
        media_type=upstream_headers.get("content-type"),
    )