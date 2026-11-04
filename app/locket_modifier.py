import urllib.request
import urllib.error
import json
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from app.database import db

app = FastAPI(title="Locket Dynamic Cloud Modifier Proxy", version="2.1.0")

UPSTREAM_TARGET = "https://api.locketcamera.com"

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def dynamic_reverse_proxy(request: Request, path: str):
    url = f"{UPSTREAM_TARGET}/{path}"
    
    # Lấy query parameters nếu có
    query_params = str(request.url.query)
    if query_params:
        url += f"?{query_params}"

    # Lấy headers từ client
    headers = dict(request.headers)
    headers.pop("host", None)
    headers["Host"] = "api.locketcamera.com"

    # Lấy body của request (nếu là POST/PUT)
    body = await request.body()
    method = request.method

    # Trích xuất Token xác thực từ Header
    auth_header = headers.get("authorization", "")
    user_token = auth_header.replace("Bearer ", "").strip()

    try:
        # Sử dụng urllib chuẩn của Python
        req = urllib.request.Request(url, data=body if body else None, headers=headers, method=method)
        
        with urllib.request.urlopen(req, timeout=30.0) as upstream_response:
            upstream_status = upstream_response.status
            upstream_headers = dict(upstream_response.headers.items())
            upstream_content = upstream_response.read()
            
    except urllib.error.HTTPError as e:
        upstream_status = e.code
        upstream_headers = dict(e.headers.items())
        upstream_content = e.read()
    except Exception as exc:
        return JSONResponse(status_code=502, content={"error": f"Bad Gateway to Upstream: {str(exc)}"})

    content_type = upstream_headers.get("content-type", "")
    
    if "application/json" in content_type and upstream_content:
        try:
            data = json.loads(upstream_content.decode("utf-8"))
            
            # --- 1. XỬ LÝ DANH SÁCH NGƯỜI XEM ĐỘNG (Moments/Posts) ---
            if "moments" in path or "posts" in path:
                if isinstance(data, dict):
                    dynamic_viewers = []
                    if db is not None and user_token:
                        cursor = db.viewers_history.find({"token": user_token}).sort("viewed_at", -1).limit(5)
                        async for record in cursor:
                            dynamic_viewers.append({
                                "user_id": record.get("viewer_id", "unknown_id"),
                                "username": record.get("username", "bạn bè"),
                                "display_name": record.get("display_name", "Thành viên"),
                                "viewed_at": record.get("viewed_at", "2026-06-06T15:00:00Z")
                            })
                    
                    if not dynamic_viewers:
                        dynamic_viewers = [
                            {
                                "user_id": "vtl_cloud_id",
                                "username": "vuthanhluan",
                                "display_name": "Vũ Thành Luân",
                                "viewed_at": "2026-06-06T15:00:00Z"
                            }
                        ]
                    
                    data["viewers"] = dynamic_viewers

            # --- 2. XỬ LÝ TRẠNG THÁI VÀ THỜI HẠN GOLD TỪ MONGODB ---
            elif "subscribers" in path:
                if isinstance(data, dict) and "subscriber" in data:
                    is_gold_active = True
                    expiry_date = "2029-12-31T23:59:59Z"
                    
                    if db is not None and user_token:
                        account_record = await db.accounts.find_one({"api_token": user_token})
                        if account_record:
                            # Đọc trực tiếp thời gian từ DB (hỗ trợ expires_at hoặc gold_expires_at)
                            db_expiry = account_record.get("expires_at") or account_record.get("gold_expires_at")
                            if db_expiry:
                                expiry_date = str(db_expiry)
                            
                            is_gold_active = account_record.get("is_active", True)

                    if is_gold_active:
                        data["subscriber"]["entitlements"] = {
                            "Gold": {
                                "expires_date": expiry_date,
                                "product_identifier": "com.locket.gold.yearly",
                                "purchase_date": "2026-01-01T00:00:00Z"
                            }
                        }
            
            response_headers = {k: v for k, v in upstream_headers.items() if k.lower() not in ["content-length", "transfer-encoding", "content-encoding"]}
            return JSONResponse(content=data, status_code=upstream_status, headers=response_headers)
            
        except Exception:
            pass

    response_headers = {k: v for k, v in upstream_headers.items() if k.lower() not in ["content-length", "transfer-encoding", "content-encoding"]}
    return Response(
        content=upstream_content,
        status_code=upstream_status,
        headers=response_headers,
        media_type=upstream_headers.get("content-type")
    )