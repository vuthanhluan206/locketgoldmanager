# Locket Gold Manager

FastAPI + MongoDB. Một file `web/index.html` chứa trang tải cấu hình và giao diện đăng nhập/quản trị. Server loại bỏ phần admin khỏi phản hồi `/`. `/admin` hiển thị màn hình đăng nhập; tất cả dữ liệu/thao tác admin yêu cầu phiên Bearer được xác minh bằng MongoDB. Không còn token tĩnh hoặc token trong URL.

Đây là hệ thống cấp phép độc lập cho ứng dụng bạn kiểm soát. DNS và CA không tự kích hoạt Gold trong Locket chính thức; JSON subscriber là hợp đồng nội bộ có dạng tương tự RevenueCat, không cam kết tương thích SDK RevenueCat.

## Chạy local (Python 3.11+, Docker Desktop đang chạy)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python -m app.bootstrap
```

Không ghi đè `.env` đã có nếu muốn giữ cấu hình. `app.bootstrap` hỏi email và mật khẩu hai lần (ẩn khi nhập), chỉ lưu email và hash có salt vào `.env`. Nhập tài khoản bạn muốn sử dụng; không có email/mật khẩu quản trị mặc định trong source. Bản local trong phiên làm việc này đã được cấu hình bằng tài khoản bạn yêu cầu.

Điền `MONGODB_URI` và `NEXTDNS_ID` của bạn trong `.env`. `NEXTDNS_ID` gồm 6 ký tự hex; bỏ trống thì API tải profile trả 503. `ROOT_CA_PATH` tùy chọn là đường dẫn file chứng chỉ CA công khai PEM/DER. Không cung cấp private key. Đường dẫn này chỉ do người triển khai cấu hình, không nhận từ HTTP request.

```powershell
docker compose up -d
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --no-access-log
```

- Trang khách: `http://127.0.0.1:8000/`
- Đăng nhập: `http://127.0.0.1:8000/admin`

Khởi động sẽ kết nối MongoDB, tạo index và cập nhật một tài khoản superadmin theo cấu hình môi trường. Thiếu cấu hình, CA không hợp lệ hoặc database không kết nối được thì ứng dụng không khởi động. Đổi thông tin trong `.env` rồi khởi động lại để áp dụng.

## Tài khoản và phiên

- Mật khẩu: PBKDF2-HMAC-SHA256, 600.000 vòng, salt ngẫu nhiên 16 byte, so sánh constant-time. Tính hash ở thread để không chặn event loop.
- MongoDB `admins`: email, password hash và phiên bản xác thực; không lưu mật khẩu gốc.
- Token: sinh ngẫu nhiên 48 byte (64 ký tự URL-safe); chỉ SHA256 của token được lưu trong `sessions`.
- Phiên mặc định 1 giờ, không tự gia hạn. `SESSION_TTL_SECONDS` cho phép 300–86400 giây. Mỗi request kiểm tra hạn dùng ngay cả khi MongoDB TTL chưa kịp xóa bản ghi.
- Đăng xuất xóa phiên ở server. Chạy lại `python -m app.bootstrap` rồi restart để đổi mật khẩu; hash mới làm mọi phiên cũ mất hiệu lực. Dùng cùng cấu hình trên tất cả instance.
- Frontend lưu token vào `localStorage` theo yêu cầu. JavaScript có thể đọc storage, nên XSS vẫn có thể đánh cắp token. Với hệ thống nhạy cảm hơn, nên chuyển sang cookie `HttpOnly; Secure; SameSite` kèm bảo vệ CSRF. CSP không bảo đảm loại bỏ mọi XSS.
- Không có endpoint đăng ký hoặc tài khoản mặc định công khai. Không lưu token trong URL, DOM hoặc log ứng dụng. Không cấu hình proxy ghi Authorization header hoặc request body đăng nhập.

## API

| Method | Endpoint | Quyền |
|---|---|---|
| GET | `/` | Công khai; không có markup/script admin |
| GET | `/admin` | Màn hình đăng nhập công khai, không có dữ liệu tài khoản |
| POST | `/api/admin/login` | Email/mật khẩu; rate limited |
| GET | `/api/admin/me` | Bearer session |
| POST | `/api/admin/logout` | Bearer session, thu hồi token hiện tại |
| POST | `/admin/add-account` | Bearer session; thêm/cập nhật theo ID |
| GET | `/admin/accounts?skip=0&limit=50` | Bearer session; limit ≤100, skip ≤10000 |
| DELETE | `/admin/accounts/{account_id}` | Bearer session |
| GET | `/profile.mobileconfig` | Công khai |
| GET | `/v1/subscribers/{account_id}` | Công khai theo yêu cầu ban đầu |

Đăng nhập:

```json
{"email":"YOUR_ADMIN_EMAIL","password":"YOUR_ADMIN_PASSWORD"}
```

Thêm/gia hạn, kèm `Authorization: Bearer ACCESS_TOKEN`:

```json
{"locket_id":"example_user_123","expires_date":"2026-12-31T23:59:59Z"}
```

ID là chuỗi 1–128 ký tự ASCII thuộc `[A-Za-z0-9_$:@.\-]`. Không chấp nhận object MongoDB, HTML hay đường dẫn. Thời hạn phải có múi giờ và ở tương lai; lưu/so sánh UTC. MongoDB dùng unique index chống trùng ID. Giao diện hiển thị dữ liệu bằng `textContent`, không dùng `innerHTML`.

API subscriber vẫn cho phép người biết/đoán ID tra cứu trạng thái. Nếu đây là dữ liệu riêng tư, cần bổ sung xác thực danh tính ứng dụng/người dùng trước khi public endpoint đó. Không dùng bí mật admin trong ứng dụng khách.

## Giới hạn và headers

- Request body tối đa 8 KiB kể cả chunked; tối đa 5 giây đọc body.
- 120 request/IP/phút, 10 login/IP/phút và 30 login/phút toàn tiến trình. Trả 429 và `Retry-After`. Bộ nhớ bộ đếm có giới hạn.
- Limiter nằm trong bộ nhớ từng process, reset khi restart. Chạy một worker; nhiều instance cần limiter chung ở reverse proxy/WAF/Redis. Không phải bảo vệ DDoS hoàn chỉnh.
- Không tự đọc `X-Forwarded-For`. Uvicorn chỉ được tin các IP proxy thực tế; cấu hình sai làm tất cả khách bị tính cùng IP hoặc cho phép giả IP.
- CSP nonce riêng mỗi response, không `unsafe-inline`; `nosniff`, `DENY`, `no-referrer`, `no-store`, Permissions-Policy; HSTS chỉ trên HTTPS.
- Host phải nằm trong `ALLOWED_HOSTS`. Không bật CORS vì frontend cùng origin. CORS không thay thế xác thực API.
- Lỗi validation không phản chiếu dữ liệu nhập. Lỗi DB trả 503, lỗi ngoài dự kiến trả JSON 500 chung. Không gửi stack trace tới trình duyệt.

## Profile và Safari

Nút tải là link HTTP trực tiếp với MIME `application/x-apple-aspen-config` và `Content-Disposition: attachment`, không cần Blob, popup hoặc JavaScript. Không dùng font/CDN/Tailwind runtime bên ngoài. CSS hỗ trợ safe area, `100svh` có fallback, input 16px và nút tối thiểu 48px.

CA được kiểm tra kích thước, BasicConstraints CA, thời hạn và không chứa private key. Profile được tạo một lần khi startup. Profile chưa ký; iOS có thể hiển thị chưa xác minh và luôn cần người dùng xác nhận cài đặt. Không tự bật full trust cho CA. Phải kiểm tra trên iPhone/iPad thực tế trước khi phân phối.

## Deploy cloud

Deploy trên Vercel: xem [DEPLOY-VERCEL.md](DEPLOY-VERCEL.md). Đã có native entrypoint `index.py`, `.python-version` và `.vercelignore`; không dùng Docker/localhost MongoDB cho Vercel.

Dockerfile chạy user không phải root, một worker. `.dockerignore` loại `.env`, khóa và chứng chỉ khỏi image. Dùng secret manager của nền tảng để cấp cấu hình; mount chứng chỉ CA ở chế độ chỉ đọc nếu cần.

```sh
docker build -t locket-manager .
docker run --env-file .env -p 127.0.0.1:8000:8000 locket-manager
```

Trong container, `127.0.0.1` là container hiện tại: đặt `MONGODB_URI` tới MongoDB Atlas hoặc hostname MongoDB trong mạng private. `compose.yaml` chỉ phục vụ database local, không phải cấu hình production. Dùng DB auth/TLS, tài khoản DB quyền tối thiểu, backup và không public cổng database.

Cấu hình môi trường production:

```dotenv
ALLOWED_HOSTS=["your-domain.example"]
REQUIRE_HTTPS=true
SESSION_TTL_SECONDS=3600
```

Reverse proxy chấm dứt TLS, chỉ forward đến backend qua mạng private và gửi protocol/client IP chính xác. Cấu hình `FORWARDED_ALLOW_IPS` bằng IP proxy thực tế; không dùng `*` trên backend có thể truy cập trực tiếp. Bật `REQUIRE_HTTPS` chỉ sau khi xác nhận FastAPI nhận đúng scheme HTTPS. Không chạy `--reload` trên production. Thêm rate limit chung, giới hạn body/timeout và lọc log ở edge trước khi scale.

## Kiểm thử và mã nguồn để copy

```powershell
pip install -r requirements-dev.txt
python -m pytest -q
```

Tests dùng MongoDB giả cho request HTTP và startup: login thành công/thất bại, token giả/hết hạn/thu hồi, đổi hash, mọi route admin, injection/XSS input, expiry UTC, body/chunked, rate limit, Host, HTTPS/HSTS, CSP nonce, lỗi DB và TTL index. Chúng không chứng minh kết nối hoặc độ bền dữ liệu của MongoDB thật.

`SOURCE.md` chứa nguyên văn các file để copy; `source-code.zip` chứa mã nguồn không kèm `.env`, `.venv` hoặc dữ liệu runtime.

Tham khảo: [OWASP Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html), [OWASP HTML5 Storage](https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html), [Starlette Middleware](https://starlette.dev/middleware/), [Apple DNSSettings](https://developer.apple.com/documentation/devicemanagement/dnssettings).
