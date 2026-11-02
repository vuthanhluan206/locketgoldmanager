from fastapi import FastAPI, Response
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
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

# 1. GIAO DIỆN WEB: Mở trên Safari để bấm nút Cài đặt
@app.get("/install", response_class=HTMLResponse)
async def install_page():
    html_content = """
    <html>
        <head>
            <title>Cài đặt Locket Gold</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
        </head>
        <body style="text-align:center; padding-top: 100px; font-family: sans-serif; background-color: #f0f2f5;">
            <h2>Locket Gold Premium</h2>
            <p>Trang tải ứng dụng trực tiếp</p>
            <br>
            <!-- Lệnh itms-services này sẽ gọi hệ điều hành iOS kích hoạt popup cài đặt -->
            <a href="itms-services://?action=download-manifest&url=https://locketgold.vuthanhluan.bond/manifest.plist" 
               style="padding: 15px 40px; background: #007aff; color: white; text-decoration: none; border-radius: 25px; font-size: 18px; font-weight: bold;">
               Cài đặt Ứng dụng
            </a>
        </body>
    </html>
    """
    return html_content

# 2. FILE CẤU HÌNH APPLE: Giao tiếp với iOS để kéo file IPA về máy
@app.get("/manifest.plist")
async def get_manifest():
    # CHÚ Ý: Bạn cần thay thế link .ipa bên dưới bằng link trực tiếp (direct link) chứa file Locket Mod của bạn
    plist_content = """<?xml version="1.0" encoding="UTF-8"?>
    <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
    <plist version="1.0">
    <dict>
        <key>items</key>
        <array>
            <dict>
                <key>assets</key>
                <array>
                    <dict>
                        <key>kind</key>
                        <string>software-package</string>
                        <key>url</key>
                        <string>https://link-cua-ban/Locket_Gold_Mod.ipa</string>
                    </dict>
                </array>
                <key>metadata</key>
                <dict>
                    <key>bundle-identifier</key>
                    <string>com.locket.gold.mod</string>
                    <key>bundle-version</key>
                    <string>1.0</string>
                    <key>kind</key>
                    <string>software</string>
                    <key>title</key>
                    <string>Locket Gold</string>
                </dict>
            </dict>
        </array>
    </dict>
    </plist>"""
    # Trả về định dạng mà Apple yêu cầu
    return Response(content=plist_content, media_type="application/x-apple-aspen-config")

# --- CÁC ENDPOINT REVENUECAT CŨ GIỮ NGUYÊN BÊN DƯỚI ---
@app.get("/v1/subscribers/{app_user_id}")
async def get_subscriber(app_user_id: str):
    response_data = {
        "request_date": "2026-11-03T00:00:00Z",
        "request_date_ms": 1793750400000,
        "subscriber": {
            "entitlements": {"Gold": {"expires_date": "2099-11-03T00:00:00Z", "product_identifier": "com.locket.gold.yearly", "purchase_date": "2026-11-03T00:00:00Z"}},
            "original_app_user_id": app_user_id,
            "subscriptions": {"com.locket.gold.yearly": {"expires_date": "2099-11-03T00:00:00Z", "purchase_date": "2026-11-03T00:00:00Z"}}
        }
    }
    return Response(content=json.dumps(response_data), media_type="application/json")

@app.get("/")
async def root():
    return {"status": "online", "service": "Locket Gold Hub"}
