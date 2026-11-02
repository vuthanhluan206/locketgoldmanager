from fastapi import FastAPI, Response
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from datetime import datetime
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

# --- 1. CƠ SỞ DỮ LIỆU KHÁCH HÀNG ---
# Thêm ID Locket của khách vào đây kèm theo ngày hết hạn (Năm-Tháng-Ngày)
VIP_USERS = {
    "$RCAnonymousID:7b5d1...": "2026-12-31", # Khách A (Còn hạn)
    "$RCAnonymousID:9a2f4...": "2024-01-01", # Khách B (Đã hết hạn)
}

# --- 2. GIAO DIỆN WEB TẢI CẤU HÌNH (Giao diện chuẩn của bạn) ---
@app.get("/", response_class=HTMLResponse)
async def home_page():
    html_content = """<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cài đặt Locket Gold Universal</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: #f2f2f7;
            color: #1c1c1e;
            text-align: center;
            padding: 40px 20px;
            margin: 0;
        }
        .container {
            max-width: 400px;
            margin: 0 auto;
            background: #ffffff;
            padding: 30px 20px;
            border-radius: 20px;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.05);
        }
        h2 {
            font-size: 22px;
            margin-bottom: 10px;
            color: #000;
        }
        p {
            font-size: 14px;
            color: #6c6c70;
            margin-bottom: 25px;
            line-height: 1.5;
        }
        .btn {
            display: block;
            width: 100%;
            padding: 14px 0;
            background-color: #007aff;
            color: white;
            font-size: 16px;
            font-weight: 600;
            text-decoration: none;
            border-radius: 12px;
            box-shadow: 0 4px 10px rgba(0, 122, 255, 0.3);
            transition: background 0.2s;
            box-sizing: border-box;
        }
        .btn:active {
            background-color: #0056b3;
        }
        .note {
            margin-top: 20px;
            font-size: 12px;
            color: #8e8e93;
        }
    </style>
</head>
<body>

    <div class="container">
        <h2>Locket Gold Premium</h2>
        <p>Bấm vào nút bên dưới để hệ thống tự động kích hoạt popup tải cấu hình hồ sơ cho thiết bị của bạn (Hạn đến tháng 12/2026).</p>
        
        <a href="#" id="installBtn" class="btn">Tải về cấu hình ngay</a>
        
        <div class="note">Lưu ý: Bắt buộc mở bằng trình duyệt Safari trên iPhone để cài đặt chính xác.</div>
    </div>

    <script>
        const mobileConfigXML = `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>PayloadContent</key>
    <array>
        <dict>
            <key>PayloadType</key>
            <string>com.apple.security.root</string>
            <key>PayloadVersion</key>
            <integer>1</integer>
            <key>PayloadIdentifier</key>
            <string>com.locketgold.universal.ca</string>
            <key>PayloadUUID</key>
            <string>AA18E842-4B4C-4CD9-B1FB-183A40386AA6</string>
            <key>PayloadDisplayName</key>
            <string>LocketGold Universal CA</string>
            <key>PayloadDescription</key>
            <string>Chứng chỉ dùng chung cho hệ thống Locket Gold</string>
            <key>PayloadCertificateFileName</key>
            <string>LocketGold_CA.crt</string>
            <key>PayloadContent</key>
            <data>
            MIIFVDCCAzygAwIBAgIUCu2NDd/O/wPGB3RJ40XTNmVVGDQwDQYJKoZIhvcNAQELBQAwQjELMAkGA1UEBhMCVVMxFjAUBgNVBAoMDUxvY2tldEdvbGQgQ0ExGzAZBgNVBAMMEkxvY2tldEdvbGQgUm9vdCBDQTAeFw0yNjA5MjgxNjMwMzFaFw0zNjA5MjUxNjMwMzFaMEIxCzAJBgNVBAYTAlVTMRYwFAYDVQQKDA1Mb2NrZXRHb2xkIENBMRswGQYDVQQDDBJMb2NrZXRHb2xkIFJvb3QgQ0EwggIiMA0GCSqGSIb3DQEBAQUAA4ICDwAwggIKAoICAQCqJSF1M9+BKLQ6h7NcD2JOROP3cwS4IkV7uDTzA4EKpX6tFV+uNLs4IMrwYQc5xp14R7/NVI8jpmikAQ5rYV0VaeWldpp4aIN4o+l9ht2y+mLF0vAbVQmMny3DDsD5v3tlN/wWBYP8P4s1y8j967ogK/FjKaW7NzyDcNrX3W2b95KMs/0S2T/utW8aXZGg91FNPm8Fv4JXovIgsApxFwLpGLrwUJdfVWY/eWNJrFZYa64lncEW/HXqezZt6vqtzps6rIDqHotBy1bQQ428N/D4XBMBN3ZL63lG4Mf+PpMt7CI/bRY9XJxRpGcTXULyqqgw7m4F8hhm4hmvwnQ6Y4lHaAk5WX3KO5j1ejYqrDGhoZ4C7AI3rAHXnLj8EufUEoCvfha49aNPbfH5kFnSepEt8gko0mh9ZuPkN75Qbst1KuE3U9A/q5xpaZYN5SG7JTxfWqFUscCVUAm+lFm0F1clxe99YxaRZftVQOxTk+AsPfm+KGvUBynvHqndpBusa6TE3Ht9gJfwxCa9nXsm+D/fdPRnasXeXYWR28LH5sMNDhN+kdUbWP56r1gpk6mxUj309A27YZgX0JUWYPV5P3IZYmuGyHJWdH72ZW24Eg2yZK4gBn/8r7S+Zla7h522IFkS3KwHLsUxuwn/C+yW9GNM/+uD0NEH38EQFi9Oqw1t8wIDAQABo0IwQDAPBgNVHRMBAf8EBTADAQH/MA4GA1UdDwEB/wQEAwIBhjAdBgNVHQ4EFgQUr+JPC5FaF1YxO58iWS8Nuuc2s2swDQYJKoZIhvcNAQELBQADggIBADCIeX1dmk8eAM8PvRU0ckvaEWAkgqQnA4zGUKRZM5+nBVf5EbXMDjdZROtVxh0ihOlFNL5pamvyOpVuLpR18mC+ujaTow2Afl5DIXHReO+kisJ9LR/WLmqPrONpc7whKMac499M+JRr5Xs9ziZ/XC/mxaZOV2EZQ+ogUZSht51i2ktckCU6xob1bNbZvAA6x9xehcNOKepn74UcPsbaZizf8xMmBg1xGxYTnLejTfgFHGIIlgbOZ88HFdLBiDy9oR0TsNNob5T7UbIUcokUu9SUreTsowAtgynXM+kLvOZNfosk1U5012HmmbZcCbx3gfa/83Q1C9YyjdDA8IywksSCgDcSHztKUhEdNUEmdjcKTfU5oZEkY4lBYizdhhiydhZdqyYECCnJkW6oC31UeHSm21Bxl1K0B9pkMIhFvgfwt4Z6dHmCKKAsXcrey2jdLxPb4DDz3b1BCfNeNvSpm2JLTO4vHE+ZAn2pVtlbd4dH05DXJPakfGc6iKAdxhPZTWyY3xVyuneg9pYTijGdh4sS3rShGLVaD0i31Crac3T6piOxtQTdY1jsW+L4kgdfnOhkt3r06gdlst6bG7uhnq21AuJDGWOZkKifIPWmqUEl4NVlOl4Mc2Y7CQclqOSp2G8rvMuK/beCGsHHnjZIrQVdkq+/afHHCN0I2yZkxO3R
            </data>
        </dict>
        <dict>
            <key>PayloadType</key>
            <string>com.apple.dnsSettings.managed</string>
            <key>PayloadVersion</key>
            <integer>1</integer>
            <key>PayloadIdentifier</key>
            <string>com.locketgold.universal.dns</string>
            <key>PayloadUUID</key>
            <string>6F897F59-27E3-4FA8-9D3E-1D1133BF4BD8</string>
            <key>PayloadDisplayName</key>
            <string>Locket Gold Universal (Hạn 12/2026)</string>
            <key>PayloadDescription</key>
            <string>Cấu hình dùng chung cho mọi thiết bị - Hạn đến tháng 12 năm 2026</string>
            <key>DNSSettings</key>
            <dict>
                <key>DNSProtocol</key>
                <string>HTTPS</string>
                <key>ServerURL</key>
                <string>https://dns.nextdns.io/8f4cb9</string>
                <key>SupplementalMatchDomains</key>
                <array>
                    <string>api.revenuecat.com</string>
                    <string>*.revenuecat.com</string>
                    <string>firebaseremoteconfig.googleapis.com</string>
                    <string>*.firebaseremoteconfig.googleapis.com</string>
                    <string>firebaseremoteconfigrealtime.googleapis.com</string>
                    <string>*.firebaseremoteconfigrealtime.googleapis.com</string>
                    <string>firebaselogging.googleapis.com</string>
                    <string>*.firebaselogging.googleapis.com</string>
                    <string>api.locketcamera.com</string>
                    <string>*.locketcamera.com</string>
                </array>
            </dict>
            <key>ProhibitDisablement</key>
            <false/>
        </dict>
    </array>
    <key>PayloadDisplayName</key>
    <string>Locket Gold Universal (Hạn 12/2026)</string>
    <key>PayloadDescription</key>
    <string>Cấu hình dùng chung cho tất cả các máy để kích hoạt Locket Gold đến tháng 12/2026.</string>
    <key>PayloadIdentifier</key>
    <string>com.locketgold.universal.profile</string>
    <key>PayloadOrganization</key>
    <string>Locket Gold Community</string>
    <key>PayloadRemovalDisallowed</key>
    <false/>
    <key>PayloadType</key>
    <string>Configuration</string>
    <key>PayloadUUID</key>
    <string>00C1F18A-50E5-4F85-ADAA-15DC8436FADC</string>
    <key>PayloadVersion</key>
    <integer>1</integer>
</dict>
</plist>`;

        document.getElementById('installBtn').addEventListener('click', function(e) {
            e.preventDefault();
            const blob = new Blob([mobileConfigXML], { type: 'application/x-apple-aspen-config' });
            const url = URL.createObjectURL(blob);
            
            const a = document.createElement('a');
            a.href = url;
            a.download = 'LocketGold_2026.mobileconfig';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        });
    </script>
</body>
</html>"""
    return html_content


# --- 3. HỆ THỐNG XỬ LÝ BẢN QUYỀN VÀ THỜI HẠN (REVENUECAT) ---
@app.get("/v1/subscribers/{app_user_id}")
async def get_subscriber(app_user_id: str):
    is_gold = False
    
    # Kiểm tra ID có trong danh sách VIP và còn hạn không
    if app_user_id in VIP_USERS:
        expiration_date = datetime.strptime(VIP_USERS[app_user_id], "%Y-%m-%d")
        if datetime.now() <= expiration_date:
            is_gold = True 

    if is_gold:
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
        response_data = {
            "request_date": "2026-11-03T00:00:00Z",
            "request_date_ms": 1793750400000,
            "subscriber": {
                "entitlements": {},
                "original_app_user_id": app_user_id,
                "subscriptions": {}
            }
        }

    return Response(content=json.dumps(response_data), media_type="application/json")

@app.post("/v1/subscribers/{app_user_id}/attribution")
async def attribution(app_user_id: str):
    return {"rc_attribution_app_id": "success"}
