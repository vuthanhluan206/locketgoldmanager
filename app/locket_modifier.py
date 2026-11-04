import urllib.request
import urllib.error
import json
import os
import gzip
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pymongo import MongoClient

router = APIRouter(prefix="/proxy", tags=["Locket Proxy"])

UPSTREAM_TARGET = "https://api.locketcamera.com"

MONGO_URI = os.getenv("MONGODB_URI") or os.getenv("MONGO_URI")
db = None
if MONGO_URI:
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
        db = client.get_default_database()
    except Exception:
        pass

@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def dynamic_reverse_proxy(request: Request, path: str):
    url = f"{UPSTREAM_TARGET}/{path}"
    
    query_params = str(request.url.query)
    if query_params:
        url += f"?{query_params}"

    headers = dict(request.headers)
    headers.pop("host", None)
    headers["Host"] = "api.locketcamera.com"
    headers["Accept-Encoding"] = "identity"

    body = await request.body()
    method = request.method

    auth_header = headers.get("authorization", "")
    user_token = auth_header.replace("Bearer ", "").strip()

    try:
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
            raw_content = upstream_content
            if "gzip" in upstream_headers.get("content-encoding", "").lower():
                try:
                    raw_content = gzip.decompress(upstream_content)
                except Exception:
                    pass

            data = json.loads(raw_content.decode("utf-8"))
            
            # --- 1. ÉP CẤU HÌNH TOÀN DIỆN CHO APP CONFIG ---
            if isinstance(data, dict):
                data["max_video_duration_seconds"] = 60
                data["video_max_seconds"] = 60
                data["duration_limit"] = 60
                data["max_video_duration"] = 60
                data["video_recording_limit"] = 60
                data["enable_library_video_upload"] = True
                data["enable_private_posts"] = True
                data["is_gold"] = True
                data["unlocked_filters"] = True
                data["has_unlocked_filters"] = True
                data["is_premium_user"] = True
                data["filters_unlocked"] = True

                if "features" in data and isinstance(data["features"], dict):
                    data["features"]["max_video_duration_seconds"] = 60
                    data["features"]["video_recording_limit"] = 60
                    data["features"]["unlocked_all_filters"] = True
                    data["features"]["filters_unlocked"] = True

            # --- 2. XỬ LÝ DANH SÁCH NGƯỜI XEM (Moments/Posts) ---
            if "moments" in path or "posts" in path:
                if isinstance(data, dict):
                    dynamic_viewers = []
                    if db is not None and user_token:
                        try:
                            cursor = db.viewers_history.find({"token": user_token}).sort("viewed_at", -1).limit(5)
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
                    
                    data["viewers"] = dynamic_viewers

            # --- 3. BỔ SUNG ĐẦY ĐỦ ENTITLEMENTS CHO REVENUECAT (SUBSCRIBERS) ---
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
                            },
                            "unlimited_video_length": {
                                "expires_date": expiry_date,
                                "product_identifier": "com.locket.gold.yearly",
                                "purchase_date": "2026-01-01T00:00:00Z"
                            },
                            "allow_photo_library_videos": {
                                "expires_date": expiry_date,
                                "product_identifier": "com.locket.gold.yearly",
                                "purchase_date": "2026-01-01T00:00:00Z"
                            },
                            "private_posts": {
                                "expires_date": expiry_date,
                                "product_identifier": "com.locket.gold.yearly",
                                "purchase_date": "2026-01-01T00:00:00Z"
                            }
                        }
                        data["subscriber"]["subscriptions"] = {
                            "com.locket.gold.yearly": {
                                "expires_date": expiry_date,
                                "is_sandbox": False,
                                "original_purchase_date": "2026-01-01T00:00:00Z",
                                "purchase_date": "2026-01-01T00:00:00Z",
                                "ownership_type": "PURCHASED",
                                "store": "app_store"
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
