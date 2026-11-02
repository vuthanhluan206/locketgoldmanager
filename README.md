# Locket Gold License Manager

FastAPI + MongoDB, landing page HTML/CSS/JS và dashboard được bảo vệ ở server. Đây là hệ thống cấp phép độc lập cho ứng dụng bạn kiểm soát; không tự tích hợp vào Locket/RevenueCat chính thức, không chuyển hướng HTTPS hay can thiệp giao dịch của dịch vụ đó. JSON trả về có dạng tương tự RevenueCat, không cam kết tương thích toàn bộ SDK RevenueCat.

## Chạy nhanh (Python 3.11+ và Docker)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Điền giá trị vừa sinh vào `ADMIN_TOKEN` trong `.env` (không dùng token ví dụ). Điền ID NextDNS gồm 6 ký tự hex từ dashboard NextDNS vào `NEXTDNS_ID`. Nếu cần chèn CA, đặt `ROOT_CA_PATH` trỏ đến chứng chỉ CA công khai PEM/DER mà bạn sở hữu và đã kiểm tra; không đưa private key vào dự án. Bỏ trống sẽ chỉ có payload DNS. Không tự sinh CA giả vì người dùng cần biết họ đang tin tưởng chứng chỉ nào.

```powershell
docker compose up -d
uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

Mở `http://127.0.0.1:8000/`. Admin mở `http://127.0.0.1:8000/?admin=TOKEN_CUA_BAN`. Server kiểm tra token trước khi chèn dashboard vào trang. JavaScript xóa query khỏi URL ngay sau khi mở và giữ token trong bộ nhớ; tải lại trang sẽ trở về trang khách hàng. Nút Thoát xóa token trong bộ nhớ. Query token vẫn có thể xuất hiện trong log proxy/hạ tầng hoặc lịch sử đồng bộ trước khi JavaScript chạy: cấu hình proxy không ghi query string, không chia sẻ link, và dùng HTTPS khi triển khai thật. Các API admin luôn yêu cầu Bearer token, không chấp nhận query token.

Landing page tải `/profile.mobileconfig` thành Blob rồi kích hoạt download. Khi chưa đặt NextDNS ID, server trả 503 kèm hướng dẫn. Profile là XML chưa ký, iOS có thể hiển thị chưa xác minh; người dùng phải tự xác nhận cài đặt trong Cài đặt. Chèn CA không tự bật full trust trên iOS và không làm ứng dụng Locket gọi API này.

## API

| Method | URL | Xác thực / hành vi |
|---|---|---|
| GET | `/` | Trang khách; query `admin` hợp lệ mới nhận dashboard |
| GET | `/profile.mobileconfig` | Công khai, cấu hình NextDNS và CA nếu đã cung cấp |
| GET | `/v1/subscribers/{account_id}` | Công khai, Gold khi hạn > UTC hiện tại; còn lại entitlements rỗng |
| POST | `/admin/add-account` | Bearer token; thêm hoặc cập nhật theo ID |
| GET | `/admin/accounts?skip=0&limit=50` | Bearer token; tối đa 100 dòng/trang |
| DELETE | `/admin/accounts/{account_id}` | Bearer token; 204 hoặc 404 |

POST body:

```json
{"locket_id":"example_user_123","expires_date":"2026-12-31T23:59:59Z"}
```

Ngày hết hạn phải ở tương lai và có múi giờ. ID tối đa 128 ký tự, dùng chữ ASCII, số hoặc `_ $ : @ . -`. Database dùng unique index cho ID; gia hạn cập nhật bản ghi, không xóa tự động tài khoản hết hạn. API subscriber không trả token hay danh sách tài khoản. Lỗi kết nối DB trả 503 thay vì cấp quyền. Endpoint subscriber công khai theo yêu cầu; ứng dụng sở hữu hệ thống nên xác thực người gọi nếu cần ngăn tra cứu trạng thái ID tùy ý.

Không bật CORS vì frontend cùng origin. Không có analytics/CDN bên ngoài. Token không nằm trong HTML hoặc source frontend. MongoDB Docker chỉ bind localhost; khi triển khai thật dùng database có xác thực, backup, TLS và reverse proxy HTTPS với giới hạn tốc độ, giới hạn request body. Không public cổng MongoDB.

## Kiểm thử

```powershell
pip install -r requirements-dev.txt
python -m pytest -q
```

Tests HTTP dùng database giả để kiểm tra phân quyền, validation và quyền Gold; kiểm tra profile bằng parser plist. Chạy MongoDB thật để kiểm tra kết nối, index, lưu trữ và khởi động server. Cần kiểm tra tải/cài trên iPhone thật trước khi phân phối.

## Cấu trúc

`app/config.py`: biến môi trường; `database.py`: lifecycle MongoDB; `models.py`: validation và entitlement; `security.py`: Bearer token; `routes.py`: API; `profile.py`: XML mobileconfig; `main.py`: khởi tạo ứng dụng và security headers. `web/index.html` chứa landing page, CSS và JS; `web/admin.html` là fragment riêng chỉ được server chèn sau xác thực.

Tài liệu tham khảo: [MongoDB FastAPI Async](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/integrations/fastapi-integration/), [Apple DNS Settings](https://support.apple.com/guide/deployment/dns-settings-payload-settings-dep86469ba99/web).
