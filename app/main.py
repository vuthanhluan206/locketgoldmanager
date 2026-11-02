from fastapi import FastAPI, Response
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import json

app = FastAPI()

app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# 1. DANH SÁCH KHÁCH HÀNG (DATABASE GIẢ LẬP)
# Trong thực tế, bạn nên dùng MySQL, PostgreSQL hoặc Firebase để dễ thêm/bớt khách hàng.
# Key là 'app_user_id' của người dùng trong Locket, Value là ngày hết hạn (YYYY-MM-DD)
VIP_USERS = {
    "$RCAnonymousID:7b5d1...": "2026-12-31", # Khách hàng A (Còn hạn)
    "$RCAnonymousID:9a2f4...": "2024-01-01", # Khách hàng B (Đã hết hạn)
}

@app.get("/v1/subscribers/{app_user_id}")
async def get_subscriber(app_user_id: str):
    # 2. KIỂM TRA ID NGƯỜI DÙNG CÓ TRONG DANH SÁCH VIP KHÔNG
    is_gold = False
    
    if app_user_id in VIP_USERS:
        # Lấy ngày hết hạn của khách và so sánh với ngày giờ hiện tại
        expiration_date = datetime.strptime(VIP_USERS[app_user_id], "%Y-%m-%d")
        if datetime.now() <= expiration_date:
            is_gold = True # Còn hạn -> Cho phép lên Gold

    # 3. TRẢ VỀ KẾT QUẢ DỰA TRÊN TRẠNG THÁI
    if is_gold:
        # JSON Gói Gold (Thành công)
        response_data = {
            "request_date": "2026-11-03T00:00:00Z",
            "request_date_ms": 1793750400000,
            "subscriber": {
                "entitlements": {
                    "Gold": {
                        "expires_date": "2099-11-03T00:00:00Z",
                        "product_identifier": "com.locket.gold.yearly",
                        "purchase_date": "2026-11-03T00:00:00Z"
                    }
                },
                "original_app_user_id": app_user_id,
                "subscriptions": {
                    "com.locket.gold.yearly": {
                        "expires_date": "2099-11-03T00:00:00Z",
                        "purchase_date": "2026-11-03T00:00:00Z"
                    }
                }
            }
        }
    else:
        # JSON Tài khoản thường (Hết hạn hoặc chưa đăng ký)
        response_data = {
            "request_date": "2026-11-03T00:00:00Z",
            "request_date_ms": 1793750400000,
            "subscriber": {
                "entitlements": {}, # Cắt toàn bộ quyền lợi
                "original_app_user_id": app_user_id,
                "subscriptions": {}
            }
        }

    return Response(content=json.dumps(response_data), media_type="application/json")

@app.post("/v1/subscribers/{app_user_id}/attribution")
async def attribution(app_user_id: str):
    return {"rc_attribution_app_id": "success"}
