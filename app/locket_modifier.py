import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from app.database import db

app = FastAPI(title="Locket Dynamic Cloud Modifier Proxy", version="2.0.0")

UPSTREAM_TARGET = "https://api.locketcamera.com"

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def dynamic_reverse_proxy(request: Request, path: str):
    client = httpx.AsyncClient(follow_redirects=True)
    url = f"{UPSTREAM_TARGET}/{path}"
    
    headers = dict(request.headers)
    headers.pop("host", None)
    
    body = await request.body()
    query_params = request.query_params

    # Trích xuất Token xác thực từ Header để nhận diện tài khoản
    auth_header = headers.get("authorization", "")
    user_token = auth_header.replace("Bearer ", "").strip()

    try:
        upstream_response = await client.request(
            method=request.method,
            url=url,
            headers=headers,
            params=query_params,
            content=body,
            timeout=30.0
        )
    except httpx.RequestError as e:
        return JSONResponse(status_code=502, content={"error": f"Bad Gateway to Upstream: {str(e)}"})
    finally:
        await client.aclose()

    content_type = upstream_response.headers.get("content-type", "")
    
    if "application/json" in content_type:
        try:
            data = upstream_response.json()
            
            # --- 1. XỬ LÝ DANH SÁCH NGƯỜI XEM ĐỘNG (Moments/Posts) ---
            if "moments" in path or "posts" in path:
                if isinstance(data, dict):
                    dynamic_viewers = []
                    # Có thể truy vấn lịch sử xem từ DB hoặc tạo danh sách phản hồi mẫu
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
                    expiry_date = "2029-12-31T23:59:59Z"  # Mặc định xa nếu không tìm thấy
                    
                    if db is not None and user_token:
                        # Tra cứu tài khoản trong collection accounts
                        account_record = await db.accounts.find_one({"api_token": user_token})
                        if account_record:
                            # Đọc trực tiếp thời gian hết hạn từ DB (hỗ trợ cả expires_at và gold_expires_at)
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
            
            response_headers = dict(upstream_response.headers)
            response_headers.pop("content-length", None)
            
            return JSONResponse(
                content=data,
                status_code=upstream_response.status_code,
                headers=response_headers
            )
            
        except Exception:
            pass

    response_headers = dict(upstream_response.headers)
    response_headers.pop("content-length", None)
    
    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=response_headers,
        media_type=upstream_response.headers.get("content-type")
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)