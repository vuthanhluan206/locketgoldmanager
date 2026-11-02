from fastapi import FastAPI, Response
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.cors import CORSMiddleware
import json

app = FastAPI()

app.add_middleware(
    TrustedHostMiddleware, 
    allowed_hosts=["locketgold.vuthanhluan.bond", "*.vercel.app", "localhost", "127.0.0.1"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Endpoint giả lập bản quyền RevenueCat để kích hoạt Gold
@app.get("/v1/subscribers/{app_user_id}")
async def get_subscriber(app_user_id: str):
    response_data = {
        "request_date": "2026-11-03T00:00:00Z",
        "request_date_ms": 1793750400000,
        "subscriber": {
            "entitlements": {
                "Gold": {
                    "expires_date": "2099-11-03T00:00:00Z",
                    "grace_period_expires_date": None,
                    "product_identifier": "com.locket.gold.yearly",
                    "purchase_date": "2026-11-03T00:00:00Z"
                }
            },
            "first_seen": "2026-11-03T00:00:00Z",
            "original_app_user_id": app_user_id,
            "subscriptions": {
                "com.locket.gold.yearly": {
                    "expires_date": "2099-11-03T00:00:00Z",
                    "is_sandbox": False,
                    "original_purchase_date": "2026-11-03T00:00:00Z",
                    "purchase_date": "2026-11-03T00:00:00Z",
                    "store": "app_store"
                }
            }
        }
    }
    return Response(content=json.dumps(response_data), media_type="application/json")

@app.post("/v1/subscribers/{app_user_id}/attribution")
async def attribution(app_user_id: str):
    return {"rc_attribution_app_id": "success"}

@app.get("/")
async def root():
    return {"status": "online", "service": "Locket Gold Proxy"}
