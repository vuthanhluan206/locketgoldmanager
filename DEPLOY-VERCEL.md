# Deploy FastAPI lên Vercel

## Cập nhật: lỗi 400 và upload proxy

Log ngày 04/11/2026 cho thấy domain riêng trả 200 nhưng alias/deployment Vercel trả 400.
Điều này phù hợp với hostname chưa có trong allowlist; để xác nhận, kiểm tra body `Invalid host header`.
Nếu body là `HTTPS is required`, kiểm tra scheme do nền tảng cung cấp, không tin header client tùy ý.

Đặt Environment Variables cho đúng Production/Preview rồi redeploy:

```dotenv
ALLOWED_HOSTS=["locketgold.vuthanhluan.bond","locketgold-premium-luan-eafb.vercel.app"]
ADMIN_PATH=/your-private-admin-path
REQUIRE_HTTPS=true
```

Code tự thêm hostname chính xác từ `VERCEL_URL`, `VERCEL_PROJECT_PRODUCTION_URL`,
`VERCEL_BRANCH_URL` khi `VERCEL=1`. Đây là biến hệ thống của deployment, không phải HTTP headers.
Alias tùy chỉnh vẫn phải khai báo trong `ALLOWED_HOSTS`. Không cho phép `*` hoặc `*.vercel.app`.
`VERCEL_PROJECT_PRODUCTION_URL` có thể là custom domain; trường hợp đó vẫn dùng allowlist tường minh.
Nguồn biến hệ thống: https://vercel.com/docs/environment-variables/system-environment-variables
Khi sử dụng Turnstile trên nhiều hostname, cập nhật cả widget Cloudflare và `TURNSTILE_HOSTNAME`.
Đường dẫn admin cũ trả 404 sau khi đổi `ADMIN_PATH` là hành vi đúng.

FastAPI chấp nhận tối đa **50 MiB** cho `/proxy/…`, **8 KiB** cho các route khác,
kiểm tra cả body không có Content-Length. Vercel Functions có giới hạn payload **4,5 MB**
trước khi request đến ứng dụng; code không vượt được giới hạn này. Proxy upload lớn cần
chạy trên container/VPS với reverse proxy cho phép 50 MiB, hoặc một luồng upload trực tiếp
được dịch vụ đích hỗ trợ. Không thể tự thay luồng upload của client bên ngoài chỉ bằng cấu hình DNS.
Nguồn: https://vercel.com/docs/functions/limitations

Chưa thay đổi Environment Variables hoặc deploy Vercel từ phiên audit này.

Repository này có entrypoint `index.py` theo cơ chế FastAPI native của Vercel và chọn Python 3.12 qua `.python-version`. `vercel.json` chỉ định FastAPI và đặt lại Build Command/Output Directory về mặc định, tránh phục vụ riêng HTML tĩnh. Giữ nguyên backend; Vercel hỗ trợ lifespan. Không chạy Dockerfile, `uvicorn --reload` hoặc `docker compose` trong Vercel Build Command.

`pyproject.toml` khai báo tường minh `[tool.vercel] entrypoint = "app.main:app"`, tránh phụ thuộc vào việc tự dò file import lại app hoặc app được khởi tạo qua factory. Vercel cài runtime dependencies từ `[project].dependencies` trong file này; danh sách đồng bộ với `requirements.txt` cho local và Docker, có test kiểm tra không bị lệch.

## 1. Chuẩn bị database và tài khoản

- Tạo MongoDB Atlas hoặc dùng MongoDB có thể kết nối từ Vercel qua TLS. URI `localhost` của máy bạn không hoạt động trên Vercel.
- Tạo database user quyền `readWrite` chỉ trên database của ứng dụng. Cấu hình Atlas Network Access theo mạng/IP egress của môi trường deploy; không mặc định mở database cho mọi IP. Nếu cần egress cố định/private network, kiểm tra tính năng và gói nền tảng hỗ trợ trước.
- Trước khi public, đổi mật khẩu đã gửi trong hội thoại bằng lệnh local `python -m app.bootstrap`. Mật khẩu được nhập ẩn; chỉ hash có salt được lưu trong `.env`. Lấy giá trị hash từ `.env` để nhập vào Vercel; không đưa file này lên Git.
- Production và Preview nên dùng database/tài khoản DB riêng. Code mới chỉ tạo Admin lần đầu, không ghi đè tài khoản khi startup. Các deployment chạy code cũ vẫn có thể ghi đè: ngừng sử dụng/thu hồi quyền truy cập database của các bản cũ, hoặc chuyển production sang database riêng với thông tin truy cập mới. Đổi code mới không vô hiệu hóa tiến trình cũ đang giữ thông tin đăng nhập DB.

## 2. Import repository

1. Trong Vercel chọn **Add New → Project**, import `vuthanhluan206/locketgoldmanager`.
2. Root Directory là thư mục gốc repository, nơi có `index.py` và `requirements.txt`.
3. Dùng nhận diện framework FastAPI/native và các lệnh build mặc định. Không đặt Output Directory là `web` hoặc `public`, vì HTML phải đi qua FastAPI để có CSP nonce và loại bỏ view admin khỏi trang khách.
4. Xác định production domain trong Project Settings → Domains để điền `ALLOWED_HOSTS`. Không đoán domain nếu tên project bị trùng.

## 3. Environment Variables

Nhập các giá trị dưới đây vào Vercel Project Settings → Environment Variables cho đúng môi trường. Giá trị nhập trong UI là giá trị thực, không bọc thêm dấu nháy shell.

| Tên | Giá trị |
|---|---|
| `MONGODB_URI` | URI Atlas/TLS của database; không dùng localhost |
| `MONGODB_DATABASE` | Tên database, ví dụ `locket_manager` |
| `NEXTDNS_ID` | ID NextDNS của bạn, hiện đang dùng `a8b247` |
| `SUPERADMIN_EMAIL` | Email admin của bạn |
| `SUPERADMIN_PASSWORD_HASH` | Toàn bộ hash từ `.env`, dạng `pbkdf2_sha256$600000$...$...` |
| `ALLOWED_HOSTS` | JSON array chứa domain thực, ví dụ `["your-project.vercel.app","your-domain.example"]` |
| `REQUIRE_HTTPS` | `true` |
| `SESSION_TTL_SECONDS` | `3600` |
| `ROOT_CA_PATH` | Để trống nếu chỉ cấp cấu hình DNS |
| `ROOT_CA_PEM` | Chứng chỉ Root CA công khai dạng PEM, dùng thay cho `ROOT_CA_PATH` |
| `SUBSCRIBER_API_TOKEN` | Tùy chọn: token ngẫu nhiên 32–256 ký tự ASCII để server tin cậy gọi API thuê bao. Bỏ biến nếu không dùng; không nhúng vào app di động |

`SUPERADMIN_EMAIL`/`SUPERADMIN_PASSWORD_HASH` chỉ seed lần đầu khi DB chưa có Admin. Để cập nhật tài khoản đã tồn tại, chuẩn bị `.env` local với URI Atlas và tên database production chính xác, email/hash mong muốn, rồi chạy `python -m app.bootstrap --sync-db`. Lệnh thay đổi tài khoản DB đó và vô hiệu hóa phiên cũ nếu hash đổi. Không dùng URI localhost khi muốn cập nhật tài khoản Vercel. Nếu không đổi mật khẩu, không cần chạy lệnh này khi nâng cấp.

Với preview, thêm đúng hostname preview vào `ALLOWED_HOSTS` cho môi trường đó hoặc chỉ triển khai production ban đầu. Không dùng wildcard để bỏ kiểm tra Host. Một deployment URL ngẫu nhiên không nằm trong allowlist sẽ trả 400, dù production domain vẫn hoạt động.

Để thêm Root CA trên Vercel, đặt `ROOT_CA_PATH` trống và dán toàn bộ chứng chỉ công khai vào giá trị `ROOT_CA_PEM`, từ `-----BEGIN CERTIFICATE-----` đến `-----END CERTIFICATE-----`, giữ các dòng hoặc dùng chuỗi `\n`. Không bọc dấu nháy trong giao diện Vercel. Chọn Production, Save và Redeploy, rồi tải/cài lại profile. Chỉ dùng một chứng chỉ Root CA tự ký còn hạn, không dùng intermediate, chuỗi chứng chỉ hoặc private key. `.vercelignore` cố ý loại file chứng chỉ và khóa; đường dẫn `E:\...` không tồn tại trên cloud. Nếu cả hai biến trống thì profile chỉ có DNS. Việc cài chứng chỉ thủ công không tự bật tin cậy SSL/TLS.

Đánh dấu biến bí mật là sensitive nếu Vercel hỗ trợ trong môi trường tương ứng. Mỗi lần đổi biến môi trường phải redeploy. Không đặt cấu hình bí mật trong frontend hoặc `vercel.json`.

## 4. Bảo vệ và kiểm tra

- Nếu trang chủ hiện cả login và API trả Vercel `NOT_FOUND`: kiểm tra Settings → Build and Deployment, Root Directory phải là gốc repo (`./` hoặc để trống), không phải `web`. Framework là FastAPI; tắt override Output Directory và Build Command, không xuất riêng `web`. Sau đó tạo deployment từ commit mới nhất trên `main`. HTML thô có `__NONCE__` nghĩa là request chưa qua FastAPI.
- Nếu build báo `FASTAPI_ENTRYPOINT_NOT_FOUND`, xác nhận deployment dùng commit có `pyproject.toml` và Root Directory là gốc repository. Không redeploy mã cũ chỉ có cấu hình tự dò.
- Nếu runtime báo `ModuleNotFoundError: No module named 'fastapi'` sau dòng build `Installing required dependencies from pyproject.toml`, phải deploy commit có `[project].dependencies` đầy đủ. File chỉ khai báo `[tool.vercel]` không đủ để cài dependencies khi Vercel chọn pyproject thay requirements.

- Đăng nhập đã có bộ đếm chung MongoDB ngoài limiter từng instance. Dùng thêm Vercel Firewall/WAF theo khả năng gói để lọc lưu lượng trước khi tới function/database. Xác minh IP proxy để giới hạn theo IP chính xác.
- Xác minh HTTPS scheme/IP proxy thực tế; không tùy tiện tin `X-Forwarded-For` từ client. Nếu gặp 400, kiểm tra detail trong JSON và log: phân biệt lỗi Host với `HTTPS is required`; không tắt các kiểm tra một cách mặc định.
- Sau deploy, kiểm tra `/`, `/admin`, đăng nhập, thêm/gia hạn một ID thử, tải profile, đăng xuất và thử gọi lại với token cũ.
- Kiểm tra MongoDB có `admins`, `sessions`, `accounts`, `login_limits` và index TTL trên `sessions.expires_at`, `login_limits.expires_at`.
- Không đưa `.env`, `.venv`, token, password hash hoặc log request vào Git. `.vercelignore` và `.gitignore` đã loại các file runtime/bí mật.

Chưa deploy Vercel bằng tài khoản của bạn trong phiên này. Tài liệu chính thức: [FastAPI on Vercel](https://vercel.com/docs/frameworks/backend/fastapi), [Python runtime](https://vercel.com/docs/functions/runtimes/python).
