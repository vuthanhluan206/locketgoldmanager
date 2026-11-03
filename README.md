# Locket Gold Manager

## Bảo vệ admin bằng IP và Cloudflare Turnstile

- Giữ giới hạn hiện có: 120 request/IP/phút; đăng nhập 10 lần/IP/phút và 30 lần/phút toàn hệ thống. API admin có thêm giới hạn 60 request/IP/phút, dùng bộ đếm MongoDB chung giữa các instance. Vượt giới hạn trả HTTP 429 và `Retry-After: 60`.
- Tạo widget **Managed** trong Cloudflare Dashboard → Turnstile, khai báo hostname thực tế của trang admin. Đặt các biến sau trong `.env` hoặc Environment Variables của Vercel, rồi khởi động/deploy lại:

```dotenv
TURNSTILE_SITE_KEY=your_public_site_key
TURNSTILE_SECRET_KEY=your_private_secret_key
TURNSTILE_HOSTNAME=locketgold.vuthanhluan.bond,locketgold-premium.vercel.app
```

`TURNSTILE_HOSTNAME` chứa một hoặc nhiều tên miền cách nhau bằng dấu phẩy, không có `https://`, cổng hay đường dẫn. Thêm tất cả tên miền này vào cùng widget Turnstile trong Cloudflare; cả hai dùng chung Site Key và Secret Key. Secret Key chỉ nằm ở backend. Khi bật, mọi đăng nhập phải có token hợp lệ; backend kiểm tra `success`, hostname thuộc danh sách cho phép và action `admin-login` trước khi kiểm tra mật khẩu. Token lỗi/hết hạn trả 403; lỗi kết nối Cloudflare hoặc thiếu cấu hình trả 503. Bỏ trống cả hai key sẽ giữ cách đăng nhập hiện tại; cần điền đủ ba biến để bật bảo vệ.

Mặc định giới hạn theo IP kết nối do server cung cấp, không tin header do khách gửi. Chỉ cấu hình `TRUSTED_PROXY_CIDRS` khi origin được giới hạn truy cập từ proxy tin cậy và proxy đó luôn ghi đè `CF-Connecting-IP`:

```dotenv
TRUSTED_PROXY_CIDRS=["YOUR_TRUSTED_PROXY_CIDR"]
```

Dùng dải IP chính thức của Cloudflare nếu origin nhận kết nối trực tiếp từ Cloudflare; giữ danh sách cập nhật. Không dùng `0.0.0.0/0` hoặc `::/0`. Với Uvicorn trực tiếp sau Cloudflare, dùng `--no-proxy-headers` khi chọn cơ chế này để giữ đúng IP peer cho bước kiểm tra proxy. Nếu triển khai Vercel hoặc qua nhiều proxy, phải xác minh cách nền tảng cung cấp IP và chặn truy cập vòng qua proxy trước khi bật tin header. Turnstile dùng được cả khi tên miền không proxy qua Cloudflare.

Giới hạn tổng request ở middleware vẫn theo process; Turnstile bảo vệ đăng nhập và không thay thế giới hạn lưu lượng tại edge. Nếu dùng Cloudflare WAF, áp dụng rule cho đường dẫn trang admin hiện tại và `/api/admin/*`, `/admin/*`; tránh áp challenge lên API subscriber vì ứng dụng không giải được challenge trình duyệt.

Tài liệu: [Siteverify](https://developers.cloudflare.com/turnstile/get-started/server-side-validation/), [CSP cho Turnstile](https://developers.cloudflare.com/turnstile/reference/content-security-policy/).

FastAPI + MongoDB. Một file `web/index.html` chứa trang tải cấu hình và giao diện đăng nhập/quản trị. Server loại bỏ phần admin khỏi phản hồi `/`. `/admin` hiển thị màn hình đăng nhập; tất cả dữ liệu/thao tác admin yêu cầu phiên Bearer được xác minh bằng MongoDB. Không còn token tĩnh hoặc token trong URL.

Đây là hệ thống cấp phép độc lập cho ứng dụng bạn kiểm soát. DNS và CA không tự kích hoạt Gold trong Locket chính thức; JSON subscriber là hợp đồng nội bộ có dạng tương tự RevenueCat, không cam kết tương thích SDK RevenueCat.

## Chạy local (Python 3.12+, Docker Desktop đang chạy)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python -m app.bootstrap
```

Không ghi đè `.env` đã có nếu muốn giữ cấu hình. `app.bootstrap` hỏi email và mật khẩu hai lần (ẩn khi nhập), chỉ lưu email và hash có salt vào `.env`. Nhập tài khoản bạn muốn sử dụng; không có email/mật khẩu quản trị mặc định trong source. Bản local trong phiên làm việc này đã được cấu hình bằng tài khoản bạn yêu cầu.

Điền `MONGODB_URI` và `NEXTDNS_ID` của bạn trong `.env`. `NEXTDNS_ID` gồm 6 ký tự hex; bỏ trống thì API tải profile trả 503. Để profile chứa cả DNS và Root CA, cấu hình **một** trong hai biến: `ROOT_CA_PATH` (file chứng chỉ công khai PEM/DER có trên server) hoặc `ROOT_CA_PEM` (nội dung PEM, hỗ trợ xuống dòng thật hoặc chuỗi `\n`). Không cung cấp private key. Cấu hình chỉ do người triển khai đặt, không nhận từ HTTP request. Nếu bỏ trống cả hai biến, profile vẫn chỉ chứa DNS.

Profile xuất XML plist với `PayloadScope=System`, UUID riêng cho profile và từng payload; chứng chỉ được chuẩn hóa thành DER, kiểm tra tự ký, CA và thời hạn. XML này **chưa được ký CMS**; iOS có thể hiển thị “Not Signed”. Không có bảo đảm cài thành công trên mọi thiết bị/chính sách MDM. Sau khi cài thủ công, người dùng vẫn phải bật tin cậy tại **Cài đặt → Cài đặt chung → Giới thiệu → Cài đặt tin cậy chứng chỉ**. DNS không ép chuyển tiếp HTTPS và profile không tự cấp quyền Locket Gold.

```powershell
docker compose up -d
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --no-access-log
```

- Trang khách: `http://127.0.0.1:8000/`
- Đăng nhập: `http://127.0.0.1:8000/admin`

Khởi động sẽ kết nối MongoDB, tạo index và chỉ tạo superadmin từ môi trường khi tài khoản chưa tồn tại. Tài khoản trong MongoDB là nguồn xác thực sau lần tạo đầu; restart không đổi email/mật khẩu. Thiếu cấu hình bắt buộc hoặc DB không kết nối được thì startup thất bại. CA không hợp lệ chỉ vô hiệu hóa tải profile (503); Admin và API thuê bao vẫn hoạt động, log có `PROFILE_CONFIG_INVALID`.

## Tài khoản và phiên

- Mật khẩu: PBKDF2-HMAC-SHA256, 600.000 vòng, salt ngẫu nhiên 16 byte, so sánh constant-time. Tính hash ở thread để không chặn event loop.
- MongoDB `admins`: email, password hash và phiên bản xác thực; không lưu mật khẩu gốc.
- Token: sinh ngẫu nhiên 48 byte (64 ký tự URL-safe); chỉ SHA256 của token được lưu trong `sessions`.
- Phiên mặc định 1 giờ, không tự gia hạn. `SESSION_TTL_SECONDS` cho phép 300–86400 giây. Mỗi request kiểm tra hạn dùng ngay cả khi MongoDB TTL chưa kịp xóa bản ghi.
- Đăng xuất xóa phiên ở server. Để đổi mật khẩu: chạy `python -m app.bootstrap` để cập nhật `.env`, rồi `python -m app.bootstrap --sync-db` để áp dụng có chủ đích vào MongoDB đang cấu hình. Lệnh này thay email/hash và vô hiệu hóa phiên dùng hash cũ. Đổi biến môi trường rồi restart không ghi đè tài khoản đã có. `--check` chỉ xác minh mật khẩu với cấu hình local, không kiểm tra Vercel hay tài khoản DB.
- Frontend lưu token vào `localStorage` theo yêu cầu. JavaScript có thể đọc storage, nên XSS vẫn có thể đánh cắp token. Với hệ thống nhạy cảm hơn, nên chuyển sang cookie `HttpOnly; Secure; SameSite` kèm bảo vệ CSRF. CSP không bảo đảm loại bỏ mọi XSS.
- Không có endpoint đăng ký hoặc tài khoản mặc định công khai. Không lưu token trong URL, DOM hoặc log ứng dụng. Không cấu hình proxy ghi Authorization header hoặc request body đăng nhập.

## API

API thuê bao không lưu lịch sử mua hàng. Các trường `first_seen`, `purchase_date` và `original_purchase_date` trả `null` khi không có dữ liệu, thay vì tạo ngày mua bằng thời gian gọi API. `request_date` và `request_date_ms` vẫn là thời gian phản hồi; trạng thái Gold và ngày hết hạn không đổi. Đây là hợp đồng nội bộ, chưa xác minh tính tương thích với ứng dụng Locket chính thức.

Nút tải trên trang chủ gọi trực tiếp `/profile.mobileconfig`, dùng `NEXTDNS_ID` và CA được server kiểm tra. Không còn DNS hoặc chứng chỉ nhúng trong HTML. Nếu thiếu cấu hình, endpoint trả 503; profile đã cài trên thiết bị không tự cập nhật.

API subscriber luôn yêu cầu token server hợp lệ hoặc phiên Admin còn hạn, kể cả khi không đặt `SUBSCRIBER_API_TOKEN`. Các client trước đây gọi ẩn danh sẽ nhận 401 và cần tích hợp xác thực qua server tin cậy. Bản sửa không di chuyển, ghi lại hoặc xóa dữ liệu tài khoản hiện có.

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
| GET | `/v1/subscribers/{account_id}` | Bearer phiên Admin hoặc token riêng cho server tin cậy |

Đăng nhập:

```json
{"email":"YOUR_ADMIN_EMAIL","password":"YOUR_ADMIN_PASSWORD"}
```

Thêm/gia hạn, kèm `Authorization: Bearer ACCESS_TOKEN`:

```json
{"locket_id":"example_user_123","expires_date":"2026-12-31T23:59:59Z"}
```

ID là chuỗi 1–128 ký tự ASCII thuộc `[A-Za-z0-9_$:@.\-]`. Không chấp nhận object MongoDB, HTML hay đường dẫn. Thời hạn phải có múi giờ và ở tương lai; lưu/so sánh UTC. MongoDB dùng unique index chống trùng ID. Giao diện hiển thị dữ liệu bằng `textContent`, không dùng `innerHTML`.

API subscriber từ chối tra cứu ẩn danh (401). Server tích hợp có thể dùng `Authorization: Bearer SUBSCRIBER_API_TOKEN` khi đã cấu hình biến tùy chọn này bằng token ngẫu nhiên 32–256 ký tự ASCII, không có khoảng trắng. Không đặt biến rỗng; bỏ biến nếu không dùng. Token này chỉ dành cho server tin cậy và có quyền tra cứu mọi ID, không phải token cho người dùng cuối. Không nhúng token server/Admin vào ứng dụng di động. Phiên Admin cũng có thể dùng để kiểm tra API.

Luồng tích hợp ứng dụng do bạn kiểm soát: ứng dụng đăng nhập hệ thống của bạn → server xác minh danh tính và lấy ID nội bộ từ phiên → server gọi API thuê bao bằng token riêng → trả trạng thái được phép cho chính người dùng đó. Chưa có mã nguồn client/nhà cung cấp danh tính trong repo; không thể tự suy ra ID từ link chia sẻ hoặc bật Gold trong Locket chính thức bằng DNS/CA. Không coi username trong link là ID nội bộ nếu chưa xác minh.

## Giới hạn và headers

- Request body tối đa 8 KiB kể cả chunked; tối đa 5 giây đọc body.
- 120 request/IP/phút, 10 login/IP/phút và 30 login/phút toàn tiến trình. Trả 429 và `Retry-After`. Bộ nhớ bộ đếm có giới hạn.
- Middleware giới hạn request theo từng process. Riêng đăng nhập có thêm bộ đếm nguyên tử dùng chung trong MongoDB `login_limits` (10/IP, 30/toàn hệ thống mỗi cửa sổ phút; TTL dọn dữ liệu). Bộ đếm dùng chung áp dụng cho request đúng schema trước khi xác minh mật khẩu; middleware vẫn chặn cả request sai schema. Giới hạn IP phụ thuộc proxy cung cấp IP chính xác; bảo vệ lưu lượng lớn cần WAF/edge, không phải cơ chế chống DDoS hoàn chỉnh.
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

Kiểm thử đơn vị dùng MongoDB giả. Kiểm thử tích hợp tùy chọn dùng MongoDB thật, tạo database riêng tên `locket_test_<uuid>`, rồi xóa đúng database test trong phần dọn dẹp; không dùng collections sản xuất. Kiểm tra ghi/đọc/gia hạn/hết hạn/xóa tài khoản, đổi mật khẩu thu hồi phiên, đăng xuất và restart bằng cấu hình cũ không ghi đè Admin.

```powershell
$env:TEST_MONGODB_URI='mongodb://127.0.0.1:27017'
python -m pytest -q
```

Để trống/bỏ `TEST_MONGODB_URI` thì kiểm thử tích hợp được bỏ qua. Kết quả local không chứng minh kết nối Atlas, cấu hình Vercel hay cài profile trên iPhone.

`SOURCE.md` chứa nguyên văn các file để copy; `source-code.zip` chứa mã nguồn không kèm `.env`, `.venv` hoặc dữ liệu runtime.

Tham khảo: [OWASP Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html), [OWASP HTML5 Storage](https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html), [Starlette Middleware](https://starlette.dev/middleware/), [Apple DNSSettings](https://developer.apple.com/documentation/devicemanagement/dnssettings).



