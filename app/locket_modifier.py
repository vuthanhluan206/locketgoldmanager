import asyncio
import json
import secrets
import urllib.error
import urllib.request
import httpx
import os
import time
from datetime import datetime, timezone
from urllib.parse import quote
from starlette.datastructures import Headers
from fastapi.encoders import jsonable_encoder
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

from .config import get_settings
from .models import subscriber_response
from .routers.management import download_profile
from .security import token_digest

# Đọc đường dẫn Admin từ Vercel, mặc định là /admin
ADMIN_PATH = os.getenv("ADMIN_PATH", "/admin")

# ================= ĐÃ GỠ BỎ PREFIX="/proxy" ĐỂ ADMIN NẰM Ở GỐC =================
router = APIRouter(tags=["Locket Proxy"])

HOP_HEADERS = {'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
               'te', 'trailer', 'transfer-encoding', 'upgrade'}
MAX_RESPONSE = 50 * 1024 * 1024

FAILED_LOGIN_ATTEMPTS = {}
MAX_FAILURES = 5
LOCKOUT_TIME = 300 

class AccountRequest(BaseModel):
    admin_user: str      
    admin_pass: str      
    locket_id: str
    note: str = ""

# ĐƯỜNG DẪN ADMIN HOẠT ĐỘNG Ở GỐC (VD: domain.com/admin)
@router.get(ADMIN_PATH, response_class=FileResponse)
async def get_admin_page():
    # Khắc phục triệt để lỗi 500 vỡ giao diện trên Vercel bằng đường dẫn tuyệt đối
    current_dir = os.path.dirname(os.path.realpath(__file__))
    file_path = os.path.join(current_dir, "..", "web", "index.html")
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Không tìm thấy file giao diện web/index.html")
    return FileResponse(file_path)

@router.post(f"{ADMIN_PATH}/add")
async def api_add_account(req: Request, data: AccountRequest):
    client_ip = req.headers.get("cf-connecting-ip") or req.headers.get("x-forwarded-for") or req.client.host
    now = time.time()
    
    if client_ip in FAILED_LOGIN_ATTEMPTS:
        attempts, last_fail = FAILED_LOGIN_ATTEMPTS[client_ip]
        if attempts >= MAX_FAILURES:
            if now - last_fail < LOCKOUT_TIME:
                raise HTTPException(status_code=429, detail="IP đã bị khóa 5 phút do nhập sai mật khẩu quá nhiều lần.")
            else:
                del FAILED_LOGIN_ATTEMPTS[client_ip]

    accounts_col = getattr(req.app.state, "accounts", None)
    if accounts_col is None:
        raise HTTPException(503, "Lỗi kết nối Cơ sở dữ liệu")
    
    admins_col = accounts_col.database["admins"]
    
    admin_user_db = await admins_col.find_one({
        "username": data.admin_user, 
        "password": data.admin_pass
    })
    
    if not admin_user_db:
        if client_ip in FAILED_LOGIN_ATTEMPTS:
            FAILED_LOGIN_ATTEMPTS[client_ip] = (FAILED_LOGIN_ATTEMPTS[client_ip][0] + 1, now)
        else:
            FAILED_LOGIN_ATTEMPTS[client_ip] = (1, now)
        raise HTTPException(status_code=401, detail="Sai tài khoản hoặc mật khẩu Quản trị!")

    if client_ip in FAILED_LOGIN_ATTEMPTS:
        del FAILED_LOGIN_ATTEMPTS[client_ip]
        
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
    return {"status": "success", "message": f"Đã cấp Locket Gold thành công cho ID: {data.locket_id}"}
# ====================================================================================

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

# ================= CÁC ĐƯỜNG DẪN PROXY LOCKET ĐƯỢC GẮN CHỮ /proxy THỦ CÔNG =================
@router.get("/proxy/install", response_class=Response)
async def download_proxy_profile(request: Request):
    return await download_profile(request)

@router.get("/proxy/proxy.pac", response_class=Response)
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

@router.get("/proxy/{filename}", include_in_schema=False)
async def handle_static_files(filename: str):
    if any(filename.endswith(ext) for ext in [".png", ".ico", ".txt", ".xml", ".json"]):
        return Response(status_code=204)
    raise HTTPException(status_code=404, detail="Not Found")

@router.api_route("/proxy/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
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

            for key in ('etag', 'content-md5', 'digest', 'content-encoding'):
                response_headers.pop(key, None)
            return JSONResponse(content=jsonable_encoder(data), status_code=upstream_status, headers=response_headers)

    return Response(
        content=upstream_content,
        status_code=upstream_status,
        headers=response_headers,
        media_type=upstream_headers.get("content-type"),
    )