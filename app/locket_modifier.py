import urllib.request
import urllib.error
import json
import os
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pymongo import MongoClient

app = FastAPI(title="Locket Dynamic Cloud Modifier Proxy", version="2.3.2")

UPSTREAM_TARGET = "https://api.locketcamera.com"

MONGO_URI = os.getenv("MONGODB_URI") or os.getenv("MONGO_URI")
db = None
if MONGO_URI:
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
        db = client.get_default_database()
    except Exception:
        pass

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def dynamic_reverse_proxy(request: Request, path: str):
    url = f"{UPSTREAM_TARGET}/{path}"
    
    query_params = str(request.url.query)
    if query_params:
        url += f"?{query_params}"

    headers = dict(request.headers)
    headers.pop("host", None)
    headers["Host"] = "api.locketcamera.com"

    method = request.method
    content_type_header = headers.get("content-type", "")
    auth_header = headers.get("authorization", "")
    user_token = auth_header.replace("Bearer ", "").strip()

    is_upload = method in ["POST", "PUT", "PATCH"] and ("multipart/form-data" in content_type_header or "posts" in path or "moments" in path)
    body = await request.body()

    try:
        req = urllib.request.Request(url, data=body if body else None, headers=headers, method=method)
        timeout_limit = 60.0 if is_upload else 30.0

        with urllib.request.urlopen(req, timeout=timeout_limit) as upstream_response:
            upstream_status = upstream_response.status
            upstream_headers = dict(upstream_response.headers.items())
            upstream_content = upstream_response.read()
            
    except urllib.error.HTTPError as e:
        upstream_status = e.code
        upstream_headers = dict(e.headers.items())
        upstream_content = e.read()
    except Exception as exc:
        return JSONResponse(status_code=502, content={"error": f"Bad Gateway to Upstream: {str(exc)}"})

    response_headers = {k: v for k, v in upstream_headers.items() if k.lower() not in ["content-length", "transfer-encoding", "content-encoding"]}

    if is_upload:
        return Response(
            content=upstream_content,
            status_code=upstream_status,
            headers=response_headers,
            media_type=upstream_headers.get("content-type")
        )

    content_type = upstream_headers.get("content-type", "")
    
    if "application/json" in content_type and upstream_content:
        try:
            data = json.loads(upstream_content.decode("utf-8"))
            
            # --- 1. XỬ LÝ DANH SÁCH NGƯỜI XEM (Hỗ trợ cả dạng Dict và List) ---
            if "moments" in path or "posts" in path or "viewer" in path:
                dynamic_viewers = []
                if db is not None and user_token:
                    try:
                        cursor = db.viewers_history.find({"token": user_token}).sort("viewed_at", -1).limit(10)
                        for record in cursor:
                            dynamic_viewers.append({
                                "user_id": str(record.get("viewer_id", "unknown_id")),
                                "username": record.get("username", "bạn bè"),
                                "display_name": record.get("display_name", "Thành viên"),
                                "viewed_at": record.get("viewed_at", "2026-06-06T15:00:00Z")
                            })
                    except Exception:
                        pass
                
                if not dynamic_viewers:
                    dynamic_viewers = [
                        {
                            "user_id": "vtl_cloud_id",
                            "username": "vuthanhluan",
                            "display_name": "Vũ Thành Luân",
                            "viewed_at": "2026-06-06T15:00:00Z"
                        }
                    ]
                
                # Nếu phản hồi là một đối tượng dict, gán trực tiếp trường viewers vào
                if isinstance(data, dict):
                    data["viewers"] = dynamic_viewers
                elif isinstance(data, list):
                    # Trường hợp API trả về danh sách các bài đăng, lặp qua để chèn viewers vào từng bài đăng
                    for item in data:
                        if isinstance(item, dict):
                            item["viewers"] = dynamic_viewers

            # --- 2. XỬ LÝ TRẠNG THÁI GOLD ---
            elif "subscribers" in path or "user" in path:
                if isinstance(data, dict):
                    if "subscriber" not in data or not isinstance(data["subscriber"], dict):
                        data["subscriber"] = {}
                    
                    is_gold_active = True
                    expiry_date = "2029-12-31T23:59:59Z"
                    
                    if db is not None and user_token:
                        try:
                            account_record = db.accounts.find_one({"api_token": user_token})
                            if account_record:
                                db_expiry = account_record.get("expires_at") or account_record.get("gold_expires_at")
                                if db_expiry:
                                    expiry_date = str(db_expiry)
                                is_gold_active = account_record.get("is_active", True)
                        except Exception:
                            pass

                    if is_gold_active:
                        data["subscriber"]["entitlements"] = {
                            "Gold": {
                                "expires_date": expiry_date,
                                "product_identifier": "com.locket.gold.yearly",
                                "purchase_date": "2026-01-01T00:00:00Z"
                            }
                        }
            
            return JSONResponse(content=data, status_code=upstream_status, headers=response_headers)
            
        except Exception:
            pass

    return Response(
        content=upstream_content,
        status_code=upstream_status,
        headers=response_headers,
        media_type=upstream_headers.get("content-type")
    )
