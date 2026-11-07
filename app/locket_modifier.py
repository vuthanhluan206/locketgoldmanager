import urllib.request
import urllib.error
import json
import os
import gzip
import asyncio
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pymongo import MongoClient

router = APIRouter(tags=["Locket Proxy"])

# Khởi tạo kết nối MongoDB trực tiếp an toàn dựa trên biến môi trường của dự án
MONGO_URI = os.getenv("MONGODB_URI") or os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("MONGODB_DATABASE", "locket_manager")
db = None
if MONGO_URI:
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000, connectTimeoutMS=2000)
        try:
            db = client.get_default_database()
        except Exception:
            db = client[MONGO_DB_NAME]
    except Exception:
        db = None


def _fetch_upstream(req: urllib.request.Request, timeout_limit: float):
    try:
        with urllib.request.urlopen(req, timeout=timeout_limit) as upstream_response:
            return (
                upstream_response.status,
                dict(upstream_response.headers.items()),
                upstream_response.read(),
            )
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers.items()), e.read()


@router.get("/proxy.pac", response_class=Response)
@router.get("/proxy/proxy.pac", response_class=Response)
async def get_root_pac_file(request: Request):
    host = request.headers.get("host", "locketgold-premium.vercel.app")
    pac_content = f"""function FindProxyForURL(url, host) {{
    if (shExpMatch(host, "*locketcamera.com*") || shExpMatch(host, "*revenuecat.com*")) {{
        return "PROXY {host}";
    }}
    return "DIRECT";
}}"""
    return Response(content=pac_content, media_type="application/javascript")


# Endpoint Test nhanh để kiểm tra kết nối
@router.get("/ping", response_class=JSONResponse)
@router.get("/proxy/ping", response_class=JSONResponse)
async def ping_proxy(request: Request):
    return {"status": "success", "message": "Proxy is active and routing correctly!"}


@router.get("/install", response_class=Response)
@router.get("/proxy/install", response_class=Response)
async def download_profile(request: Request):
    host = request.headers.get("host", "locketgold-premium.vercel.app")
    scheme = request.url.scheme
    pac_url = f"{scheme}://{host}/proxy.pac"

    mobileconfig_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>PayloadContent</key>
	<array>
		<dict>
			<key>AutoProxy</key>
			<dict>
				<key>ProxyAutoConfigURLString</key>
				<string>{pac_url}</string>
			</dict>
			<key>PayloadDescription</key>
			<string>Cấu hình Proxy tự động cho Locket Gold</string>
			<key>PayloadDisplayName</key>
			<string>Locket Gold Proxy</string>
			<key>PayloadIdentifier</key>
			<string>com.vuthanhluan.proxy.conf</string>
			<key>PayloadType</key>
			<string>com.apple.webClip.managed</string>
			<key>PayloadUUID</key>
			<string>8A15256A-47B2-4F81-815E-921356A41001</string>
			<key>PayloadVersion</key>
			<integer>1</integer>
		</dict>
	</array>
	<key>PayloadDescription</key>
	<string>Cấu hình mạng tương thích mọi phiên bản iOS</string>
	<key>PayloadDisplayName</key>
	<string>Locket Proxy Manager</string>
	<key>PayloadIdentifier</key>
	<string>com.vuthanhluan.locketmanager.profile</string>
	<key>PayloadOrganization</key>
	<string>Vũ Thành Luân</string>
	<key>PayloadRemovalDisallowed</key>
	<false/>
	<key>PayloadType</key>
	<string>Configuration</string>
	<key>PayloadUUID</key>
	<string>7B241459-36A1-4E72-904D-812445B39002</string>
	<key>PayloadVersion</key>
	<integer>1</integer>
</dict>
</plist>"""

    return Response(
        content=mobileconfig_content,
        media_type="application/x-apple-aspen-config",
        headers={"Content-Disposition": "attachment; filename=locket_proxy.mobileconfig"}
    )


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def dynamic_reverse_proxy(request: Request, path: str):
    clean_path = path.lstrip("/")
    if clean_path.startswith("proxy/"):
        clean_path = clean_path[6:]

    # Bỏ qua các route quản trị hệ thống
    if clean_path.startswith(("admin", "api/admin", "v1/subscribers")) or clean_path in ["", "favicon.ico", "robots.txt", "install", "proxy.pac", "ping"]:
        return JSONResponse(status_code=404, content={"detail": "Not found"})

    # PHÂN TÍCH VÀ ĐỊNH HƯỚNG UPSTREAM THÔNG MINH
    # Nếu đường dẫn chứa từ khóa subscribers hoặc thuộc về RevenueCat -> Trỏ sang api.revenuecat.com
    # Ngược lại, trỏ về api.locketcamera.com
    raw_full_url = str(request.url)
    if "subscribers" in clean_path or "v1/subscribers" in raw_full_url or "revenuecat" in raw_full_url:
        UPSTREAM_TARGET = "https://api.revenuecat.com"
        target_host = "api.revenuecat.com"
    else:
        UPSTREAM_TARGET = "https://api.locketcamera.com"
        target_host = "api.locketcamera.com"

    url = f"{UPSTREAM_TARGET}/{clean_path}"
    
    query_params = str(request.url.query)
    if query_params:
        url += f"?{query_params}"

    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("content-length", None)
    headers["Host"] = target_host
    headers["Accept-Encoding"] = "identity"

    method = request.method
    content_type_header = headers.get("content-type", "")
    auth_header = headers.get("authorization", "")
    user_token = auth_header.replace("Bearer ", "").strip()

    is_upload = method in ["POST", "PUT", "PATCH"] and (
        "multipart/form-data" in content_type_header 
        or "video/" in content_type_header 
        or "posts" in clean_path 
        or "moments" in clean_path
    )
    
    body = await request.body()

    if method in ["POST", "PUT", "PATCH"] and ("posts" in clean_path or "moments" in clean_path) and body:
        try:
            req_json = json.loads(body.decode("utf-8"))
            if isinstance(req_json, dict):
                if "is_private" not in req_json:
                    req_json["is_private"] = False
                body = json.dumps(req_json).encode("utf-8")
        except Exception:
            pass

    try:
        req = urllib.request.Request(url, data=body if body else None, headers=headers, method=method)
        timeout_limit = 90.0 if is_upload else 30.0
        upstream_status, upstream_headers, upstream_content = await asyncio.to_thread(
            _fetch_upstream, req, timeout_limit
        )
    except Exception as exc:
        return JSONResponse(status_code=502, content={"error": f"Bad Gateway to Upstream: {str(exc)}"})

    response_headers = {
        k: v for k, v in upstream_headers.items()
        if k.lower() not in ["content-length", "transfer-encoding", "content-encoding"]
    }

    if is_upload and "application/json" not in upstream_headers.get("content-type", "").lower():
        return Response(
            content=upstream_content,
            status_code=upstream_status,
            headers=response_headers,
            media_type=upstream_headers.get("content-type")
        )

    content_type = upstream_headers.get("content-type", "")

    if "application/json" in content_type.lower() and upstream_content:
        try:
            raw_content = upstream_content
            if "gzip" in upstream_headers.get("content-encoding", "").lower():
                try:
                    raw_content = gzip.decompress(upstream_content)
                except Exception:
                    pass

            data = json.loads(raw_content.decode("utf-8"))

            # --- ÉP CẤU HÌNH THỜI LƯỢNG VIDEO LÊN 60 GIÂY VÀ MỞ KHÓA TÍNH NĂNG ---
            if isinstance(data, dict):
                data["max_video_duration_seconds"] = 60
                data["video_max_seconds"] = 60
                data["duration_limit"] = 60
                data["max_video_duration"] = 60
                data["video_recording_limit"] = 60
                data["enable_library_video_upload"] = True
                data["enable_private_posts"] = True
                data["is_gold"] = True
                data["has_ios_subscription"] = True
                
                data["unlocked_filters"] = True
                data["has_unlocked_filters"] = True
                data["is_premium_user"] = True
                data["filters_unlocked"] = True
                data["camera_filters_enabled"] = True

                if "features" in data and isinstance(data["features"], dict):
                    data["features"]["max_video_duration_seconds"] = 60
                    data["features"]["video_recording_limit"] = 60
                    data["features"]["unlocked_all_filters"] = True
                    data["features"]["filters_unlocked"] = True

            # --- 1. XỬ LÝ DANH SÁCH NGƯỜI XEM (Viewers) ---
            if "moments" in clean_path or "posts" in clean_path or "viewer" in clean_path:
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

                if isinstance(data, dict):
                    data["viewers"] = dynamic_viewers
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            item["viewers"] = dynamic_viewers

            # --- 2. XỬ LÝ TRẠNG THÁI VÀ THỜI HẠN GOLD TỪ MONGODB & REVENUECAT ---
            elif "subscribers" in clean_path or "user" in clean_path:
                if isinstance(data, dict):
                    if "subscriber" not in data or not isinstance(data["subscriber"], dict):
                        data["subscriber"] = {}

                    is_gold_active = True
                    expiry_date = "2029-12-31T23:59:59Z"

                    if db is not None and user_token:
                        try:
                            account_record = db.accounts.find_one({"api_token": user_token})
                            if account_record:
                                db_expiry = (
                                    account_record.get("expires_date")
                                    or account_record.get("expires_at")
                                    or account_record.get("gold_expires_at")
                                )
                                if db_expiry:
                                    expiry_date = (
                                        db_expiry.isoformat().replace("+00:00", "Z")
                                        if hasattr(db_expiry, "isoformat")
                                        else str(db_expiry)
                                    )
                                is_gold_active = account_record.get("is_active", True)
                        except Exception:
                            pass

                    if is_gold_active:
                        data["subscriber"]["entitlements"] = {
                            "Gold": {
                                "expires_date": expiry_date,
                                "grace_period_expires_date": None,
                                "product_identifier": "com.locket.gold.yearly",
                                "purchase_date": "2026-01-01T00:00:00Z"
                            },
                            "unlimited_video_length": {
                                "expires_date": expiry_date,
                                "grace_period_expires_date": None,
                                "product_identifier": "com.locket.gold.yearly",
                                "purchase_date": "2026-01-01T00:00:00Z"
                            },
                            "allow_photo_library_videos": {
                                "expires_date": expiry_date,
                                "grace_period_expires_date": None,
                                "product_identifier": "com.locket.gold.yearly",
                                "purchase_date": "2026-01-01T00:00:00Z"
                            },
                            "private_posts": {
                                "expires_date": expiry_date,
                                "grace_period_expires_date": None,
                                "product_identifier": "com.locket.gold.yearly",
                                "purchase_date": "2026-01-01T00:00:00Z"
                            },
                            "unlocked_filters": {
                                "expires_date": expiry_date,
                                "grace_period_expires_date": None,
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
                        if "non_subscriptions" not in data["subscriber"]:
                            data["subscriber"]["non_subscriptions"] = {}
                        data["subscriber"]["non_subscriptions"]["max_video_duration"] = [
                            {
                                "id": "max_duration_60s",
                                "purchase_date": "2026-01-01T00:00:00Z",
                                "store": "app_store"
                            }
                        ]

            return JSONResponse(content=data, status_code=upstream_status, headers=response_headers)

        except Exception:
            pass

    return Response(
        content=upstream_content,
        status_code=upstream_status,
        headers=response_headers,
        media_type=upstream_headers.get("content-type")
    )
