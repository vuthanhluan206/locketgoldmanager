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
from fastapi import APIRouter, HTTPException, Request, Response, Depends, status
from fastapi.responses import JSONResponse, FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

from .config import get_settings
from .models import subscriber_response
from .routers.management import download_profile
from .security import token_digest

router = APIRouter(prefix="/proxy", tags=["Locket Proxy"])

HOP_HEADERS = {'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
               'te', 'trailer', 'transfer-encoding', 'upgrade'}
MAX_RESPONSE = 50 * 1024 * 1024

# ================= CƠ CHẾ BẢO MẬT ADMIN (BIẾN MÔI TRƯỜNG) =================
security = HTTPBasic()

def verify_admin(credentials: HTTPBasicCredentials = Depends(security)):
    # Đặt biến môi trường ADMIN_PASSWORD trên Vercel, mặc định là 'admin123' nếu quên cấu hình
    admin_password = os.getenv("ADMIN_PASSWORD", "admin123")
    
    is_user_ok = secrets.compare_digest(credentials.username, "admin")
    is_pass_ok = secrets.compare_digest(credentials.password, admin_password)
    
    if not (is_user_ok and is_pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tài khoản hoặc mật khẩu Quản trị viên không chính xác",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

class AccountRequest(BaseModel):
    locket_id: str
    note: str = ""

@router.get("/admin", response_class=FileResponse)
async def get_admin_page(admin_user: str = Depends(verify_admin)):
    """Trả về file web/index.html. Trình duyệt sẽ yêu cầu nhập user/pass trước khi hiển thị"""
    return FileResponse("web/index.html")

@router.post("/admin/add")
async def api_add_account(req: Request, data: AccountRequest, admin_user: str = Depends(verify_admin)):
    """API thêm ID vào MongoDB, được bảo vệ bởi Basic Auth"""
    accounts_col = getattr(req.app.state, "accounts", None)
    if accounts_col is None:
        raise HTTPException(503, "Không thể kết nối đến cơ sở dữ liệu")
    
    await accounts_col.update_one(
        {"locket_id": data.locket_id},
        {"$set": {
            "locket_id": data.locket_id, 
            "note": data.note, 
            "status": "active",
            "updated_at": datetime.now(timezone.utc)
        }},
        upsert=True
    )
    return {"status": "success", "message": f"Đã cấp quyền Gold cho ID: {data.locket_id}"}
# ==========================================================================

async def process_image_with_ai(image_bytes: bytes, prompt: str) -> bytes:
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
        return None

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
    """Định vị ID chính xác bằng cách quét ưu tiên Header của RevenueCat"""
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

@router.get("/install", response_class=Response)
async def download_proxy_profile(request: Request):
    return await download_profile(request)

@router.get("/proxy.pac", response_class=Response)
async def get_proxy_pac(request: Request):
    host = request.headers.get("host", "locketgold.vuthanhluan.bond")
    pac_content = f"""
function FindProxyForURL(url, host) {{
    if (shExpMatch(host, "*locketcamera.com*") || shExpMatch(host, "*revenuecat.com*")) {{
        return "PROXY {host}";
    }}
    return "DIRECT";
}}
"""
    return Response(content=pac_content.strip(), media_type="application/x-ns-proxy-autoconfig")

@router.get("/{filename}", include_in_schema=False)
async def handle_static_files(filename: str):
    if any(filename.endswith(ext) for ext in [".png", ".ico", ".txt", ".xml", ".json"]):
        return Response(status_code=204)
    raise HTTPException(status_code=404, detail="Not Found")

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
        if key in {'host', 'cookie', 'forwarded', 'accept-encoding'} or key.startswith(('x-forwarded-', 'cf-')):
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

    if is_upload:
        try:
            if body:
                ai_prompt = "strictly change hair color to vibrant fiery red hair, highly detailed, realistic hair texture"
                modified_bytes = await process_image_with_ai(body, ai_prompt)
                if modified_bytes:
                    body = modified_bytes
        except Exception as e:
            print(f"[AI Proxy Error]: {e}")

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
            
            if segments & {'subscribers', 'user', 'users'}:
                if isinstance(data, dict):
                    candidate_id = _extract_locket_id(path, data, dict(request.headers))
                    
                    # ================= SỬA LỖI CẤP GOLD HÀNG LOẠT =================
                    # Chỉ kiểm tra và ghi đè JSON nếu lấy được ID và ID đó TỒN TẠI trong MongoDB
                    if accounts_col is not None and candidate_id:
                        account_record = await accounts_col.find_one({"locket_id": candidate_id, "status": "active"}, {"_id": 0})
                        
                        if account_record:
                            now = datetime.now(timezone.utc)
                            sub_payload = subscriber_response(candidate_id, account_record, now)
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
                    # Nếu account_record là None, code sẽ bỏ qua việc thêm entitlements 
                    # và trả về JSON gốc (tài khoản không có Gold).

            for key in ('etag', 'content-md5', 'digest', 'content-encoding'):
                response_headers.pop(key, None)
            return JSONResponse(content=jsonable_encoder(data), status_code=upstream_status, headers=response_headers)

    return Response(
        content=upstream_content,
        status_code=upstream_status,
        headers=response_headers,
        media_type=upstream_headers.get("content-type"),
    )