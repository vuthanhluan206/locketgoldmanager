# Project source

Each section contains the file path and its complete text content. Secrets, binary assets, Git metadata, virtual environments and caches are excluded.

## .dockerignore

```text
.git
.env
.env.*
.venv
__pycache__
.pytest_cache
*.pem
*.key
*.cer
*.der
*.p12
*.pfx
*.zip
*.log
tests
SOURCE.md
```

## .env.example

```text
MONGODB_URI=mongodb://127.0.0.1:27017
MONGODB_DATABASE=locket_manager
NEXTDNS_ID=
ROOT_CA_PATH=
# Alternative to ROOT_CA_PATH: a single public root CA certificate in PEM format.
ROOT_CA_PEM=
SUPERADMIN_EMAIL=admin@example.com
# Run python -m app.bootstrap to set the real email and salted password hash in .env.
SUPERADMIN_PASSWORD_HASH=
# Custom secret path for the admin login page (e.g., /admin-secret-path).
ADMIN_PATH=/admin
ALLOWED_HOSTS=["localhost","127.0.0.1","[::1]"]
REQUIRE_HTTPS=false
SESSION_TTL_SECONDS=3600
# Set all three values to enable Cloudflare Turnstile on admin login.
TURNSTILE_SITE_KEY=
TURNSTILE_SECRET_KEY=
# One hostname or multiple hostnames separated by commas; no URL paths.
TURNSTILE_HOSTNAME=
# Only direct, trusted proxies which overwrite CF-Connecting-IP. Never use 0.0.0.0/0.
TRUSTED_PROXY_CIDRS=[]
# Optional: configure a separate random token (32+ ASCII characters) for trusted
# server-to-server subscriber checks. Never embed this or admin tokens in a mobile app.
# SUBSCRIBER_API_TOKEN=
```

## .gitignore

```text
.env
.env.*
!.env.example
.venv/
__pycache__/
.pytest_cache/
*.pem
*.key
*.cer
*.der
*.p12
*.pfx
*.log
*.zip
SOURCE.md
rootCA.key
generate_root_ca.py
```

## .python-version

```text
3.12
```

## .vercelignore

```text
.git
.env
.env.*
.venv
.pytest_cache
**/__pycache__/**
tests
SOURCE.md
source-code.zip
*.pem
*.key
*.cer
*.der
*.p12
*.pfx
*.log
generate_root_ca.py
```

## CODE-AUDIT.md

```markdown
# Audit Locket Management & Proxy — 04/11/2026

Phạm vi: FastAPI, cấu hình, middleware, proxy HTTP, MongoDB, auth/password/session,
Turnstile, routers quản trị/subscriber, profile, frontend, dependencies và pytest.
Giả định: một worker sau TLS proxy tin cậy; nhiều instance cần giới hạn lưu lượng tại edge.
Đây là kiểm tra source và test local, không phải chứng nhận hệ thống production.

## Phát hiện và sửa

| Mức | Trường hợp lỗi cụ thể | Sửa |
|---|---|---|
| Cao | urllib tự theo redirect; Authorization/Host có thể đi đến đích khác | Tắt redirect trong transport; trả 502 cho upstream 3xx; upstream Host luôn `api.locketcamera.com` |
| Cao | Admin session/service token bị gửi nhầm vào proxy có thể lộ cho upstream | Từ chối token service đã cấu hình và session đã lưu trong MongoDB trước khi gọi upstream; bỏ cookie và forwarded headers |
| Trung bình | Domain Vercel trả 400 khi chỉ domain riêng nằm trong allowlist | Thêm chính xác hostname từ biến hệ thống Vercel; giữ allowlist cho alias và domain riêng; không wildcard |
| Trung bình | `testserver` luôn được chấp nhận cả trên production | Bỏ tự thêm hostname test; test khai báo rõ hostname riêng |
| Trung bình | Header `Content-Type` khác kiểu viết hoa làm bỏ qua JSON; bỏ Content-Encoding nhưng vẫn giữ bytes gzip làm hỏng response | Đọc headers không phân biệt hoa thường; yêu cầu identity; nếu upstream vẫn nén thì giữ bytes và encoding, không tiêm JSON |
| Trung bình | Lỗi MongoDB bị nuốt, làm trạng thái Gold/viewers sai và không thể chẩn đoán | Để handler DB trả 503, không trả trạng thái giả khi lỗi DB; không tiết lộ exception |
| Trung bình | Timestamp BSON datetime trong viewers khiến JSON serialization thất bại và bị nuốt lỗi | Dùng jsonable_encoder; không tự tạo timestamp quá khứ giả |
| Trung bình | Ghi đè toàn bộ entitlements/subscriptions làm mất quyền khác | Chỉ cập nhật/xóa `Gold` và product Gold do hệ thống quản lý; giữ các mục khác |
| Trung bình | Token bị coi là locket_id khi không tìm thấy ID | Bỏ fallback token; ưu tiên original_app_user_id từ phản hồi upstream thành công |
| Trung bình | `/proxy/install` tự tạo lại profile sau khi startup đã đánh dấu CA lỗi | Dùng chung endpoint profile và cùng cache; lỗi cấu hình trả 503 nhất quán |
| Trung bình | `/openapi.json` công khai sơ đồ API dù đã tắt docs | Tắt OpenAPI endpoint; không xuất đường dẫn admin cấu hình trong public HTML |
| Trung bình | Cấu hình pytest dùng cố định `.pytest_tmp` gây WinError 5 trên máy hiện tại | Dùng cơ chế thư mục tạm mặc định của pytest; giữ pythonpath và testpaths |

## Các chức năng được giữ

- PBKDF2-SHA256 600.000 vòng, salt ngẫu nhiên; bearer session chỉ lưu SHA256 trong DB,
  kiểm tra expiry/auth_version, logout thu hồi phiên.
- Turnstile kiểm tra server-side success/hostname/action; giới hạn login dùng MongoDB chung.
- Admin và proxy dùng cùng `app.state.accounts`, trường `locket_id` và `expires_date` UTC.
  Thêm/gia hạn/xóa từ admin tác động ngay tới lần tra cứu proxy tiếp theo.
- Viewers dùng `viewers_history`, tra theo token upstream và sắp xếp viewed_at giảm dần;
  thêm index `(token, viewed_at)` hỗ trợ query. Không tự tạo viewers nếu DB không có dữ liệu.
- XML plist profile, MIME `application/x-apple-aspen-config`, Content-Disposition attachment,
  kiểm tra Root CA và cache lúc startup. Hai URL tải dùng chung bytes.
- CORS không bật: giao diện cùng origin không cần CORS. Không cho wildcard credentials.
  Client native không bị CORS của trình duyệt hạn chế.
- Body: proxy 50 MiB/60 giây, route khác 8 KiB/5 giây; kiểm tra cả chunked.
  Transport chạy trong thread, không chặn event loop; response upstream có giới hạn 50 MiB.

## Giới hạn và việc chưa xác minh

- Vercel Function giới hạn payload 4,5 MB. Mức 50 MiB tại app không thay đổi giới hạn nền tảng.
  Xem https://vercel.com/docs/functions/limitations. Chưa thay đổi cloud environment hoặc deploy.
- Upstream được cố định và chỉ sửa JSON sau phản hồi 2xx có bearer upstream. Điều này chưa
  chứng minh upstream thực sự ràng buộc ID trong URL với token; cần hợp đồng/kiểm thử được
  chủ dịch vụ cho phép. Test local không chứng minh tương thích app Locket/RevenueCat thật.
- Profile DNS/CA không tự thực hiện interception TLS, không tự bật full trust hoặc bỏ certificate pinning.
  Chưa kiểm tra trên iPhone/Safari; profile chưa ký CMS.
- `viewers_history.token` vẫn giữ schema token gốc để không phá hệ thống ghi dữ liệu hiện tại.
  Repo chưa có producer ghi viewers; cần triển khai đổi cả producer/consumer nếu chuyển sang token hash.
  Không ghi token, ID cá nhân hay đường dẫn admin vào log ứng dụng mới.
- Frontend vẫn lưu bearer token trong localStorage theo thiết kế hiện tại; XSS có thể đọc token.
  Nonce CSP, textContent và loại inline handlers giúp giảm rủi ro, không loại bỏ hoàn toàn.
- Tổng limiter vẫn theo process; login/admin có bộ đếm DB chung. TLS, IP proxy thực tế và WAF
  phải được cấu hình tại deployment. Không tin X-Forwarded-* do client gửi để bỏ kiểm tra HTTPS.
- Proxy buffer body/response trong RAM; upload đồng thời lớn cần giới hạn concurrency tại reverse proxy.
  Giới hạn đọc urllib là timeout socket, không phải thời hạn tổng tuyệt đối cho upstream chậm nhỏ giọt.
- Chưa kiểm tra MongoDB thật, lịch sử Git, dependency CVE, load test hay production credentials.

## Kiểm chứng

Chạy `python -m pytest -q` từ thư mục gốc. Test không gọi API Locket thật.
Kết quả: **68 passed, 1 skipped**, một cảnh báo deprecation httpx/Starlette.
Test proxy dùng transport giả cho status/compression/timeout và MongoDB giả cho expiry/viewers;
một HTTP server local xác minh urllib không đi theo redirect. Upload kiểm tra đúng 50 MiB,
50 MiB + 1 byte dạng chunked, và admin 8 KiB + 1 byte. Test host cho phép đúng hostname deployment,
chặn hostname khác và hậu tố giả. Test MongoDB thật chỉ chạy khi đặt TEST_MONGODB_URI.
```

## DEPLOY-VERCEL.md

````markdown
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
````

## Dockerfile

```text
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home appuser
COPY app ./app
COPY web ./web
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
```

## README.md

````markdown
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



````

## SECURITY-AUDIT.md

```markdown
# Kết quả rà soát và vá bảo mật

Phạm vi: source FastAPI, vòng đời MongoDB, auth, các API quản trị/subscriber/profile, HTML/JS và cấu hình đóng gói. Giả định triển khai một worker sau HTTPS reverse proxy. Đây là rà soát source và kiểm thử local, không phải chứng nhận không còn lỗ hổng.

| Mức | Phát hiện trước sửa | Tác động cụ thể | Bản vá |
|---|---|---|---|
| Cao | Token thật trong `app/config.py` và `.env.example` | Người đọc repo có toàn quyền admin | Bỏ token tĩnh, làm sạch file mẫu; phiên chỉ được cấp sau login tài khoản MongoDB |
| Cao | Login qua `?admin=TOKEN` | Token có thể vào log/history trước khi JS xóa | Vô hiệu URL token, login POST bằng email/mật khẩu; không lưu mật khẩu gốc |
| Cao | Không có expiry/revocation cho token tĩnh | Token rò rỉ có hiệu lực vô thời hạn | Token ngẫu nhiên 48 byte, lưu hash ở DB, expiry, TTL, logout và auth version |
| Trung bình | Không rate limit/body limit | Spam login hoặc payload lớn tiêu tốn CPU/RAM | 8 KiB, timeout body, giới hạn IP và tổng login; bộ đếm có giới hạn bộ nhớ |
| Trung bình | CSP `unsafe-inline` | Nếu phát sinh HTML injection, script inline có thể chạy | Nonce từng response; bỏ inline event attributes, không CDN |
| Trung bình | Chưa kiểm tra Host hoặc enforce HTTPS | Host giả được chấp nhận; production có thể vô tình phục vụ HTTP | Allowlist host; REQUIRE_HTTPS; HSTS chỉ trên HTTPS |
| Trung bình | CA đọc/parse mỗi download, PayloadIdentifier chứa khoảng trắng | CA sai gây lỗi lúc khách tải; định danh profile không sạch | Kiểm tra CA lúc startup, giới hạn file, sửa identifier, cache profile |

Các điểm đã đúng và được giữ: dependency bảo vệ toàn router admin, ID dạng chuỗi được validation trước khi tạo filter MongoDB, không nhận raw query, ngày có timezone, unique index, dùng `textContent`. Không tìm thấy đường dẫn HTTP cho phép đọc file tùy ý; chỉ dùng tên template cố định và CA path từ cấu hình server.

## Thay đổi hợp đồng

- `/admin` là trang login công khai, không trả dữ liệu MongoDB.
- `/api/admin/login` là API công khai có rate limit. `/api/admin/me`, `/api/admin/logout` và mọi endpoint dữ liệu `/admin/*` yêu cầu session hợp lệ trong MongoDB.
- Token URL và token tĩnh cũ không còn được chấp nhận.
- Bootstrap hash lấy từ môi trường, đồng bộ tài khoản cố định vào MongoDB khi startup. Đổi hash rồi restart làm token phiên cũ không còn hợp lệ.
- Trang khách chỉ có một thẻ và link tải trực tiếp, không gửi script/markup admin. Cả hai view nằm trong một file HTML.

## Giới hạn còn lại trước production

1. `localStorage` là yêu cầu người dùng: XSS có thể đọc token. Cookie HttpOnly + CSRF phù hợp hơn khi ưu tiên an toàn phiên tối đa.
2. Limiter từng process không chống brute-force phân tán trên nhiều replica hoặc DDoS. Cần shared limiter/edge, IP proxy đúng, TLS và mạng DB private.
3. Subscriber API đang công khai theo hợp đồng ban đầu, có thể bị dò ID. Cần xác thực người gọi nếu trạng thái thuê bao được coi là riêng tư.
4. Mật khẩu đã gửi trong hội thoại cần được thay trước triển khai internet. Chạy bootstrap với mật khẩu mới; không đưa hash `.env` lên Git.
5. Đã kiểm tra startup, login tài khoản được yêu cầu, session auth, danh sách, tải profile và logout với MongoDB local thật. Chưa kiểm tra certificate trust chain, cài profile trên Safari/iPhone và cấu hình HTTPS proxy thực tế.
6. Chưa quét CVE của dependency hoặc kiểm tra toàn bộ lịch sử Git. Nếu từng commit bí mật, phải thu hồi bí mật; xóa khỏi phiên bản hiện tại không xóa lịch sử.

## Xác minh đã thực hiện

- 16 tests tự động đã đạt, bao gồm các trường hợp tham số hóa cho toàn bộ route admin; database giả cho kiểm thử HTTP và startup.
- Kiểm tra cú pháp JavaScript của file HTML đã đạt bằng Node.js.
- Smoke test MongoDB thật đã đạt: startup/index/bootstrap, email/mật khẩu yêu cầu, Bearer auth, danh sách tài khoản, profile và đăng xuất; token sau logout trả 401. Không in token hoặc dữ liệu khách hàng.
- Chưa kiểm tra UI bằng trình duyệt hoặc thiết bị iOS thật; Docker image chưa build trong phiên này.
```

## app/__init__.py

```python

```

## app/auth.py

```python
import asyncio
import logging
import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from pymongo import ReturnDocument

from .config import get_settings
from .passwords import verify_password
from .security import require_admin, token_digest
from .middleware import client_ip
from .turnstile import verify_turnstile

router = APIRouter(prefix='/api/admin', tags=['Authentication'])
logger = logging.getLogger(__name__)


async def enforce_login_limit(request: Request):
    now = datetime.now(timezone.utc)
    window = int(now.timestamp()) // 60
    ip_key = hashlib.sha256(client_ip(request.scope).encode('utf-8')).hexdigest()
    # Shared counters survive serverless cold starts; local middleware also limits malformed requests.
    for key, limit in [(ip_key, 10), ('global', 30)]:
        bucket = await request.app.state.login_limits.find_one_and_update(
            {'_id': f'{window}:{key}'},
            {'$inc': {'count': 1}, '$setOnInsert': {'expires_at': now + timedelta(minutes=2)}},
            upsert=True, return_document=ReturnDocument.AFTER,
        )
        if bucket['count'] > limit:
            raise HTTPException(429, 'Too many login attempts', headers={'Retry-After': '60'})


class LoginInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email: str = Field(min_length=3, max_length=254, pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
    password: SecretStr = Field(min_length=1, max_length=256)
    turnstile_token: SecretStr = Field(default=SecretStr(''), max_length=2048)

    @field_validator('email')
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()


@router.post('/login')
async def login(data: LoginInput, request: Request):
    await enforce_login_limit(request)
    await verify_turnstile(data.turnstile_token.get_secret_value())
    settings = get_settings()
    admin = await request.app.state.admins.find_one({'_id': 'superadmin'})
    encoded = admin['password_hash'] if admin else settings.superadmin_password_hash.get_secret_value()
    # Also perform an expensive verification for unknown emails; keep the event loop responsive.
    valid = await asyncio.to_thread(verify_password, data.password.get_secret_value(), encoded)
    if not valid or admin is None or data.email != admin['email']:
        logger.warning(
            'ADMIN_LOGIN_REJECTED: credentials rejected',
        )
        raise HTTPException(401, 'Email hoặc mật khẩu không đúng')
    token = secrets.token_urlsafe(48)
    expires = datetime.now(timezone.utc) + timedelta(seconds=settings.session_ttl_seconds)
    await request.app.state.sessions.insert_one({
        '_id': token_digest(token), 'admin_id': admin['_id'],
        'auth_version': admin['auth_version'], 'expires_at': expires,
    })
    return {'access_token': token, 'token_type': 'bearer', 'expires_at': expires}


@router.get('/me')
async def me(admin: Annotated[dict, Depends(require_admin)]):
    return {'email': admin['email']}


@router.post('/logout', status_code=204)
async def logout(request: Request, admin: Annotated[dict, Depends(require_admin)]):
    await request.app.state.sessions.delete_one({'_id': admin['session_id']})
    return Response(status_code=204)
```

## app/bootstrap.py

```python
"""Run python -m app.bootstrap to configure an admin without saving a plaintext password."""
from getpass import getpass
from pathlib import Path
import re
import sys
import asyncio

from .passwords import hash_password, verify_password


async def sync_admin(settings):
    from pymongo import AsyncMongoClient
    from .database import admin_document

    client = AsyncMongoClient(settings.mongodb_uri.get_secret_value(),
                              serverSelectionTimeoutMS=5000, timeoutMS=10000)
    try:
        await client[settings.mongodb_database].admins.update_one(
            {'_id': 'superadmin'}, {'$set': admin_document(settings)}, upsert=True,
        )
    finally:
        await client.close()


def update_env(values: dict[str, str]):
    path = Path('.env')
    text = path.read_text(encoding='utf-8-sig') if path.exists() else ''
    for name, value in values.items():
        pattern = rf'(?m)^\s*{name}\s*=.*$'
        line = f"{name}='{value}'"
        text = re.sub(pattern, lambda match: line, text) if re.search(pattern, text) else text.rstrip('\n') + '\n' + line + '\n'
    text = re.sub(r'(?m)^\s*ADMIN_TOKEN\s*=.*\n?', '', text)
    path.write_text(text, encoding='utf-8')


if __name__ == '__main__':
    if sys.argv[1:] == ['--sync-db']:
        from .config import get_settings

        try:
            asyncio.run(sync_admin(get_settings()))
        except Exception as exc:
            raise SystemExit('Admin update failed: ' + type(exc).__name__) from None
        print('Updated admin in the configured MongoDB. Previous password sessions are invalidated.')
        raise SystemExit(0)
    if sys.argv[1:] == ['--check']:
        from .config import get_settings

        settings = get_settings()
        print('Configured email: ' + settings.superadmin_email)
        valid = verify_password(
            getpass('Password to verify (hidden): '),
            settings.superadmin_password_hash.get_secret_value(),
        )
        print('Password matches local configuration.' if valid else 'Password does NOT match local configuration.')
        raise SystemExit(0 if valid else 1)
    email = input('Superadmin email: ').strip().lower()
    if not re.fullmatch(r"[A-Za-z0-9._+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", email):
        raise SystemExit('Invalid email')
    password = getpass('Superadmin password (12+ characters): ')
    if password != getpass('Confirm password: '):
        raise SystemExit('Passwords do not match')
    update_env({'SUPERADMIN_EMAIL': email, 'SUPERADMIN_PASSWORD_HASH': hash_password(password)})
    print('Updated .env. For an existing database, run python -m app.bootstrap --sync-db to apply credentials.')
```

## app/config.py

```python
import json
import re
from functools import lru_cache
from ipaddress import ip_network
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from .passwords import validate_password_hash


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore', hide_input_in_errors=True)
    superadmin_email: str = Field(min_length=3, max_length=254, pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
    superadmin_password_hash: SecretStr
    mongodb_uri: SecretStr
    mongodb_database: str = 'locket_manager'
    nextdns_id: str = Field(default='', pattern=r'^([a-fA-F0-9]{6})?$')
    root_ca_path: str = ''
    root_ca_pem: str = Field(default='', max_length=65536, repr=False)
    admin_path: str = Field(default='/admin', pattern=r'^/[A-Za-z0-9_-]{1,64}$')
    allowed_hosts: list[str] = ['localhost', '127.0.0.1', '[::1]']
    vercel: str = ''
    vercel_url: str = ''
    vercel_project_production_url: str = ''
    vercel_branch_url: str = ''
    require_https: bool = False
    session_ttl_seconds: int = Field(default=3600, ge=300, le=86400)
    subscriber_api_token: SecretStr | None = None
    turnstile_site_key: str = Field(default='', pattern=r'^[A-Za-z0-9_-]*$', max_length=256)
    turnstile_secret_key: SecretStr = SecretStr('')
    turnstile_hostname: str = ''
    trusted_proxy_cidrs: list[str] = []

    @field_validator('admin_path')
    @classmethod
    def validate_admin_path(cls, value: str) -> str:
        if value in {'/proxy', '/api', '/v1', '/favicon', '/robots'}:
            raise ValueError('ADMIN_PATH conflicts with an application route')
        return value

    @model_validator(mode='after')
    def deployment_hosts(self):
        if self.vercel == '1':
            for host in (self.vercel_url, self.vercel_branch_url):
                if host:
                    if not re.fullmatch(r'[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.vercel\.app', host):
                        raise ValueError('Vercel system URL must be an exact vercel.app hostname')
                    if host.lower() not in self.allowed_hosts:
                        self.allowed_hosts.append(host.lower())
            # Vercel may select a custom domain here; custom domains remain explicitly configured.
            host = self.vercel_project_production_url.lower()
            if re.fullmatch(r'[a-z0-9-]+(?:\.[a-z0-9-]+)*\.vercel\.app', host) and host not in self.allowed_hosts:
                self.allowed_hosts.append(host)
        return self

    @field_validator('trusted_proxy_cidrs')
    @classmethod
    def validate_proxy_cidrs(cls, value: list[str]) -> list[str]:
        for network in value:
            ip_network(network)
        return value

    @field_validator('subscriber_api_token')
    @classmethod
    def validate_subscriber_token(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None:
            raw = value.get_secret_value()
            if not 32 <= len(raw) <= 256 or not raw.isascii() or any(c.isspace() for c in raw):
                raise ValueError('SUBSCRIBER_API_TOKEN must be a random ASCII token of 32-256 characters')
        return value

    @field_validator('superadmin_password_hash')
    @classmethod
    def validate_hash(cls, value: SecretStr) -> SecretStr:
        validate_password_hash(value.get_secret_value())
        return value

    @field_validator('superadmin_email')
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()

    @field_validator('mongodb_uri')
    @classmethod
    def validate_uri(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith(('mongodb://', 'mongodb+srv://')):
            raise ValueError('MONGODB_URI must be a MongoDB connection URI')
        return value

    @field_validator('allowed_hosts', mode='before')
    @classmethod
    def validate_hosts(cls, value):
        if isinstance(value, str):
            raw = value.strip()
            if raw.startswith('['):
                hosts = json.loads(raw)
            else:
                hosts = [h.strip() for h in raw.split(',') if h.strip()]
        elif isinstance(value, list):
            hosts = [str(h).strip() for h in value if str(h).strip()]
        else:
            raise ValueError('ALLOWED_HOSTS must be a list of hostnames')
        if not hosts or any('*' in host or '://' in host or '/' in host for host in hosts):
            raise ValueError('ALLOWED_HOSTS must contain explicit hostnames and never wildcard (*)')
        return hosts


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

## app/database.py

```python
from contextlib import asynccontextmanager
import hashlib
import logging
from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography import x509
from fastapi import FastAPI, Request
from pymongo import AsyncMongoClient
from .config import get_settings
from .profile import build_profile

logger = logging.getLogger(__name__)


def admin_document(settings):
    password_hash = settings.superadmin_password_hash.get_secret_value()
    return {'email': settings.superadmin_email, 'password_hash': password_hash,
            'auth_version': hashlib.sha256(password_hash.encode('ascii')).hexdigest()}


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.profile = None
    try:
        app.state.profile = build_profile(settings) if settings.nextdns_id else None
    except (ValueError, OSError, x509.ExtensionNotFound, InvalidSignature, UnsupportedAlgorithm) as exc:
        logger.error('PROFILE_CONFIG_INVALID: %s; profile download disabled', type(exc).__name__)
    client = AsyncMongoClient(
        settings.mongodb_uri.get_secret_value(), tz_aware=True,
        serverSelectionTimeoutMS=5000, connectTimeoutMS=5000,
        socketTimeoutMS=5000, timeoutMS=5000, maxPoolSize=20,
    )
    try:
        await client.admin.command('ping')
        db = client[settings.mongodb_database]
        app.state.accounts = db.accounts
        app.state.admins = db.admins
        app.state.sessions = db.sessions
        app.state.login_limits = db.login_limits
        app.state.viewers_history = db.viewers_history

        await app.state.accounts.create_index('locket_id', unique=True)
        await db.admins.create_index('email', unique=True)
        await db.sessions.create_index('expires_at', expireAfterSeconds=0)
        await db.login_limits.create_index('expires_at', expireAfterSeconds=0)
        await db.viewers_history.create_index([('token', 1), ('viewed_at', -1)])

        await db.admins.update_one({'_id': 'superadmin'}, {
            '$setOnInsert': admin_document(settings),
        }, upsert=True)
        yield
    finally:
        await client.close()


def get_accounts(request: Request):
    return request.app.state.accounts
```

## app/locket_modifier.py

```python
import asyncio
import json
import secrets
import urllib.error
import urllib.request
import httpx
import os
from datetime import datetime, timezone, timedelta
from urllib.parse import quote
from starlette.datastructures import Headers
from fastapi.encoders import jsonable_encoder
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse, FileResponse

from .config import get_settings
from .models import subscriber_response
from .routers.management import download_profile
from .security import token_digest

router = APIRouter(tags=["Locket Proxy"])

HOP_HEADERS = {'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
               'te', 'trailer', 'transfer-encoding', 'upgrade'}
MAX_RESPONSE = 50 * 1024 * 1024

ADMIN_PATH = os.getenv("ADMIN_PATH", "/admin")

# ================= 1. TRANG CHỦ VÀ CÁC API QUẢN TRỊ (KHỚP VỚI INDEX.HTML GỐC) =================

@router.get("/", response_class=FileResponse)
async def get_root_page():
    """Phục vụ file index.html nguyên bản khi truy cập trang chủ /"""
    current_dir = os.path.dirname(os.path.realpath(__file__))
    file_path = os.path.join(current_dir, "..", "web", "index.html")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Không tìm thấy file giao diện web/index.html")
    return FileResponse(file_path)

@router.get(ADMIN_PATH, response_class=FileResponse)
async def get_admin_page():
    """Đường dẫn Admin dự phòng"""
    current_dir = os.path.dirname(os.path.realpath(__file__))
    file_path = os.path.join(current_dir, "..", "web", "index.html")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Không tìm thấy file giao diện")
    return FileResponse(file_path)

@router.post("/api/admin/login")
async def api_admin_login(req: Request):
    """Xử lý đăng nhập từ file index.html gốc"""
    data = await req.json()
    email = data.get("email", "")
    password = data.get("password", "")
    
    accounts_col = getattr(req.app.state, "accounts", None)
    if accounts_col is None:
        raise HTTPException(503, "Lỗi DB")
    
    # Kiểm tra trong collection admins hoặc accounts tùy cấu hình của bạn
    admin_user = await accounts_col.database["admins"].find_one({"username": email, "password": password})
    if not admin_user:
        raise HTTPException(status_code=401, detail="Email hoặc mật khẩu không đúng")
        
    token = secrets.token_hex(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    return {"access_token": token, "expires_at": expires_at}

@router.get("/api/admin/me")
async def api_admin_me(req: Request):
    auth = req.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {"email": "admin@vuthanhluan.bond"}

@router.post("/api/admin/logout")
async def api_admin_logout():
    return Response(status_code=204)

@router.get("/admin/accounts")
async def api_get_accounts(req: Request, skip: int = 0, limit: int = 50):
    accounts_col = getattr(req.app.state, "accounts", None)
    if accounts_col is None:
        raise HTTPException(503, "Lỗi DB")
    
    cursor = accounts_col.find({"status": "active"}).skip(skip).limit(limit)
    accounts = await cursor.to_list(length=limit)
    
    result = []
    for acc in accounts:
        result.append({
            "locket_id": acc.get("locket_id"),
            "expires_date": acc.get("expires_date", (datetime.now(timezone.utc) + timedelta(days=365)).isoformat())
        })
    return JSONResponse(result)

@router.post("/admin/add-account")
async def api_add_account(req: Request):
    data = await req.json()
    accounts_col = getattr(req.app.state, "accounts", None)
    
    await accounts_col.update_one(
        {"locket_id": data.get("locket_id")},
        {"$set": {
            "locket_id": data.get("locket_id"), 
            "expires_date": data.get("expires_date"),
            "status": "active",
            "updated_at": datetime.now(timezone.utc)
        }},
        upsert=True
    )
    return Response(status_code=204)

@router.delete("/admin/accounts/{locket_id}")
async def api_delete_account(req: Request, locket_id: str):
    accounts_col = getattr(req.app.state, "accounts", None)
    await accounts_col.delete_one({"locket_id": locket_id})
    return Response(status_code=204)

# ================= 2. HỖ TRỢ XỬ LÝ AI & PROXY =================

async def process_image_with_ai(image_bytes: bytes, prompt: str) -> bytes:
    api_token = os.getenv("HUGGINGFACE_API_TOKEN", "")
    if not api_token:
        raise ValueError("Thiếu cấu hình HUGGINGFACE_API_TOKEN")

    hf_endpoint = "https://api-inference.huggingface.co/models/timbrooks/instruct-pix2pix"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/octet-stream",
        "X-Wait-For-Model": "true"
    }
    async with httpx.AsyncClient(timeout=9.5) as client:
        resp = await client.post(hf_endpoint, headers=headers, content=image_bytes)
        if resp.status_code == 200:
            return resp.content
        return None

def _clean_headers(headers):
    named = {key.strip().lower() for key in headers.get('connection', '').split(',')}
    return {key.lower(): value for key, value in headers.items()
            if key.lower() not in HOP_HEADERS | named | {'content-length'}}

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def _forward_upstream(url: str, body: bytes | None, headers: dict[str, str], method: str, timeout: float):
    req = urllib.request.Request(url, data=body if body else None, headers=headers, method=method)
    opener = urllib.request.build_opener(NoRedirect())
    try:
        response = opener.open(req, timeout=timeout)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        content = response.read(MAX_RESPONSE + 1)
        if len(content) > MAX_RESPONSE:
            raise ValueError('Upstream response exceeds limit')
        return response.code, dict(response.headers.items()), content

def _extract_locket_id(path: str, data: dict, request_headers: dict) -> str:
    headers_lower = {k.lower(): v for k, v in request_headers.items()}
    for hk in ["x-app-user-id", "x-revenuecat-app-user-id", "x-locket-user-id"]:
        if hk in headers_lower and headers_lower[hk]:
            return headers_lower[hk]
    sub = data.get('subscriber')
    if isinstance(sub, dict) and isinstance(sub.get('original_app_user_id'), str) and sub['original_app_user_id']:
        return sub['original_app_user_id']
    parts = [p for p in path.split("/") if p]
    if "subscribers" in parts:
        idx = parts.index("subscribers")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return ''

@router.get("/install", response_class=Response)
async def download_proxy_profile(request: Request):
    return await download_profile(request)

@router.get("/proxy.pac", response_class=Response)
async def get_proxy_pac(request: Request):
    host = request.headers.get("host", "locketgold.vuthanhluan.bond")
    pac_content = f"""
function FindProxyForURL(url, host) {{
    if (shExpMatch(host, "*locketcamera.com*") || shExpMatch(host, "*revenuecat.com*")) {{
        return "PROXY {host}";
    }}
    return "DIRECT";
}}
"""
    return Response(content=pac_content.strip(), media_type="application/x-ns-proxy-autoconfig")

# ================= 3. REVERSE PROXY ĐỘNG =================

@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def dynamic_reverse_proxy(request: Request, path: str):
    if request.method == "GET":
        ext = path.split('.')[-1].lower() if '.' in path else ""
        if ext in ['css', 'js', 'png', 'jpg', 'ico']:
            current_dir = os.path.dirname(os.path.realpath(__file__))
            file_path = os.path.join(current_dir, "..", "web", path)
            if os.path.exists(file_path):
                return FileResponse(file_path)

    original_host = request.headers.get("host", "")
    if "revenuecat.com" in original_host:
        upstream_host = "api.revenuecat.com"
    else:
        upstream_host = "api.locketcamera.com"
        
    url = f"https://{upstream_host}/" + quote(path, safe="/:@!$&'()*+,;=-._~")
    
    query_params = str(request.url.query)
    if query_params:
        url += f"?{query_params}"

    headers = _clean_headers(dict(request.headers))
    for key in list(headers):
        if key in {'host', 'cookie', 'forwarded', 'accept-encoding'} or key.startswith(('x-forwarded-', 'cf-')):
            del headers[key]
    headers['Host'] = upstream_host
    headers['Accept-Encoding'] = 'identity'

    method = request.method
    content_type_header = headers.get("content-type", "")
    
    is_upload = method in ["POST", "PUT", "PATCH"] and (
        "multipart/form-data" in content_type_header.lower()
        or "octet-stream" in content_type_header.lower()
        or "image/" in content_type_header.lower()
    )
    body = await request.body()
    timeout_limit = 60.0 if is_upload else 30.0

    if is_upload:
        try:
            if body:
                ai_prompt = "strictly change hair color to vibrant fiery red hair, highly detailed, realistic hair texture"
                modified_bytes = await process_image_with_ai(body, ai_prompt)
                if modified_bytes:
                    body = modified_bytes
        except Exception as e:
            print(f"[AI Proxy Error]: {e}")

    try:
        upstream_status, upstream_headers, upstream_content = await asyncio.to_thread(
            _forward_upstream, url, body, headers, method, timeout_limit
        )
    except (OSError, ValueError):
        return JSONResponse(status_code=502, content={'detail': 'Upstream unavailable'})

    upstream_headers = Headers({key.lower(): value for key, value in upstream_headers.items()})
    response_headers = _clean_headers(upstream_headers)
    response_headers.pop('set-cookie', None)
    if 300 <= upstream_status < 400:
        return JSONResponse({'detail': 'Upstream redirect blocked'}, status_code=502)

    if is_upload:
        return Response(content=upstream_content, status_code=upstream_status, headers=response_headers, media_type=upstream_headers.get("content-type"))

    content_type = upstream_headers.get("content-type", "")
    accounts_col = getattr(request.app.state, "accounts", None)

    if (200 <= upstream_status < 300 and 
            'application/json' in content_type.lower() and upstream_content and
            upstream_headers.get('content-encoding', 'identity').lower() == 'identity'):
        try:
            data = json.loads(upstream_content.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return Response(upstream_content, status_code=upstream_status, headers=response_headers)
        
        if isinstance(data, (dict, list)):
            segments = set(path.split('/'))
            
            if segments & {'subscribers', 'user', 'users'}:
                if isinstance(data, dict):
                    candidate_id = _extract_locket_id(path, data, dict(request.headers))
                    
                    if accounts_col is not None and candidate_id:
                        account_record = await accounts_col.find_one({"locket_id": candidate_id, "status": "active"}, {"_id": 0})
                        
                        if account_record:
                            now = datetime.now(timezone.utc)
                            sub_payload = subscriber_response(candidate_id, account_record, now)
                            subscriber = data.get('subscriber')
                            
                            if subscriber is None:
                                subscriber = data['subscriber'] = sub_payload['subscriber']
                                
                            if isinstance(subscriber, dict):
                                for field, key in [('entitlements', 'Gold'), ('subscriptions', 'com.locket.gold.yearly')]:
                                    values = subscriber.get(field)
                                    if not isinstance(values, dict):
                                        values = {}
                                    values.pop(key, None)
                                    values.update(sub_payload['subscriber'][field])
                                    subscriber[field] = values

            for key in ('etag', 'content-md5', 'digest', 'content-encoding'):
                response_headers.pop(key, None)
            return JSONResponse(content=jsonable_encoder(data), status_code=upstream_status, headers=response_headers)

    return Response(
        content=upstream_content,
        status_code=upstream_status,
        headers=response_headers,
        media_type=upstream_headers.get("content-type"),
    )
```

## app/main.py

```python
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient

# Import router từ file locket_modifier mà chúng ta vừa hoàn thiện
from app.locket_modifier import router as locket_router

# ================= QUẢN LÝ KẾT NỐI MONGODB (DÀNH CHO SERVERLESS) =================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Quản lý vòng đời của ứng dụng.
    Mở kết nối Database khi Vercel boot máy chủ ảo lên, và đóng lại khi xử lý xong.
    """
    # Đảm bảo bạn đã cấu hình biến môi trường MONGODB_URI trên Vercel
    mongodb_uri = os.getenv("MONGODB_URI")
    
    if mongodb_uri:
        # Khởi tạo client kết nối tới MongoDB Atlas
        client = AsyncIOMotorClient(mongodb_uri)
        app.state.db_client = client
        
        # Lấy database (Nếu URI của bạn không có tên DB mặc định, nó sẽ dùng 'locket_db')
        db = client.get_default_database("locket_db")
        
        # Gán collection 'accounts' vào app.state để locket_modifier.py có thể gọi
        app.state.accounts = db["accounts"]
        
        # (Collection 'admins' sẽ được locket_modifier.py tự động gọi qua accounts.database["admins"])
    else:
        print("[CẢNH BÁO] Chưa cấu hình biến môi trường MONGODB_URI")
        app.state.accounts = None

    yield  # Ứng dụng chạy tại đây

    # Đóng kết nối khi máy chủ ảo của Vercel tắt (tránh treo memory)
    if hasattr(app.state, "db_client"):
        app.state.db_client.close()
# ===============================================================================

# Khởi tạo FastAPI
app = FastAPI(
    title="Locket Gold Universal Proxy",
    description="Hệ thống cấp quyền Locket Gold và Xử lý Ảnh AI",
    version="2.0.0",
    lifespan=lifespan
)

# Cấu hình CORS để giao diện Admin (fetch API) không bị chặn
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Bạn có thể thay "*" bằng tên miền thật để bảo mật hơn
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Tích hợp toàn bộ API Quản trị và Proxy từ file locket_modifier.py
app.include_router(locket_router)

# Route phụ để kiểm tra server có đang sống không (Ping test)
@app.get("/")
async def root_health_check():
    return {"status": "Locket Proxy is running mượt mà 🚀"}
```

## app/middleware.py

```python
"""Bounded requests and throttling with explicitly trusted proxy addresses."""
import asyncio
from ipaddress import ip_address, ip_network
import secrets
import time

from fastapi.responses import JSONResponse
from starlette.datastructures import Headers, MutableHeaders
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .config import get_settings

MAX_BODY = 8192


def client_ip(scope) -> str:
    peer = scope['client'][0] if scope.get('client') else 'unknown'
    try:
        address = ip_address(peer)
        if any(address in ip_network(cidr) for cidr in get_settings().trusted_proxy_cidrs):
            forwarded = Headers(scope=scope).get('cf-connecting-ip', '')
            return str(ip_address(forwarded))
        return str(address)
    except ValueError:
        return peer


def security_headers(nonce: str, https: bool) -> dict[str, str]:
    headers = {
        'Cache-Control': 'no-store',
        'Referrer-Policy': 'no-referrer',
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'DENY',
        'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
        'Content-Security-Policy': (
            f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; "
            "img-src 'self' data:; connect-src 'self' https://challenges.cloudflare.com; frame-src https://challenges.cloudflare.com; "
            "form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
        ),
    }
    if https:
        headers['Strict-Transport-Security'] = 'max-age=31536000'
    return headers


class RateLimiter:
    def __init__(self, capacity: int = 10000):
        self.buckets = {}
        self.capacity = capacity
        self.next_cleanup = 0.0

    def allow(self, key: tuple, limit: int) -> bool:
        now = time.monotonic()
        if now >= self.next_cleanup:
            self.buckets = {k: v for k, v in self.buckets.items() if v[0] > now}
            self.next_cleanup = now + 60
        bucket = self.buckets.get(key)
        if bucket is None or bucket[0] <= now:
            if bucket is None and len(self.buckets) >= self.capacity:
                return False
            self.buckets[key] = [now + 60, 1]
            return True
        if bucket[1] >= limit:
            return False
        bucket[1] += 1
        return True


class SecurityMiddleware:
    def __init__(self, app):
        self.settings = get_settings()
        self.app = TrustedHostMiddleware(
            app, allowed_hosts=self.settings.allowed_hosts, www_redirect=False,
        )
        self.limiter = RateLimiter()

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)

        # Bỏ qua giới hạn 8KiB và kiểm tra body cho toàn bộ luồng Proxy
        if scope['path'].startswith('/proxy'):
            return await self.app(scope, receive, send)

        nonce = secrets.token_urlsafe(24)
        scope.setdefault('state', {})['csp_nonce'] = nonce
        headers = Headers(scope=scope)
        https = scope['scheme'] == 'https' or headers.get('x-forwarded-proto') == 'https'

        async def secured_send(message):
            if message['type'] == 'http.response.start':
                MutableHeaders(scope=message).update(security_headers(nonce, https))
            await send(message)

        async def reject(status, detail, retry=False):
            response = JSONResponse(
                {'detail': detail}, status_code=status,
                headers={'Retry-After': '60'} if retry else None,
            )
            await response(scope, receive, secured_send)

        if self.settings.require_https and not https:
            return await reject(400, 'HTTPS is required')
        ip = client_ip(scope)
        if not self.limiter.allow((ip, 'all'), 120):
            return await reject(429, 'Too many requests', True)
        if scope['path'].rstrip('/') == '/api/admin/login':
            if (not self.limiter.allow((ip, 'login'), 10)
                    or not self.limiter.allow(('global', 'login'), 30)):
                return await reject(429, 'Too many login attempts', True)
        length = headers.get('content-length')
        if length is not None:
            if not length.isascii() or not length.isdecimal():
                return await reject(400, 'Invalid Content-Length')
            if len(length) > 10 or int(length) > MAX_BODY:
                return await reject(413, 'Request body exceeds 8 KiB')

        body = bytearray()
        try:
            async with asyncio.timeout(5):
                while True:
                    message = await receive()
                    if message['type'] == 'http.disconnect':
                        return
                    body.extend(message.get('body', b''))
                    if len(body) > MAX_BODY:
                        return await reject(413, 'Request body exceeds 8 KiB')
                    if not message.get('more_body', False):
                        break
        except TimeoutError:
            return await reject(408, 'Request body timed out')

        delivered = False

        async def buffered_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
            return await receive()

        await self.app(scope, buffered_receive, secured_send)
```

## app/models.py

```python
from datetime import date, datetime, time, timezone
from typing import Annotated
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

AccountId = Annotated[str, Field(min_length=1, max_length=128, pattern=r'^[A-Za-z0-9_$:@.\-]+$')]


def normalize_expiry(value) -> datetime:
    if isinstance(value, str):
        value = date.fromisoformat(value) if len(value) == 10 else datetime.fromisoformat(value.replace('Z', '+00:00'))
    if isinstance(value, date) and not isinstance(value, datetime):
        value = datetime.combine(value, time(23, 59, 59), tzinfo=timezone.utc)
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('expires_date must be a date or a datetime with timezone')
    return value.astimezone(timezone.utc)


class AccountInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    locket_id: AccountId
    expires_date: AwareDatetime

    @field_validator('expires_date', mode='before')
    @classmethod
    def parse_expiry(cls, value):
        return normalize_expiry(value)

    @field_validator('expires_date')
    @classmethod
    def future_date(cls, value: datetime) -> datetime:
        if value <= datetime.now(timezone.utc):
            raise ValueError('expires_date must be in the future')
        return value


class AccountOutput(BaseModel):
    locket_id: str
    expires_date: AwareDatetime


def subscriber_response(account_id: str, account: dict | None, now: datetime | None = None) -> dict:
    now = now if now is not None else datetime.now(timezone.utc)
    try:
        expiry = normalize_expiry(account['expires_date']) if account else None
    except (ValueError, TypeError, KeyError):
        expiry = None

    if expiry is None:
        expiry = datetime(2029, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

    active = expiry > now
    entitlement_expires = expiry.isoformat().replace('+00:00', 'Z') if active else None

    product_id = "com.locket.gold.yearly"
    now_str = now.isoformat().replace('+00:00', 'Z')

    entitlement = {
        'expires_date': entitlement_expires,
        'grace_period_expires_date': None,
        'product_identifier': product_id,
        'purchase_date': "2026-01-01T00:00:00Z"
    } if active else None

    subscriptions = {
        product_id: {
            'expires_date': entitlement_expires,
            'is_sandbox': False,
            'original_purchase_date': "2026-01-01T00:00:00Z",
            'purchase_date': "2026-01-01T00:00:00Z",
            'ownership_type': 'PURCHASED',
            'store': 'app_store'
        }
    } if active else {}

    return {
        'request_date': now_str,
        'request_date_ms': int(now.timestamp() * 1000),
        'subscriber': {
            'original_app_user_id': account_id,
            'non_subscriptions': {},
            'first_seen': now_str,
            'entitlements': {'Gold': entitlement} if active else {},
            'subscriptions': subscriptions,
            'management_url': None,
            'original_purchase_date': "2026-01-01T00:00:00Z"
        }
    }
```

## app/passwords.py

```python
"""Salted, deliberately expensive password hashing using the standard library."""
import hashlib
import secrets

ITERATIONS = 600000


def validate_password_hash(encoded: str) -> tuple[int, bytes, bytes]:
    try:
        algorithm, count, salt, digest = encoded.split('$')
        iterations = int(count)
        if algorithm != 'pbkdf2_sha256' or not ITERATIONS <= iterations <= 2000000:
            raise ValueError
        salt_bytes, digest_bytes = bytes.fromhex(salt), bytes.fromhex(digest)
        if len(salt_bytes) != 16 or len(digest_bytes) != 32:
            raise ValueError
        return iterations, salt_bytes, digest_bytes
    except (ValueError, TypeError):
        raise ValueError('A valid PBKDF2-SHA256 password hash is required') from None


def hash_password(password: str) -> str:
    if not 12 <= len(password) <= 256:
        raise ValueError('Password must contain 12-256 characters')
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, ITERATIONS)
    return f'pbkdf2_sha256${ITERATIONS}${salt.hex()}${digest.hex()}'


def verify_password(password: str, encoded: str) -> bool:
    try:
        iterations, salt, expected = validate_password_hash(encoded)
    except ValueError:
        return False
    actual = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
    return secrets.compare_digest(actual, expected)
```

## app/profile.py

```python
import plistlib
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone
from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding
from fastapi import HTTPException
from .config import Settings


def payload(kind: str, name: str) -> dict:
    identifier = 'local.license-manager.' + name.lower().replace(' ', '-')
    return {'PayloadType': kind, 'PayloadVersion': 1, 'PayloadIdentifier': identifier,
            'PayloadUUID': str(uuid4()).upper(), 'PayloadDisplayName': name}


def build_profile(settings: Settings) -> bytes:
    if not settings.nextdns_id:
        raise HTTPException(503, 'Chưa cấu hình NEXTDNS_ID trên server.')
    dns = payload('com.apple.dnsSettings.managed', 'NextDNS')
    dns['DNSSettings'] = {'DNSProtocol': 'HTTPS',
                          'ServerURL': f'https://dns.nextdns.io/{settings.nextdns_id}'}
    contents = [dns]
    if settings.root_ca_path and settings.root_ca_pem:
        raise ValueError('Set only one of ROOT_CA_PATH or ROOT_CA_PEM')
    if settings.root_ca_path or settings.root_ca_pem:
        if settings.root_ca_pem:
            # Accept both pasted multiline PEM and literal backslash-n from environment UIs.
            raw = settings.root_ca_pem.replace('\\n', '\n').strip().encode('utf-8')
        else:
            path = Path(settings.root_ca_path).resolve(strict=True)
            if not path.is_file():
                raise ValueError('ROOT_CA_PATH must be a certificate file')
            with path.open('rb') as certificate_file:
                raw = certificate_file.read(65537)
        if not raw or len(raw) > 65536:
            raise ValueError('Root CA must be a certificate no larger than 64 KiB')
        if b'PRIVATE KEY' in raw:
            raise ValueError('Root CA must never contain a private key')
        if b'-----BEGIN CERTIFICATE' in raw and raw.count(b'-----BEGIN CERTIFICATE') != 1:
            raise ValueError('Provide exactly one root CA certificate, not a certificate chain')
        cert = (x509.load_pem_x509_certificate(raw) if b'-----BEGIN CERTIFICATE' in raw
                else x509.load_der_x509_certificate(raw))
        if not cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
            raise ValueError('Root CA must contain a CA certificate')
        # An intermediate CA is not a self-signed root trust anchor.
        cert.verify_directly_issued_by(cert)
        try:
            usage = cert.extensions.get_extension_for_class(x509.KeyUsage).value
        except x509.ExtensionNotFound:
            usage = None
        if usage is not None and not usage.key_cert_sign:
            raise ValueError('Root CA must allow certificate signing')
        now = datetime.now(timezone.utc)
        if not cert.not_valid_before_utc <= now < cert.not_valid_after_utc:
            raise ValueError('The CA certificate is expired or not yet valid')
        ca = payload('com.apple.security.root', 'Root CA')
        ca['PayloadCertificateFileName'] = 'root-ca.cer'
        ca['PayloadContent'] = cert.public_bytes(Encoding.DER)
        contents.append(ca)
    profile = payload('Configuration', 'Locket Gold DNS')
    profile.update(PayloadContent=contents, PayloadRemovalDisallowed=False, PayloadScope='System',
                   PayloadOrganization='vuthanhluan.bond',
                   PayloadDescription='Cấu hình DNS được cung cấp bởi nhà phát triển vuthanhluan.bond. '
                   'Dành cho trải nghiệm chia sẻ ảnh, quay và đăng video, xem lại khoảnh khắc trên Locket. '
                   'Các tính năng phụ thuộc ứng dụng và quyền tài khoản đang sử dụng.')
    return plistlib.dumps(profile, fmt=plistlib.FMT_XML)
```

## app/routers/__init__.py

```python
# Package khởi tạo cho routers
```

## app/routers/management.py

```python
from pathlib import Path
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, Response, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from pymongo.errors import DuplicateKeyError
from ..database import get_accounts
from ..models import AccountInput, AccountOutput, AccountId
from ..security import require_admin
from ..config import get_settings

router = APIRouter()
WEB = Path(__file__).resolve().parent.parent.parent / 'web'
Accounts = Annotated[object, Depends(get_accounts)]

@router.get('/favicon.ico', include_in_schema=False)
async def favicon():
    return FileResponse(WEB / 'favicon.ico', media_type='image/vnd.microsoft.icon')

@router.get('/apple-touch-icon.png', include_in_schema=False)
@router.get('/apple-touch-icon-precomposed.png', include_in_schema=False)
async def apple_touch_icon():
    return FileResponse(WEB / 'apple-touch-icon.png', media_type='image/png')

@router.get('/', response_class=HTMLResponse, include_in_schema=False)
async def home(request: Request):
    if 'admin' in request.query_params:
        raise HTTPException(400, 'URL tokens are disabled. Open /admin to sign in.')
    return render_page(False, request)

@router.get('/robots.txt', include_in_schema=False)
async def robots_txt():
    return PlainTextResponse("User-agent: *\nDisallow: /")

# --- ĐIỀU HƯỚNG PAC FILE TRỰC TIẾP TRÁNH LỖI TRẮNG TRANG / 404 ---
@router.get('/proxy.pac', response_class=Response)
async def get_root_pac_file(request: Request):
    host = request.headers.get("host", "locketgold-premium.vercel.app")
    pac_content = f"""function FindProxyForURL(url, host) {{
    if (shExpMatch(host, "*locketcamera.com*") || shExpMatch(host, "*revenuecat.com*")) {{
        return "PROXY {host}";
    }}
    return "DIRECT";
}}"""
    return Response(content=pac_content, media_type="application/x-ns-proxy-autoconfig")

def render_page(admin: bool, request: Request) -> HTMLResponse:
    page = (WEB / 'index.html').read_text(encoding='utf-8')
    start, end = ('<!-- PUBLIC_START -->', '<!-- PUBLIC_END -->') if admin else ('<!-- ADMIN_START -->', '<!-- ADMIN_END -->')
    before, rest = page.split(start)
    _, after = rest.split(end)
    page = before + after
    page = page.replace('__TURNSTILE_SITE_KEY__', get_settings().turnstile_site_key)
    return HTMLResponse(page.replace('__NONCE__', request.state.csp_nonce).replace('__VIEW__', 'admin' if admin else 'public'))

@router.get('/admin-gmnWJ5nG3qZRcdku3eBtkIka', response_class=HTMLResponse, include_in_schema=False)
async def admin_login(request: Request):
    return render_page(True, request)

@router.get('/profile.mobileconfig')
async def download_profile(request: Request):
    if not request.app.state.profile:
        raise HTTPException(503, 'Cấu hình DNS hoặc chứng chỉ chưa sẵn sàng.')
    return Response(request.app.state.profile, media_type='application/x-apple-aspen-config',
                    headers={'Content-Disposition': 'attachment; filename="locket.mobileconfig"'})

# Các route yêu cầu quyền Admin
admin_router = APIRouter(prefix='/admin', dependencies=[Depends(require_admin)])

@admin_router.post('/add-account', response_model=AccountOutput)
async def upsert_account(data: AccountInput, accounts: Accounts):
    document = data.model_dump()
    try:
        await accounts.update_one({'locket_id': data.locket_id}, {'$set': document}, upsert=True)
    except DuplicateKeyError:
        await accounts.update_one({'locket_id': data.locket_id}, {'$set': document})
    return document

@admin_router.get('/accounts', response_model=list[AccountOutput])
async def list_accounts(accounts: Accounts, skip: int = Query(0, ge=0, le=10000), limit: int = Query(50, ge=1, le=100)):
    return await accounts.find({}, {'_id': 0}).sort('locket_id', 1).skip(skip).limit(limit).to_list(length=limit)

@admin_router.delete('/accounts/{account_id}', status_code=204)
async def delete_account(account_id: AccountId, accounts: Accounts):
    result = await accounts.delete_one({'locket_id': account_id})
    if not result.deleted_count:
        raise HTTPException(404, 'Account not found')
    return Response(status_code=204)
```

## app/routers/subscribers.py

```python
from datetime import datetime, timezone
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from ..database import get_accounts
from ..models import AccountId, subscriber_response
from ..security import require_subscriber_access

router = APIRouter(tags=["Subscribers"])
Accounts = Annotated[object, Depends(get_accounts)]

@router.get('/v1/subscribers/{account_id}', dependencies=[Depends(require_subscriber_access)])
async def subscriber(account_id: AccountId, accounts: Accounts):
    account = await accounts.find_one({'locket_id': account_id}, {'_id': 0})
    if not account:
        return subscriber_response(account_id, None)
    return subscriber_response(account_id, account)
```

## app/security.py

```python
import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from pymongo import ReturnDocument
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from .config import get_settings
from .middleware import client_ip

bearer = HTTPBearer(auto_error=False)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


async def require_subscriber_access(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
):
    unauthorized = HTTPException(401, "Invalid or missing subscriber API token", headers={"WWW-Authenticate": "Bearer"})
    if credentials is None:
        raise unauthorized

    settings = get_settings()
    configured = settings.subscriber_api_token
    if configured is not None and secrets.compare_digest(
        credentials.credentials.encode("utf-8"),
        configured.get_secret_value().encode("ascii"),
    ):
        return

    if re.fullmatch(r"[A-Za-z0-9_-]{64}", credentials.credentials):
        sessions = getattr(request.app.state, "sessions", None)
        admins = getattr(request.app.state, "admins", None)
        if sessions is not None and admins is not None:
            session = await sessions.find_one({
                "_id": token_digest(credentials.credentials),
                "expires_at": {"$gt": datetime.now(timezone.utc)},
            })
            if session is not None and session.get("admin_id") == "superadmin":
                admin = await admins.find_one({"_id": session["admin_id"]})
                if admin is not None and admin.get("auth_version") == session.get("auth_version"):
                    return

    raise unauthorized


async def require_admin(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
):
    now = datetime.now(timezone.utc)
    ip_key = hashlib.sha256(client_ip(request.scope).encode('utf-8')).hexdigest()
    bucket = await request.app.state.login_limits.find_one_and_update(
        {'_id': f'admin:{int(now.timestamp()) // 60}:{ip_key}'},
        {'$inc': {'count': 1}, '$setOnInsert': {'expires_at': now + timedelta(minutes=2)}},
        upsert=True, return_document=ReturnDocument.AFTER,
    )
    if bucket['count'] > 60:
        raise HTTPException(429, 'Too many admin requests', headers={'Retry-After': '60'})
    unauthorized = HTTPException(401, "Invalid or expired session", headers={"WWW-Authenticate": "Bearer"})
    if credentials is None or not re.fullmatch(r"[A-Za-z0-9_-]{64}", credentials.credentials):
        raise unauthorized
    session = await request.app.state.sessions.find_one({
        "_id": token_digest(credentials.credentials),
        "expires_at": {"$gt": datetime.now(timezone.utc)},
    })
    if session is None or session.get("admin_id") != "superadmin":
        raise unauthorized
    admin = await request.app.state.admins.find_one({"_id": session["admin_id"]})
    if admin is None or admin.get("auth_version") != session["auth_version"]:
        raise unauthorized
    return {"session_id": session["_id"], "email": admin["email"]}
```

## app/turnstile.py

```python
import asyncio
import json
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request as URLRequest, urlopen

from fastapi import HTTPException

from .config import get_settings


def siteverify(secret: str, token: str) -> dict:
    body = urlencode({'secret': secret, 'response': token}).encode('ascii')
    request = URLRequest(
        'https://challenges.cloudflare.com/turnstile/v0/siteverify', data=body,
        headers={'Content-Type': 'application/x-www-form-urlencoded'}, method='POST',
    )
    with urlopen(request, timeout=5) as response:
        return json.loads(response.read(65536))


async def verify_turnstile(token: str):
    settings = get_settings()
    secret = settings.turnstile_secret_key.get_secret_value()
    hostnames = [host.strip().lower() for host in settings.turnstile_hostname.split(',') if host.strip()]
    if not settings.turnstile_site_key and not secret:
        return
    if not settings.turnstile_site_key or not secret or not hostnames:
        raise HTTPException(503, 'Cloudflare Turnstile chưa được cấu hình đầy đủ.')
    if not token:
        raise HTTPException(403, 'Vui lòng hoàn tất xác minh Cloudflare.')
    try:
        result = await asyncio.to_thread(siteverify, secret, token)
    except (URLError, OSError, ValueError):
        raise HTTPException(503, 'Không thể xác minh Cloudflare. Vui lòng thử lại.') from None
    if (not isinstance(result, dict) or result.get('success') is not True
            or result.get('hostname') not in hostnames
            or result.get('action') != 'admin-login'):
        raise HTTPException(403, 'Xác minh Cloudflare không hợp lệ hoặc đã hết hạn.')
```

## bytes

```text

```

## compose.yaml

```yaml
services:
  mongo:
    image: mongo:8.0
    ports:
      - "127.0.0.1:27017:27017"
    volumes:
      - mongo_data:/data/db
    restart: unless-stopped
volumes:
  mongo_data:
```

## index.py

```python
"""Vercel's native FastAPI entrypoint; local Uvicorn can keep using app.main:app."""
from app.main import app as app
```

## pyproject.toml

```toml
[project]
name = "locket-gold-manager"
version = "0.1.0"
requires-python = ">=3.12,<3.15"
dependencies = [
    "fastapi>=0.115,<1",
    "uvicorn[standard]>=0.30,<1",
    "pymongo>=4.13,<5",
    "pydantic-settings>=2.5,<3",
    "cryptography>=43",
    "python-multipart>=0.0.9",
    "httpx>=0.27.0"
]

[tool.vercel]
entrypoint = "app.main:app"

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
addopts = "-p no:cacheprovider"
```

## requirements-dev.txt

```text
-r requirements.txt
pytest>=8,<10
httpx>=0.27,<1
httpx2
```

## requirements.txt

```text
fastapi>=0.115,<1
uvicorn[standard]>=0.30,<1
pymongo>=4.13,<5
motor>=3.6.0,<4
pydantic-settings>=2.5,<3
cryptography>=43
python-multipart>=0.0.9
httpx>=0.27.0
```

## str

```text

```

## tests/conftest.py

```python
from pathlib import Path
from tempfile import TemporaryDirectory


def pytest_configure(config):
    if config.option.basetemp is None:
        # Avoid shared pytest-of-<user> folders with stale Windows permissions.
        temporary = TemporaryDirectory(prefix='locket-pytest-')
        config.add_cleanup(temporary.cleanup)
        config.option.basetemp = Path(temporary.name) / 'run'
```

## tests/test_admin_protection.py

```python
from unittest.mock import AsyncMock, MagicMock
from urllib.error import URLError

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import router
from app.config import get_settings
from app.middleware import SecurityMiddleware, client_ip
from app.passwords import hash_password
from app.routers.management import router as pages


@pytest.fixture
def protected(monkeypatch):
    monkeypatch.setenv('SUPERADMIN_EMAIL', 'admin@example.test')
    monkeypatch.setenv('SUPERADMIN_PASSWORD_HASH', hash_password('test-password'))
    monkeypatch.setenv('MONGODB_URI', 'mongodb://localhost')
    monkeypatch.setenv('ALLOWED_HOSTS', '["testserver"]')
    monkeypatch.setenv('REQUIRE_HTTPS', 'false')
    monkeypatch.setenv('TURNSTILE_SITE_KEY', 'test-site-key')
    monkeypatch.setenv('TURNSTILE_SECRET_KEY', 'test-secret')
    monkeypatch.setenv('TURNSTILE_HOSTNAME', 'admin.example.test')
    monkeypatch.setenv('TRUSTED_PROXY_CIDRS', '[]')
    get_settings.cache_clear()
    app = FastAPI()
    app.add_middleware(SecurityMiddleware)
    app.include_router(router)
    app.include_router(pages)
    app.state.login_limits = AsyncMock()
    app.state.login_limits.find_one_and_update.return_value = {'count': 1}
    app.state.admins = AsyncMock()
    app.state.admins.find_one.return_value = {
        '_id': 'superadmin', 'email': 'admin@example.test',
        'password_hash': get_settings().superadmin_password_hash.get_secret_value(),
        'auth_version': 'test',
    }
    app.state.sessions = AsyncMock()
    verifier = MagicMock(return_value={
        'success': True, 'hostname': 'admin.example.test', 'action': 'admin-login',
    })
    monkeypatch.setattr('app.turnstile.siteverify', verifier)
    with TestClient(app) as http:
        yield http, app, verifier
    get_settings.cache_clear()


def login(http, token='test-token'):
    return http.post('/api/admin/login', json={
        'email': 'admin@example.test', 'password': 'test-password', 'turnstile_token': token,
    })


def test_verified_login_and_widget(protected):
    http, app, verifier = protected
    assert login(http).status_code == 200
    verifier.assert_called_once_with('test-secret', 'test-token')
    app.state.sessions.insert_one.assert_awaited_once()
    page = http.get('/admin')
    assert 'data-sitekey="test-site-key"' in page.text
    assert 'test-secret' not in page.text
    assert 'frame-src https://challenges.cloudflare.com' in page.headers['content-security-policy']
    assert 'onTurnstileReady' not in http.get('/').text


@pytest.mark.parametrize('result', [
    {'success': False}, [],
    {'success': True, 'hostname': 'wrong.test', 'action': 'admin-login'},
    {'success': True, 'hostname': 'admin.example.test', 'action': 'wrong'},
])
def test_invalid_verification_never_checks_password(protected, result):
    http, app, verifier = protected
    verifier.return_value = result
    assert login(http).status_code == 403
    app.state.admins.find_one.assert_not_awaited()
    app.state.sessions.insert_one.assert_not_awaited()


def test_missing_token_and_outage(protected):
    http, app, verifier = protected
    assert login(http, '').status_code == 403
    verifier.assert_not_called()
    verifier.side_effect = URLError('unavailable')
    assert login(http).status_code == 503
    app.state.admins.find_one.assert_not_awaited()


@pytest.mark.parametrize('hostname,status', [
    ('locketgold.vuthanhluan.bond', 200),
    ('locketgold-premium.vercel.app', 200),
    ('locketgold.vuthanhluan.bond.attacker.test', 403),
    ('other.vercel.app', 403),
    ('', 403),
])
def test_multiple_hostnames(protected, monkeypatch, hostname, status):
    http, app, verifier = protected
    monkeypatch.setenv('TURNSTILE_HOSTNAME',
                       'locketgold.vuthanhluan.bond, locketgold-premium.vercel.app ')
    get_settings.cache_clear()
    verifier.return_value['hostname'] = hostname
    assert login(http).status_code == status
    if status == 403:
        app.state.sessions.insert_one.assert_not_awaited()


def test_disabled_and_incomplete_config(protected, monkeypatch):
    http, _, verifier = protected
    monkeypatch.setenv('TURNSTILE_SECRET_KEY', '')
    get_settings.cache_clear()
    assert login(http).status_code == 503
    monkeypatch.setenv('TURNSTILE_SITE_KEY', '')
    get_settings.cache_clear()
    assert login(http, '').status_code == 200
    verifier.assert_not_called()


def test_login_and_admin_shared_limits(protected):
    http, app, verifier = protected
    app.state.login_limits.find_one_and_update.return_value = {'count': 11}
    assert login(http).status_code == 429
    verifier.assert_not_called()
    app.state.login_limits.find_one_and_update.return_value = {'count': 61}
    result = http.get('/api/admin/me')
    assert result.status_code == 429
    assert result.headers['retry-after'] == '60'
    app.state.sessions.find_one.assert_not_awaited()


def test_ip_headers_only_from_trusted_proxy(protected, monkeypatch):
    scope = {'client': ('192.0.2.10', 1000), 'headers': [
        (b'cf-connecting-ip', b'203.0.113.42'), (b'x-forwarded-for', b'198.51.100.1'),
    ]}
    assert client_ip(scope) == '192.0.2.10'
    monkeypatch.setenv('TRUSTED_PROXY_CIDRS', '["192.0.2.0/24"]')
    get_settings.cache_clear()
    assert client_ip(scope) == '203.0.113.42'
    scope['headers'] = [(b'cf-connecting-ip', b'invalid')]
    assert client_ip(scope) == '192.0.2.10'


def test_local_ip_login_limit(protected):
    http, _, verifier = protected
    for _ in range(10):
        assert http.post('/api/admin/login', json={}).status_code == 422
    assert http.post('/api/admin/login', json={}).status_code == 429
    verifier.assert_not_called()


def test_siteverify_posts_token_with_timeout(monkeypatch):
    from app.turnstile import siteverify
    response = MagicMock()
    response.__enter__.return_value.read.return_value = b'{"success":true}'
    transport = MagicMock(return_value=response)
    monkeypatch.setattr('app.turnstile.urlopen', transport)
    assert siteverify('private-secret', 'token+value') == {'success': True}
    request = transport.call_args.args[0]
    assert request.full_url == 'https://challenges.cloudflare.com/turnstile/v0/siteverify'
    assert request.method == 'POST'
    assert request.data == b'secret=private-secret&response=token%2Bvalue'
    assert transport.call_args.kwargs['timeout'] == 5
```

## tests/test_app.py

```python
import asyncio
import hashlib
import json
import plistlib
import secrets
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pymongo.errors import PyMongoError

from app.config import Settings, get_settings
from app.database import get_accounts, lifespan
from app.main import create_app
from app.middleware import RateLimiter, SecurityMiddleware
from app.models import AccountInput, subscriber_response
from app.passwords import hash_password, verify_password
from app.profile import build_profile
from app.security import token_digest


@pytest.fixture(scope='module')
def password_pair():
    password = secrets.token_urlsafe(20)
    return password, hash_password(password)


@pytest.fixture
def client(monkeypatch, password_pair):
    password, encoded = password_pair
    monkeypatch.setenv('SUPERADMIN_EMAIL', 'admin@example.test')
    monkeypatch.setenv('SUPERADMIN_PASSWORD_HASH', encoded)
    monkeypatch.setenv('MONGODB_URI', 'mongodb://127.0.0.1:27017')
    monkeypatch.setenv('ALLOWED_HOSTS', '["localhost"]')
    monkeypatch.setenv('REQUIRE_HTTPS', 'false')
    monkeypatch.setenv('NEXTDNS_ID', 'abc123')
    monkeypatch.setenv('ROOT_CA_PATH', '')
    monkeypatch.setenv('ROOT_CA_PEM', '')
    get_settings.cache_clear()
    app = create_app()
    accounts, admins, sessions = AsyncMock(), AsyncMock(), AsyncMock()
    admin = {'_id': 'superadmin', 'email': 'admin@example.test', 'password_hash': encoded,
             'auth_version': hashlib.sha256(encoded.encode()).hexdigest()}
    admins.find_one.side_effect = lambda query: admin.copy() if query in [
        {'_id': 'superadmin', 'email': admin['email']}, {'_id': admin['_id']}, {'_id': 'superadmin'},
    ] else None
    stored = {}

    async def insert(document):
        stored[document['_id']] = document.copy()

    async def find(query):
        document = stored.get(query['_id'])
        return document.copy() if document and document['expires_at'] > query['expires_at']['$gt'] else None

    async def delete(query):
        stored.pop(query['_id'], None)

    sessions.insert_one.side_effect = insert
    sessions.find_one.side_effect = find
    sessions.delete_one.side_effect = delete
    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.skip.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.to_list = AsyncMock(return_value=[])
    accounts.find = MagicMock(return_value=cursor)
    app.dependency_overrides[get_accounts] = lambda: accounts
    app.state.admins, app.state.sessions = admins, sessions
    app.state.login_limits = AsyncMock()
    buckets = {}

    async def count_login(query, update, **kwargs):
        key = query['_id']
        buckets[key] = buckets.get(key, 0) + 1
        return {'count': buckets[key]}

    app.state.login_limits.find_one_and_update.side_effect = count_login
    app.state.profile = build_profile(get_settings())
    # HTTP tests deliberately skip real MongoDB lifespan.
    http = TestClient(app, base_url='http://localhost', raise_server_exceptions=False)
    yield http, accounts, admins, sessions, stored, password, app
    http.close()
    get_settings.cache_clear()


def sign_in(client):
    http, _, _, _, _, password, _ = client
    response = http.post('/api/admin/login', json={'email': 'admin@example.test', 'password': password})
    assert response.status_code == 200, response.text
    token = response.json()['access_token']
    return token, {'Authorization': 'Bearer ' + token}


def test_views_and_csp(client):
    http = client[0]
    public = http.get('/')
    assert public.status_code == 200
    assert 'id="loginForm"' not in public.text and 'id="accountForm"' not in public.text
    assert '<script' not in public.text
    assert 'href="/profile.mobileconfig"' in public.text
    admin = http.get('/admin')
    assert 'loginForm' in admin.text and 'accountForm' in admin.text
    assert '__NONCE__' not in admin.text
    csp = admin.headers['content-security-policy']
    assert 'unsafe-inline' not in csp and 'nonce-' in csp
    nonce = csp.split("script-src 'nonce-")[1].split("'")[0]
    assert f'nonce="{nonce}"' in admin.text
    assert nonce not in http.get('/admin').headers['content-security-policy']
    assert admin.headers['x-frame-options'] == 'DENY'
    assert admin.headers['x-content-type-options'] == 'nosniff'
    assert http.get('/?admin=old-token').status_code == 400
    for path in ['/web/index.html', '/.env', '/app/config.py', '/%2e%2e/.env']:
        assert http.get(path).status_code == 404


@pytest.mark.parametrize('method,path', [
    ('post', '/admin/add-account'), ('get', '/admin/accounts'),
    ('delete', '/admin/accounts/alice'), ('get', '/api/admin/me'),
    ('post', '/api/admin/logout'),
])
def test_all_admin_data_routes_require_session(client, method, path):
    http, accounts, *_ = client
    for headers in [{}, {'Authorization': 'Bearer ' + 'x' * 64}, {'Authorization': 'Basic abc'}]:
        response = getattr(http, method)(path, headers=headers)
        assert response.status_code == 401
    accounts.update_one.assert_not_called()
    accounts.delete_one.assert_not_called()


def test_subscriber_requires_admin_or_separate_service_token(client, monkeypatch):
    http, accounts, *_ = client
    assert http.get('/v1/subscribers/alice').status_code == 401
    accounts.find_one.assert_not_awaited()
    token = secrets.token_urlsafe(48)
    monkeypatch.setenv('SUBSCRIBER_API_TOKEN', token)
    get_settings.cache_clear()
    accounts.find_one.return_value = None
    response = http.get('/v1/subscribers/alice', headers={'Authorization': 'Bearer ' + token})
    assert response.status_code == 200
    assert response.json()['subscriber']['entitlements'] == {}
    assert http.get('/v1/subscribers/alice', headers={'Authorization': 'Bearer wrong'}).status_code == 401


def test_session_login_expiry_revocation(client):
    http, _, _, _, stored, *_ = client
    token, headers = sign_in(client)
    document = stored[token_digest(token)]
    assert token not in json.dumps(document, default=str)
    assert 3500 < (document['expires_at'] - datetime.now(timezone.utc)).total_seconds() <= 3600
    assert http.get('/api/admin/me', headers=headers).json() == {'email': 'admin@example.test'}
    document['expires_at'] = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert http.get('/admin/accounts', headers=headers).status_code == 401
    token, headers = sign_in(client)
    stored[token_digest(token)]['auth_version'] = 'old-password-version'
    assert http.get('/api/admin/me', headers=headers).status_code == 401
    token, headers = sign_in(client)
    stored[token_digest(token)]['admin_id'] = 'non-superadmin'
    assert http.get('/api/admin/me', headers=headers).status_code == 401
    token, headers = sign_in(client)
    assert http.post('/api/admin/logout', headers=headers).status_code == 204
    assert http.get('/api/admin/me', headers=headers).status_code == 401


def test_bad_login_and_rate_limit(client):
    http = client[0]
    wrong = {'email': 'admin@example.test', 'password': 'incorrect-password'}
    assert http.post('/api/admin/login', json=wrong).status_code == 401
    wrong['email'] = 'missing@example.test'
    assert http.post('/api/admin/login', json=wrong).status_code == 401
    for _ in range(8):
        assert http.post('/api/admin/login', json={}).status_code == 422
    response = http.post('/api/admin/login', json={})
    assert response.status_code == 429 and response.headers['retry-after'] == '60'


def test_shared_login_limit_blocks_before_password_verification(client):
    http, _, admins, sessions, *_ = client
    client[-1].state.login_limits.find_one_and_update.side_effect = None
    client[-1].state.login_limits.find_one_and_update.return_value = {'count': 11}
    result = http.post('/api/admin/login', json={
        'email': 'admin@example.test', 'password': client[-2],
    })
    assert result.status_code == 429
    admins.find_one.assert_not_awaited()
    sessions.insert_one.assert_not_awaited()


def test_login_uses_database_credentials_after_environment_changes(client, monkeypatch):
    http, _, admins, sessions, _, password, _ = client
    monkeypatch.setenv('SUPERADMIN_PASSWORD_HASH', hash_password('different-config-password'))
    monkeypatch.setenv('SUPERADMIN_EMAIL', 'other@example.test')
    get_settings.cache_clear()
    sign_in(client)
    admins.find_one.side_effect = None
    admins.find_one.return_value = None
    sessions.insert_one.reset_mock()
    response = http.post('/api/admin/login', json={
        'email': 'admin@example.test', 'password': password,
    })
    assert response.status_code == 401
    sessions.insert_one.assert_not_awaited()


def test_upsert_injection_and_subscriber(client):
    http, accounts, *_ = client
    _, headers = sign_in(client)
    future = datetime.now(timezone.utc) + timedelta(days=30)
    body = {'locket_id': 'alice', 'expires_date': future.isoformat()}
    assert http.post('/admin/add-account', headers=headers, json=body).status_code == 200
    accounts.update_one.assert_awaited_once()
    for value in [{'$ne': None}, '<img src=x onerror=alert(1)>', '../.env', 'a' * 129]:
        body['locket_id'] = value
        response = http.post('/admin/add-account', headers=headers, json=body)
        assert response.status_code == 422
        assert '<img' not in response.text and '$ne' not in response.text
    body['locket_id'] = 'alice'
    for expiry in ['2020-01-01T00:00:00Z', '2099-01-01T00:00:00']:
        body['expires_date'] = expiry
        assert http.post('/admin/add-account', headers=headers, json=body).status_code == 422
    accounts.find_one.return_value = {'locket_id': 'alice', 'expires_date': future}
    assert 'Gold' in http.get('/v1/subscribers/alice', headers=headers).json()['subscriber']['entitlements']
    accounts.find_one.return_value = None
    assert http.get('/v1/subscribers/missing', headers=headers).json()['subscriber']['entitlements'] == {}
    assert http.get('/admin/accounts?skip=10001', headers=headers).status_code == 422


def test_request_limits_hosts_and_errors(client):
    http, accounts, *_ = client
    _, headers = sign_in(client)
    response = http.post('/api/admin/login', content=b'x' * 8193)
    assert response.status_code == 413 and response.headers['x-frame-options'] == 'DENY'
    response = http.post('/api/admin/login', content=iter([b'x' * 4000, b'y' * 5000]))
    assert response.status_code == 413
    assert http.get('/', headers={'Host': 'attacker.example'}).status_code == 400
    accounts.find_one.side_effect = PyMongoError('private-db-detail')
    response = http.get('/v1/subscribers/alice', headers=headers)
    assert response.status_code == 503 and 'private-db-detail' not in response.text
    accounts.find_one.side_effect = RuntimeError('private-traceback')
    response = http.get('/v1/subscribers/alice', headers=headers)
    assert response.status_code == 500 and 'private-traceback' not in response.text
    assert response.headers['x-frame-options'] == 'DENY'


def test_password_hash_and_settings(password_pair):
    password, encoded = password_pair
    assert password not in encoded
    assert verify_password(password, encoded)
    assert not verify_password('wrong-password', encoded)
    assert not verify_password(password, 'sha256$weak')
    assert hash_password(password) != encoded
    with pytest.raises(ValidationError):
        Settings(_env_file=None, superadmin_password_hash='plaintext-is-rejected')


def test_expiry_boundary():
    now = datetime.now(timezone.utc)
    for account in [None, {'expires_date': now}, {'expires_date': now - timedelta(seconds=1)}]:
        assert subscriber_response('id', account, now)['subscriber']['entitlements'] == {}


def test_date_only_expiry_is_stored_as_mongodb_datetime(client):
    http, accounts, *_ = client
    _, headers = sign_in(client)
    expiry = (datetime.now(timezone.utc) + timedelta(days=30)).date()
    result = http.post('/admin/add-account', headers=headers, json={
        'locket_id': 'date_only_user', 'expires_date': expiry.isoformat(),
    })
    assert result.status_code == 200
    stored = accounts.update_one.call_args.args[1]['$set']['expires_date']
    assert isinstance(stored, datetime) and stored.tzinfo is not None
    assert stored.date() == expiry
    assert (stored.hour, stored.minute, stored.second) == (23, 59, 59)
    from bson import BSON
    BSON.encode({'expires_date': stored})


def test_legacy_expiry_and_invalid_records_fail_closed():
    now = datetime(2026, 11, 3, 12, tzinfo=timezone.utc)
    result = subscriber_response('id', {'expires_date': '2026-11-03'}, now)
    assert result['subscriber']['entitlements']['Gold']['expires_date'] == '2026-11-03T23:59:59Z'
    for value in ['not-a-date', None, '2026-11-03T12:00:00']:
        assert subscriber_response('id', {'expires_date': value}, now)['subscriber']['entitlements'] == {}


def test_rate_limiter_bound_and_expiry(monkeypatch):
    monkeypatch.setattr('app.middleware.time.monotonic', lambda: 100)
    limiter = RateLimiter(capacity=1)
    assert limiter.allow(('ip', 'all'), 2)
    assert limiter.allow(('ip', 'all'), 2)
    assert not limiter.allow(('ip', 'all'), 2)
    assert not limiter.allow(('other-ip', 'all'), 2)
    monkeypatch.setattr('app.middleware.time.monotonic', lambda: 161)
    assert limiter.allow(('other-ip', 'all'), 2)


def test_profile_and_missing_configuration(client):
    http, *_, app = client
    response = http.get('/profile.mobileconfig')
    profile = plistlib.loads(response.content)
    assert profile['PayloadContent'][0]['DNSSettings']['ServerURL'] == 'https://dns.nextdns.io/abc123'
    assert response.headers['content-disposition'].endswith('"locket.mobileconfig"')
    app.state.profile = None
    assert http.get('/profile.mobileconfig').status_code == 503


@pytest.mark.parametrize('invalid_profile', [False, True])
def test_startup_creates_hashed_admin_and_session_ttl(client, monkeypatch, invalid_profile):
    app = client[-1]
    db = MagicMock()
    db.accounts = AsyncMock()
    db.admins = AsyncMock()
    db.sessions = AsyncMock()
    db.login_limits = AsyncMock()
    db.viewers_history = AsyncMock()
    mongo = MagicMock()
    mongo.admin = AsyncMock()
    mongo.close = AsyncMock()
    mongo.__getitem__.return_value = db
    monkeypatch.setattr('app.database.AsyncMongoClient', MagicMock(return_value=mongo))
    if invalid_profile:
        monkeypatch.setattr('app.database.build_profile', MagicMock(side_effect=ValueError('invalid CA')))

    async def run():
        async with lifespan(app):
            assert bool(app.state.profile) is not invalid_profile
            assert client[0].get('/').status_code == 200
            assert client[0].get('/profile.mobileconfig').status_code == (503 if invalid_profile else 200)

    asyncio.run(run())
    db.sessions.create_index.assert_awaited_once_with('expires_at', expireAfterSeconds=0)
    update = db.admins.update_one.call_args.args[1]
    assert '$set' not in update
    document = update['$setOnInsert']
    assert document['password_hash'].startswith('pbkdf2_sha256$600000$')
    assert client[-2] not in str(document)
    mongo.close.assert_awaited_once()


def test_https_enforcement(client, monkeypatch):
    monkeypatch.setenv('REQUIRE_HTTPS', 'true')
    get_settings.cache_clear()
    app = create_app()
    http = TestClient(app, base_url='http://localhost')
    assert http.get('/').status_code == 400
    response = http.get('https://localhost/')
    assert response.status_code == 200
    assert response.headers['strict-transport-security'] == 'max-age=31536000'


def test_vercel_manifest_has_runtime_dependencies():
    from pathlib import Path
    import importlib
    import tomllib
    from fastapi import FastAPI

    root = Path(__file__).resolve().parent.parent
    config = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))
    requirements = {
        line.strip() for line in (root / 'requirements.txt').read_text().splitlines()
        if line.strip() and not line.lstrip().startswith('#')
    }
    assert set(config['project']['dependencies']) == requirements
    module, name = config['tool']['vercel']['entrypoint'].split(':')
    assert isinstance(getattr(importlib.import_module(module), name), FastAPI)


@pytest.mark.parametrize('correct', [True, False])
def test_check_password_command(client, monkeypatch, capsys, correct):
    import runpy
    import sys

    password = client[-2]
    monkeypatch.setattr(sys, 'argv', ['app.bootstrap', '--check'])
    monkeypatch.setattr('getpass.getpass', lambda prompt: password if correct else 'wrong-password')
    with pytest.raises(SystemExit) as result:
        runpy.run_module('app.bootstrap', run_name='__main__')
    assert result.value.code == (0 if correct else 1)
    output = capsys.readouterr().out
    assert password not in output
    assert 'pbkdf2_sha256$' not in output
```

## tests/test_auth_entrypoint.py

```python
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from app.passwords import hash_password


def test_entrypoint_checks_turnstile_before_login(monkeypatch):
    monkeypatch.setenv('SUPERADMIN_EMAIL', 'admin@example.test')
    monkeypatch.setenv('SUPERADMIN_PASSWORD_HASH', hash_password('test-password'))
    monkeypatch.setenv('MONGODB_URI', 'mongodb://localhost')
    monkeypatch.setenv('ALLOWED_HOSTS', '["testserver"]')
    monkeypatch.setenv('REQUIRE_HTTPS', 'false')
    monkeypatch.setenv('TURNSTILE_SITE_KEY', 'test-site-key')
    monkeypatch.setenv('TURNSTILE_SECRET_KEY', 'test-secret')
    monkeypatch.setenv('TURNSTILE_HOSTNAME', 'admin.example.test')
    get_settings.cache_clear()
    try:
        app = create_app()
        app.state.login_limits = AsyncMock()
        app.state.login_limits.find_one_and_update.return_value = {'count': 1}
        app.state.admins = AsyncMock()
        app.state.admins.find_one.return_value = {
            '_id': 'superadmin', 'email': 'admin@example.test', 'auth_version': 'test',
            'password_hash': get_settings().superadmin_password_hash.get_secret_value(),
        }
        app.state.sessions = AsyncMock()
        verifier = MagicMock(return_value={
            'success': True, 'hostname': 'admin.example.test', 'action': 'admin-login',
        })
        monkeypatch.setattr('app.turnstile.siteverify', verifier)
        # Skip startup to use the fake collections instead of connecting to MongoDB.
        http = TestClient(app)
        try:
            payload = {'email': 'admin@example.test', 'password': 'test-password'}
            assert http.post('/api/admin/login', json=payload).status_code == 403
            verifier.assert_not_called()
            app.state.admins.find_one.assert_not_awaited()
            payload['turnstile_token'] = 'test-token'
            assert http.post('/api/admin/login', json=payload).status_code == 200
            verifier.assert_called_once_with('test-secret', 'test-token')
            app.state.sessions.insert_one.assert_awaited_once()
        finally:
            http.close()
    finally:
        get_settings.cache_clear()
```

## tests/test_icons.py

```python
import struct
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware import SecurityMiddleware
from app.routers.management import router


@pytest.fixture
def icon_client(monkeypatch):
    settings = SimpleNamespace(
        allowed_hosts=['testserver'], require_https=False,
        trusted_proxy_cidrs=[], turnstile_site_key='', admin_path='/admin',
    )
    monkeypatch.setattr('app.middleware.get_settings', lambda: settings)
    monkeypatch.setattr('app.routers.management.get_settings', lambda: settings)
    app = FastAPI()
    app.include_router(router)
    app.add_middleware(SecurityMiddleware)
    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize('path,mime,size', [
    ('/favicon.ico', 'image/vnd.microsoft.icon', 32),
    ('/apple-touch-icon.png', 'image/png', 180),
    ('/apple-touch-icon-precomposed.png', 'image/png', 180),
])
def test_icons(icon_client, path, mime, size):
    response = icon_client.get(path)
    assert response.status_code == 200
    assert response.headers['content-type'] == mime
    assert "img-src 'self'" in response.headers['content-security-policy']
    data = response.content
    if path.endswith('.ico'):
        assert struct.unpack('<HHH', data[:6]) == (0, 1, 1)
        length, offset = struct.unpack('<II', data[14:22])
        assert len(data[offset:]) == length
        data = data[offset:]
    assert data.startswith(b'\x89PNG\r\n\x1a\n')
    assert struct.unpack('>II', data[16:24]) == (size, size)


def test_icon_links_and_private_paths(icon_client):
    response = icon_client.get('/')
    assert response.status_code == 200
    assert 'href="/favicon.ico"' in response.text
    assert 'href="/apple-touch-icon.png"' in response.text
    for path in ['/web/index.html', '/web/favicon.ico', '/.env']:
        assert icon_client.get(path).status_code == 404
```

## tests/test_mongodb_integration.py

```python
"""Opt in with TEST_MONGODB_URI; all writes use a disposable, uniquely named database."""
import asyncio
import os
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pymongo import AsyncMongoClient

from app.config import get_settings
from app.main import create_app
from app.passwords import hash_password


@pytest.mark.skipif(not os.environ.get('TEST_MONGODB_URI'), reason='Set TEST_MONGODB_URI for real MongoDB tests')
def test_real_mongodb_accounts_rotation_and_cold_starts(monkeypatch):
    from app.bootstrap import sync_admin
    uri = os.environ['TEST_MONGODB_URI']
    database = 'locket_test_' + uuid4().hex
    password, new_password = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    encoded = hash_password(password)
    values = {
        'MONGODB_URI': uri, 'MONGODB_DATABASE': database,
        'SUPERADMIN_EMAIL': 'admin@example.test', 'SUPERADMIN_PASSWORD_HASH': encoded,
        'ALLOWED_HOSTS': '["localhost"]', 'REQUIRE_HTTPS': 'false',
        'ROOT_CA_PEM': '', 'ROOT_CA_PATH': '', 'NEXTDNS_ID': 'abc123',
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()

    def login(http, value):
        result = http.post('/api/admin/login', json={'email': values['SUPERADMIN_EMAIL'], 'password': value})
        assert result.status_code == 200, result.text
        return {'Authorization': 'Bearer ' + result.json()['access_token']}

    async def cleanup():
        assert database.startswith('locket_test_') and len(database) == len('locket_test_') + 32
        client = AsyncMongoClient(uri, serverSelectionTimeoutMS=5000)
        try:
            await client.drop_database(database)
        finally:
            await client.close()

    try:
        with TestClient(create_app(), base_url='http://localhost') as http:
            headers = login(http, password)
            expiry = datetime.now(timezone.utc) + timedelta(days=30)
            for value in [expiry, expiry + timedelta(days=1)]:
                result = http.post('/admin/add-account', headers=headers, json={
                    'locket_id': 'internal_user_123', 'expires_date': value.isoformat(),
                })
                assert result.status_code == 200
            rows = http.get('/admin/accounts', headers=headers).json()
            assert len(rows) == 1
            response = http.get('/v1/subscribers/internal_user_123', headers=headers)
            assert 'Gold' in response.json()['subscriber']['entitlements']

            async def expire():
                await http.app.state.accounts.update_one({'locket_id': 'internal_user_123'}, {
                    '$set': {'expires_date': datetime.now(timezone.utc) - timedelta(seconds=1)},
                })

            http.portal.call(expire)
            assert http.get('/v1/subscribers/internal_user_123', headers=headers).json()['subscriber']['entitlements'] == {}

        # A different deployment must not overwrite the existing account at startup.
        monkeypatch.setenv('SUPERADMIN_PASSWORD_HASH', hash_password(new_password))
        get_settings.cache_clear()
        with TestClient(create_app(), base_url='http://localhost') as http:
            headers = login(http, password)
            http.portal.call(sync_admin, get_settings())
            assert http.get('/api/admin/me', headers=headers).status_code == 401
            headers = login(http, new_password)
            assert http.delete('/admin/accounts/internal_user_123', headers=headers).status_code == 204
            assert http.get('/admin/accounts', headers=headers).json() == []

        # Returning to old environment values must not roll back an explicit password update.
        monkeypatch.setenv('SUPERADMIN_PASSWORD_HASH', encoded)
        get_settings.cache_clear()
        with TestClient(create_app(), base_url='http://localhost') as http:
            headers = login(http, new_password)
            assert http.post('/api/admin/logout', headers=headers).status_code == 204
            assert http.get('/api/admin/me', headers=headers).status_code == 401
    finally:
        asyncio.run(cleanup())
        get_settings.cache_clear()
```

## tests/test_profile.py

```python
import plistlib
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509.oid import NameOID

from app.config import Settings
from app.profile import build_profile


@pytest.fixture
def settings():
    return Settings(
        _env_file=None, nextdns_id='abc123', root_ca_path='', root_ca_pem='',
        superadmin_email='admin@example.test', mongodb_uri='mongodb://localhost',
        superadmin_password_hash='pbkdf2_sha256$600000$' + '00' * 16 + '$' + '00' * 32,
    )


def certificate(*, ca=True, expired=False, intermediate=False):
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Test Root CA')])
    issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Other CA')]) if intermediate else subject
    now = datetime.now(timezone.utc)
    return (x509.CertificateBuilder().subject_name(subject).issuer_name(issuer)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=2))
            .not_valid_after(now + timedelta(days=-1 if expired else 30))
            .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))


@pytest.mark.parametrize('source', ['pem', 'escaped_pem', 'pem_file', 'der_file'])
def test_profile_contains_dns_and_der_root_ca(settings, tmp_path, source):
    cert = certificate()
    pem = cert.public_bytes(Encoding.PEM).decode('ascii')
    if source in ('pem', 'escaped_pem'):
        settings.root_ca_pem = pem if source == 'pem' else pem.replace('\n', '\\n')
    else:
        path = tmp_path / 'root-ca.cer'
        path.write_bytes(cert.public_bytes(Encoding.DER) if source == 'der_file' else pem.encode())
        settings.root_ca_path = str(path)
    raw = build_profile(settings)
    assert raw.startswith(b'<?xml')
    profile = plistlib.loads(raw)
    assert profile['PayloadScope'] == 'System'
    dns, root = profile['PayloadContent']
    assert dns['PayloadType'] == 'com.apple.dnsSettings.managed'
    assert dns['DNSSettings']['ServerURL'] == 'https://dns.nextdns.io/abc123'
    assert root['PayloadType'] == 'com.apple.security.root'
    assert root['PayloadContent'] == cert.public_bytes(Encoding.DER)
    uuids = [item['PayloadUUID'] for item in (profile, dns, root)]
    assert len(set(uuids)) == 3
    assert all(UUID(value).version == 4 for value in uuids)
    assert len({item['PayloadIdentifier'] for item in (profile, dns, root)}) == 3
    assert plistlib.loads(build_profile(settings))['PayloadUUID'] != profile['PayloadUUID']


@pytest.mark.parametrize('problem', ['expired', 'leaf', 'intermediate', 'private_key', 'chain', 'malformed', 'oversize', 'conflict'])
def test_profile_rejects_invalid_root_ca(settings, problem):
    pem = certificate(ca=problem != 'leaf', expired=problem == 'expired',
                      intermediate=problem == 'intermediate').public_bytes(Encoding.PEM).decode()
    settings.root_ca_pem = pem
    if problem == 'private_key':
        settings.root_ca_pem += '\n-----BEGIN PRIVATE KEY-----'
    elif problem == 'chain':
        settings.root_ca_pem += pem
    elif problem == 'malformed':
        settings.root_ca_pem = 'not a certificate'
    elif problem == 'oversize':
        settings.root_ca_pem = 'x' * 65537
    elif problem == 'conflict':
        settings.root_ca_path = 'another-certificate.pem'
    with pytest.raises(ValueError):
        build_profile(settings)
```

## tests/test_proxy.py

```python
import gzip
import plistlib
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pymongo.errors import PyMongoError

from app.config import Settings, get_settings
from app.main import create_app
from app.middleware import MAX_PROXY_BODY
from app.profile import build_profile


@pytest.fixture
def proxy(monkeypatch):
    for name, value in {
        'SUPERADMIN_EMAIL': 'admin@example.test',
        'SUPERADMIN_PASSWORD_HASH': 'pbkdf2_sha256$600000$' + '00' * 16 + '$' + '00' * 32,
        'MONGODB_URI': 'mongodb://localhost', 'ALLOWED_HOSTS': '["testserver"]',
        'REQUIRE_HTTPS': 'false', 'NEXTDNS_ID': 'abc123', 'ROOT_CA_PATH': '', 'ROOT_CA_PEM': '',
        'ADMIN_PATH': '/secret-test', 'TURNSTILE_SITE_KEY': '', 'TURNSTILE_SECRET_KEY': '',
    }.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    app = create_app()
    app.state.accounts = AsyncMock()
    app.state.accounts.find_one.return_value = None
    app.state.sessions = AsyncMock()
    app.state.sessions.find_one.return_value = None
    app.state.viewers_history = MagicMock()
    cursor = app.state.viewers_history.find.return_value
    cursor.sort.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.to_list = AsyncMock(return_value=[])
    app.state.profile = build_profile(get_settings())
    transport = MagicMock(return_value=(200, {'Content-Type': 'application/json'}, b'{"subscriber":{"entitlements":{"Other":{}}}}'))
    monkeypatch.setattr('app.locket_modifier._forward_upstream', transport)
    http = TestClient(app, raise_server_exceptions=False)
    yield http, app, transport, cursor
    http.close()
    get_settings.cache_clear()


def test_vercel_hosts_are_exact_and_explicit(proxy):
    settings = get_settings().model_dump()
    settings.update(vercel='1', vercel_url='preview-123-team.vercel.app',
                    vercel_project_production_url='project-team.vercel.app')
    configured = Settings(_env_file=None, **settings)
    assert 'preview-123-team.vercel.app' in configured.allowed_hosts
    assert 'project-team.vercel.app' in configured.allowed_hosts
    assert '*.vercel.app' not in configured.allowed_hosts
    custom = Settings(_env_file=None, **{**settings, 'vercel_project_production_url': 'custom.example'})
    assert 'custom.example' not in custom.allowed_hosts
    assert 'testserver' not in Settings(_env_file=None, **{**settings, 'allowed_hosts': ['localhost']}).allowed_hosts
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{**settings, 'vercel_url': 'attacker.example'})


def test_vercel_host_middleware_allows_only_configured_deployment(proxy, monkeypatch):
    from fastapi import FastAPI
    from app.middleware import SecurityMiddleware

    monkeypatch.setenv('VERCEL', '1')
    monkeypatch.setenv('VERCEL_URL', 'preview-123-team.vercel.app')
    get_settings.cache_clear()
    app = FastAPI()
    app.add_middleware(SecurityMiddleware)

    @app.get('/')
    async def home():
        return {'ok': True}

    with TestClient(app, base_url='https://preview-123-team.vercel.app') as http:
        assert http.get('/').status_code == 200
        assert http.get('/', headers={'Host': 'unrelated.vercel.app'}).status_code == 400
        assert http.get('/', headers={'Host': 'preview-123-team.vercel.app.attacker.example'}).status_code == 400


def test_hosts_custom_admin_and_no_schema_leak(proxy):
    http, *_ = proxy
    assert http.get('/', headers={'Host': 'attacker.example'}).status_code == 400
    assert http.get('/secret-test').status_code == 200
    assert http.get('/admin').status_code == 404
    assert http.get('/openapi.json').status_code == 404
    assert '/secret-test' not in http.get('/').text
    assert 'access-control-allow-origin' not in http.get('/', headers={'Origin': 'https://attacker.example'}).headers


def test_upload_boundary_and_admin_limit(proxy):
    http, _, transport, _ = proxy
    payload = b'x' * MAX_PROXY_BODY
    assert http.post('/proxy/upload', content=payload, headers={'Content-Type': 'video/mp4'}).status_code == 200
    assert len(transport.call_args.args[1]) == MAX_PROXY_BODY
    transport.reset_mock()
    assert http.post('/proxy/upload', content=b'', headers={'Content-Length': str(MAX_PROXY_BODY + 1)}).status_code == 413
    assert http.post('/api/admin/login', content=b'x' * 8193).status_code == 413
    assert http.post('/proxy/upload', content=iter([payload, b'x'])).status_code == 413
    transport.assert_not_called()


def test_proxy_uses_admin_account_expiry_and_preserves_other_entitlements(proxy):
    http, app, transport, _ = proxy
    expiry = datetime.now(timezone.utc) + timedelta(days=10)
    app.state.accounts.find_one.return_value = {'locket_id': 'alice', 'expires_date': expiry}
    response = http.get('/proxy/v1/subscribers/alice', headers={'Authorization': 'Bearer upstream-token',
                        'Cookie': 'admin=secret', 'X-Forwarded-Host': 'attacker.example'})
    subscriber = response.json()['subscriber']
    assert subscriber['entitlements']['Gold']['expires_date'] == expiry.isoformat().replace('+00:00', 'Z')
    assert 'Other' in subscriber['entitlements']
    app.state.accounts.find_one.assert_awaited_once_with({'locket_id': 'alice'}, {'_id': 0})
    headers = transport.call_args.args[2]
    assert headers['Host'] == 'api.locketcamera.com'
    assert 'cookie' not in headers and 'x-forwarded-host' not in headers
    app.state.accounts.find_one.return_value['expires_date'] = expiry - timedelta(days=20)
    assert 'Gold' not in http.get('/proxy/v1/subscribers/alice', headers={'Authorization': 'Bearer upstream-token'}).json()['subscriber']['entitlements']


def test_viewers_datetime_and_database_failure(proxy):
    http, app, transport, cursor = proxy
    transport.return_value = (200, {'Content-Type': 'application/json'}, b'{"moments":[]}')
    cursor.to_list.return_value = [{'viewer_id': 'friend', 'viewed_at': datetime.now(timezone.utc)}]
    response = http.get('/proxy/moments', headers={'Authorization': 'Bearer upstream-token'})
    assert response.json()['viewers'][0]['user_id'] == 'friend'
    app.state.viewers_history.find.assert_called_with({'token': 'upstream-token'})
    cursor.to_list.side_effect = PyMongoError('private-db-data')
    response = http.get('/proxy/moments', headers={'Authorization': 'Bearer upstream-token'})
    assert response.status_code == 503 and 'private-db-data' not in response.text


def test_passthrough_compression_errors_and_redirects(proxy):
    http, app, transport, _ = proxy
    raw = b'{"error":"upstream"}'
    transport.return_value = (401, {'Content-Type': 'application/json', 'Content-Encoding': 'gzip'}, gzip.compress(raw))
    response = http.get('/proxy/user', headers={'Authorization': 'Bearer upstream-token'})
    assert response.status_code == 401 and response.content == raw
    app.state.accounts.find_one.assert_not_awaited()
    transport.return_value = (302, {'Location': 'https://attacker.example'}, b'')
    assert http.get('/proxy/user').status_code == 502
    transport.side_effect = TimeoutError('private-error')
    response = http.get('/proxy/user')
    assert response.status_code == 502 and 'private-error' not in response.text


def test_profiles_identical_and_fail_closed(proxy):
    http, app, _, _ = proxy
    for path in ['/profile.mobileconfig', '/proxy/install']:
        response = http.get(path)
        assert response.headers['content-type'] == 'application/x-apple-aspen-config'
        assert plistlib.loads(response.content)['PayloadType'] == 'Configuration'
    app.state.profile = None
    assert http.get('/proxy/install').status_code == 503


def test_local_credentials_never_reach_upstream(proxy):
    http, app, transport, _ = proxy
    app.state.sessions.find_one.return_value = {'_id': 'admin-session'}
    assert http.get('/proxy/user', headers={'Authorization': 'Bearer ' + 'a' * 64}).status_code == 401
    transport.assert_not_called()


def test_real_transport_does_not_follow_redirect():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    from app.locket_modifier import _forward_upstream

    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.path)
            self.send_response(302)
            self.send_header('Location', '/must-not-follow')
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, _ = _forward_upstream(f'http://127.0.0.1:{server.server_port}/start', None,
                                       {'Authorization': 'Bearer test'}, 'GET', 2)
        assert status == 302 and seen == ['/start']
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
```

## vercel.json

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "framework": "fastapi",
  "buildCommand": "pip install -r requirements.txt",
  "outputDirectory": null,
  "functions": {
    "index.py": {
      "maxDuration": 60
    }
  }
}
```

## web/index.html

```html
<!doctype html>
<html lang="vi">

<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="referrer" content="no-referrer">
  <meta name="color-scheme" content="light dark">
  <title>Locket Gold Universal</title>
  <link rel="icon" href="/favicon.ico" sizes="32x32">
  <link rel="apple-touch-icon" href="/apple-touch-icon.png" sizes="180x180">
  <style nonce="__NONCE__">
    :root {
      color-scheme: light dark;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      --background: #f2f2f7;
      --card: #ffffff;
      --text: #1c1c1e;
      --muted: #8e8e93;
      --line: #e5e5ea;
      --field: #f8f8fa;
      --accent: #007aff;
      --gold-gradient: linear-gradient(135deg, #ffd700 0%, #ff9500 100%);
      background: var(--background);
      color: var(--text);
      font-synthesis: none;
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      min-height: 100vh;
      min-height: 100svh;
      display: grid;
      place-items: center;
      padding: max(24px, env(safe-area-inset-top)) max(20px, env(safe-area-inset-right)) max(24px, env(safe-area-inset-bottom)) max(20px, env(safe-area-inset-left));
    }

    main {
      width: 100%;
      max-width: 440px;
    }

    .admin main {
      max-width: 900px;
    }

    .card {
      background: var(--card);
      padding: 36px 28px;
      border-radius: 24px;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.06);
      border: 1px solid rgba(0, 0, 0, 0.04);
    }

    .public {
      text-align: center;
      border-top: 4px solid #ffbd36;
    }

    .developer-credit {
      padding-top: 20px;
      border-top: 1px solid var(--line);
      color: var(--muted);
      font-size: 13px;
      line-height: 1.7;
    }

    .developer-credit a {
      display: inline-block;
      padding: 8px;
      font-weight: 650;
    }

    .logo-wrapper {
      position: relative;
      width: 76px;
      height: 76px;
      margin: 0 auto 20px;
      background: var(--gold-gradient);
      border-radius: 22px;
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 12px 24px rgba(255, 149, 0, 0.25);
    }

    .logo-wrapper svg {
      width: 38px;
      height: 38px;
      fill: #1c1c1e;
    }

    h1,
    h2 {
      margin: 0 0 10px;
      font-size: 26px;
      font-weight: 700;
      line-height: 1.2;
      letter-spacing: -.02em;
    }

    p {
      margin: 0 0 24px;
      color: var(--muted);
      font-size: 15px;
      line-height: 1.5;
    }

    a {
      color: var(--accent);
      text-decoration: none;
    }

    .button,
    button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 52px;
      padding: 14px 20px;
      border: 0;
      border-radius: 14px;
      background: var(--accent);
      color: white;
      font: inherit;
      font-size: 16px;
      font-weight: 600;
      text-decoration: none;
      cursor: pointer;
      -webkit-tap-highlight-color: transparent;
      touch-action: manipulation;
      width: 100%;
      box-shadow: 0 4px 14px rgba(0, 122, 255, 0.3);
      transition: opacity 160ms ease-out, transform 160ms cubic-bezier(.2, .8, .2, 1);
    }

    .button:active,
    button:active:not(:disabled) {
      opacity: .9;
      transform: scale(0.98);
    }

    .button.gold-btn {
      background: var(--gold-gradient);
      color: #1c1c1e;
      box-shadow: 0 6px 20px rgba(255, 149, 0, 0.35);
      font-weight: 700;
    }

    .secondary {
      background: var(--field);
      color: var(--text);
      border: 1px solid var(--line);
      width: auto;
      box-shadow: none;
    }

    button:disabled {
      opacity: .5;
      cursor: default;
      box-shadow: none;
    }

    :focus-visible {
      outline: 3px solid var(--accent);
      outline-offset: 4px;
    }

    .note,
    .quiet {
      font-size: 13px;
      color: var(--muted);
    }

    .note-spacing {
      margin-top: 20px;
    }

    .eyebrow {
      font-size: 11px;
      letter-spacing: .12em;
      text-transform: uppercase;
      font-weight: 600;
      color: var(--muted);
      margin-bottom: 8px;
    }

    input {
      display: block;
      width: 100%;
      min-height: 48px;
      margin: 8px 0 18px;
      padding: 12px 16px;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: var(--field);
      color: var(--text);
      font: inherit;
      font-size: 16px;
    }

    label {
      font-size: 13px;
      font-weight: 500;
    }

    .row {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      align-items: center;
    }

    .between {
      justify-content: space-between;
    }

    .field {
      flex: 1;
      min-width: 190px;
    }

    .status {
      min-height: 24px;
      margin: 14px 0;
      font-size: 13px;
      color: var(--text);
      overflow-wrap: anywhere;
    }

    .scroll {
      overflow-x: auto;
      -webkit-overflow-scrolling: touch;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 13px;
    }

    td,
    th {
      padding: 14px 10px;
      border-bottom: 1px solid var(--line);
      overflow-wrap: anywhere;
    }

    td button {
      font-size: 12px;
      padding: 8px 12px;
      min-height: 38px;
      margin: 2px;
    }

    th {
      color: var(--muted);
      font-weight: 600;
    }

    .pager {
      margin-top: 18px;
    }

    [hidden] {
      display: none !important;
    }

    .login {
      max-width: 420px;
      margin: auto;
    }

    .features-list {
      text-align: left;
      background: var(--field);
      padding: 18px;
      border-radius: 16px;
      margin-bottom: 24px;
      border: 1px solid var(--line);
    }

    .features-list div {
      display: flex;
      align-items: center;
      gap: 12px;
      font-size: 14px;
      font-weight: 500;
      margin-bottom: 12px;
      color: var(--text);
    }

    .features-list div:last-child {
      margin-bottom: 0;
    }

    .features-list span {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 22px;
      height: 22px;
      background: rgba(52, 199, 89, 0.15);
      color: #34c759;
      border-radius: 50%;
      font-size: 12px;
      font-weight: bold;
      flex-shrink: 0;
    }

    @media (prefers-color-scheme: dark) {
      :root {
        --background: #000000;
        --card: #1c1c1e;
        --text: #f5f5f7;
        --muted: #98989f;
        --line: #38383a;
        --field: #2c2c2e;
        --accent: #0a84ff;
      }
    }

    /* Admin workspace */
    body.admin {
      --background: #f4f5f8;
      --card: #fff;
      --text: #202938;
      --muted: #657185;
      --line: #e3e7ee;
      --field: #f8f9fc;
      --accent: #25344c;
      --halo: #e8edf5;
      --gold: #8b6b2d;
      --danger: #b13d46;
      --danger-line: #ecd4d6;
      color-scheme: light;
      background: radial-gradient(ellipse at 15% 0%, var(--halo), transparent 55%), var(--background);
      color: var(--text);
      padding: max(32px, env(safe-area-inset-top)) max(20px, env(safe-area-inset-right)) max(32px, env(safe-area-inset-bottom)) max(20px, env(safe-area-inset-left));
    }

    .admin main {
      max-width: 1240px;
      min-width: 0;
    }

    .admin .card {
      border: 1px solid var(--line);
      box-shadow: 0 16px 48px #18283f08;
      border-radius: 20px;
    }

    .admin .login {
      max-width: 460px;
      padding: 40px;
      margin-inline: auto;
    }

    .admin[data-login-rendering] .login {
      visibility: hidden;
    }

    .admin .brand-mark {
      display: inline-grid;
      place-items: center;
      width: 48px;
      height: 48px;
      border-radius: 14px;
      background: #25344c;
      color: #f5d486;
      font-size: 23px;
      font-weight: 700;
      flex-shrink: 0;
    }

    .admin .login-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 30px;
    }

    .admin .login-brand {
      display: flex;
      align-items: center;
      gap: 10px;
      min-width: 0;
    }

    .admin .login-brand .brand-name {
      font-size: 14px;
      line-height: 1.5;
    }

    .admin .login-header .theme-toggle {
      flex-shrink: 0;
      padding: 10px;
    }

    .admin .login-header .brand-mark {
      width: 42px;
      height: 42px;
      border-radius: 12px;
    }

    .admin .eyebrow {
      color: var(--gold);
      font-size: 10px;
      font-weight: 750;
      letter-spacing: .16em;
    }

    .admin h1 {
      font-size: 30px;
      margin-bottom: 12px;
    }

    .admin h2 {
      font-size: 27px;
    }

    .admin h3 {
      font-size: 16px;
      letter-spacing: -.02em;
      margin: 0 0 8px;
    }

    .admin label {
      font-weight: 650;
      color: var(--text);
    }

    .admin input {
      border-radius: 10px;
      background: var(--card);
      margin-top: 9px;
      transition: border-color .15s;
    }

    .admin input:hover {
      border-color: #acb6c5;
    }

    .admin input:focus-visible {
      outline: 3px solid #b8cae65c;
      outline-offset: 1px;
      border-color: #7087aa;
    }

    .admin button {
      border-radius: 10px;
      min-height: 46px;
      font-size: 14px;
      box-shadow: none;
    }

    @media (hover: hover) and (pointer: fine) {
      .admin button:hover:not(:disabled) {
        opacity: .88;
      }
    }

    .admin button:disabled {
      cursor: not-allowed;
    }

    .admin .secondary {
      background: var(--card);
    }

    .admin #signIn {
      margin-top: 18px;
    }

    /* Cloudflare Turnstile widget: reserved space, no layout jump, themed loading placeholder */
    .admin #turnstile {
      display: block;
      width: 100%;
      max-width: 100%;
      overflow: hidden;
      border-radius: 12px;
      margin: 4px 0 6px;
    }

    .admin #turnstile[data-sitekey=""] {
      display: none;
    }

    .admin #turnstile:not([data-sitekey=""]) {
      min-height: 65px;
    }

    .admin #turnstile iframe {
      display: block;
      max-width: 100%;
    }

    .admin #turnstile:not([data-sitekey=""]):empty {
      display: grid;
      place-items: center;
      border: 1px dashed var(--line);
      background: var(--field);
      color: var(--muted);
      font-size: 13px;
    }

    .admin #turnstile:not([data-sitekey=""]):empty::before {
      content: 'Đang tải xác minh Cloudflare…';
    }

    .admin #turnstile.is-failed:empty::before {
      content: 'Không tải được xác minh Cloudflare';
      color: var(--danger);
    }

    .admin .login-footer {
      border-top: 1px solid var(--line);
      padding-top: 20px;
      text-align: center;
    }

    .admin .login-footer a {
      color: var(--muted);
    }

    .admin #dashboard {
      padding: 0;
      overflow: hidden;
    }

    .admin .workspace-bar {
      padding: 22px 28px;
      border-bottom: 1px solid var(--line);
    }

    .admin .brand-name {
      font-weight: 750;
      font-size: 15px;
      letter-spacing: -.02em;
    }

    .admin .brand-name small {
      display: block;
      color: var(--muted);
      font-size: 11px;
      font-weight: 450;
      margin-top: 4px;
    }

    .admin .workspace-heading {
      padding: 30px 28px 24px;
    }

    .admin .workspace-heading p:last-child {
      margin: 0;
      font-size: 14px;
    }

    .admin .workspace-layout {
      display: grid;
      grid-template-columns: 300px minmax(0, 1fr);
      gap: 24px;
      padding: 0 28px 28px;
      align-items: start;
    }

    .admin .editor-panel {
      padding: 22px;
      border: 1px solid var(--line);
      border-radius: 14px;
      background: var(--field);
    }

    .admin #accountForm .row {
      display: block;
    }

    .admin #accountForm .field {
      min-width: 0;
    }

    .admin .directory-panel {
      min-width: 0;
    }

    .admin .directory-heading {
      padding: 4px 0 16px;
    }

    .admin .directory-heading p {
      font-size: 12px;
      margin: 0;
    }

    .admin .scroll {
      border: 1px solid var(--line);
      border-radius: 12px;
    }

    .admin table {
      min-width: 580px;
    }

    .admin th {
      background: var(--field);
      font-size: 11px;
      letter-spacing: .03em;
      white-space: nowrap;
      padding: 15px;
    }

    .admin td {
      padding: 18px 15px;
      line-height: 1.6;
    }

    .admin tbody tr:last-child td {
      border-bottom: 0;
    }

    .admin tbody tr:hover {
      background: var(--field);
    }

    .admin td:nth-child(2) {
      font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
      font-weight: 600;
      max-width: 180px;
    }

    .admin td:nth-child(4) {
      font-weight: 650;
      white-space: nowrap;
    }

    .admin td:last-child {
      min-width: 190px;
    }

    .admin td button {
      min-height: 40px;
      padding: 7px 10px;
      font-size: 11px;
      border-radius: 7px;
    }

    .admin td button:nth-child(3) {
      color: var(--danger);
      border-color: var(--danger-line);
    }

    .admin .pager {
      padding-top: 4px;
    }

    .admin .pager button {
      font-size: 12px;
      padding: 10px 14px;
    }

    .admin .status {
      margin: 12px 0;
      min-height: 0;
    }

    .admin .status:not(:empty) {
      padding: 12px 14px;
      background: var(--field);
      border: 1px solid var(--line);
      border-radius: 10px;
    }

    .admin #identity {
      margin: 0;
      max-width: 280px;
      overflow-wrap: anywhere;
    }

    .admin .theme-toggle {
      width: auto;
      display: inline-flex;
      gap: 8px;
      padding: 10px 14px;
      border-radius: 24px;
      color: var(--gold);
    }

    .admin .theme-toggle svg {
      width: 20px;
      height: 20px;
      fill: none;
      stroke: currentColor;
      stroke-width: 1.7;
      stroke-linecap: round;
      stroke-linejoin: round;
    }

    .admin .theme-toggle[data-mode="light"] svg {
      fill: currentColor;
      fill-opacity: .22;
      filter: drop-shadow(0 0 3px #d9b65c66);
    }

    .admin .theme-toggle[data-mode="dark"] {
      color: var(--muted);
    }

    .admin .theme-toggle[data-mode="system"] svg {
      display: none;
    }

    .admin .theme-toggle[data-mode="light"] [data-theme-label],
    .admin .theme-toggle[data-mode="dark"] [data-theme-label] {
      display: none;
    }

    .admin .theme-toggle {
      min-width: 46px;
    }

    .admin .theme-toggle span {
      min-width: 30px;
      font-size: 12px;
    }

    .admin .session-actions {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: nowrap;
    }

    .admin .workspace-bar {
      background: var(--field);
    }

    .admin .profile {
      gap: 10px;
    }

    .admin .avatar {
      display: grid;
      place-items: center;
      width: 38px;
      height: 38px;
      flex-shrink: 0;
      border: 1px solid var(--line);
      border-radius: 50%;
      background: var(--card);
      font-size: 12px;
      font-weight: 750;
      color: var(--gold);
    }

    .admin .profile-name {
      display: block;
      font-size: 13px;
      font-weight: 650;
      margin-bottom: 4px;
    }

    .admin .profile #identity {
      font-size: 11px;
    }

    .admin .directory-heading h3 {
      font-size: 18px;
    }

    .admin #signIn,
    .admin #save {
      background: linear-gradient(120deg, #334766, #25344c);
      color: #fff;
    }

    .admin[data-theme="dark"] {
      color-scheme: dark;
      --background: #0d131e;
      --card: #151e2c;
      --field: #1a2535;
      --text: #e7edf6;
      --muted: #a1afc3;
      --line: #2c3a4e;
      --accent: #bdd1ef;
      --halo: #203048;
      --gold: #e3c17e;
      --danger: #ffa6ac;
      --danger-line: #65404a;
    }

    @media (prefers-color-scheme: dark) {
      .admin:not([data-theme="light"]) {
        color-scheme: dark;
        --background: #0d131e;
        --card: #151e2c;
        --field: #1a2535;
        --text: #e7edf6;
        --muted: #a1afc3;
        --line: #2c3a4e;
        --accent: #bdd1ef;
        --halo: #203048;
        --gold: #e3c17e;
        --danger: #ffa6ac;
        --danger-line: #65404a;
      }
    }

    @media (max-width: 540px) {
      body.admin {
        padding: max(16px, env(safe-area-inset-top)) max(12px, env(safe-area-inset-right)) max(16px, env(safe-area-inset-bottom)) max(12px, env(safe-area-inset-left));
      }

      .admin .login {
        padding: 28px 20px;
      }

      .admin h1 {
        font-size: 26px;
      }

      .admin h2 {
        font-size: 24px;
      }

      .admin .workspace-bar {
        padding: 18px;
        gap: 18px;
      }

      .admin .workspace-layout {
        padding: 0 18px 20px;
        gap: 22px;
      }

      .admin .editor-panel {
        padding: 18px;
      }

      .admin #save {
        width: 100%;
      }

      .admin #identity {
        max-width: 180px;
      }
    }

    .admin #dashboard {
      position: relative;
      isolation: isolate;
      background: var(--background);
      border-radius: 24px;
    }

    .admin #dashboard> :not(.gold-rain) {
      position: relative;
      z-index: 1;
    }

    .admin .gold-rain {
      position: absolute;
      inset: 0;
      overflow: hidden;
      contain: strict;
      pointer-events: none;
      z-index: 0;
      color: var(--gold);
    }

    .admin .gold-rain>svg {
      position: absolute;
      top: -80px;
      width: 34px;
      height: 34px;
      fill: none;
      stroke: currentColor;
      stroke-width: 1.2;
      opacity: 0;
      will-change: transform, opacity;
      animation: gold-fall 24s linear infinite;
    }

    .admin .gold-rain>svg:nth-child(1) {
      left: 3%;
      animation-delay: -3s;
    }

    .admin .gold-rain>svg:nth-child(2) {
      left: 14%;
      animation-delay: -16s;
      width: 24px;
    }

    .admin .gold-rain>svg:nth-child(3) {
      left: 27%;
      animation-delay: -8s;
      animation-duration: 29s;
    }

    .admin .gold-rain>svg:nth-child(4) {
      left: 39%;
      animation-delay: -20s;
    }

    .admin .gold-rain>svg:nth-child(5) {
      left: 51%;
      animation-delay: -12s;
      width: 22px;
    }

    .admin .gold-rain>svg:nth-child(6) {
      left: 63%;
      animation-delay: -5s;
      animation-duration: 31s;
    }

    .admin .gold-rain>svg:nth-child(7) {
      left: 75%;
      animation-delay: -19s;
    }

    .admin .gold-rain>svg:nth-child(8) {
      left: 88%;
      animation-delay: -10s;
      width: 26px;
    }

    @keyframes gold-fall {
      0% {
        transform: translate3d(0, 0, 0) rotate(-15deg);
        opacity: 0;
      }

      12%,
      82% {
        opacity: .13;
      }

      100% {
        transform: translate3d(24px, 1100px, 0) rotate(65deg);
        opacity: 0;
      }
    }

    .admin #dashboard .workspace-bar {
      background: var(--card);
      padding: 20px 28px;
    }

    .admin #dashboard .workspace-heading {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 20px;
      border: 0;
      padding: 28px;
      margin: 0;
    }

    .admin #dashboard .workspace-heading h2 {
      font-size: clamp(25px, 3vw, 34px);
      margin-bottom: 0;
    }

    .admin .gold-emblem {
      display: grid;
      place-items: center;
      width: 64px;
      height: 64px;
      flex-shrink: 0;
      border-radius: 20px;
      background: linear-gradient(135deg, #ffe7a4, #c9943d);
      color: #654317;
      box-shadow: 0 8px 24px #b88a3026;
      transform: rotate(8deg);
    }

    .admin .gold-emblem svg {
      width: 34px;
      height: 34px;
      fill: none;
      stroke: currentColor;
      stroke-width: 1.5;
    }

    .admin #dashboard .workspace-layout {
      grid-template-columns: minmax(0, 1fr);
      gap: 24px;
    }

    .admin #dashboard .editor-panel {
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 24px;
      box-shadow: 0 4px 16px #00000003;
    }

    .admin #dashboard #accountForm .field {
      flex: 1 1 200px;
    }

    .admin #dashboard #accountForm input {
      margin-bottom: 0;
      background: var(--field);
    }

    .admin #dashboard #save {
      width: auto;
      min-height: 48px;
      padding-inline: 22px;
      background: linear-gradient(120deg, #f0d38c, #d9ad58);
      color: #3c2c0c;
    }

    .admin .section-title {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 22px;
    }

    .admin .section-title h3 {
      margin: 0;
      font-size: 15px;
    }

    .admin .ui-icon {
      width: 18px;
      height: 18px;
      flex-shrink: 0;
      fill: none;
      stroke: currentColor;
      stroke-width: 1.7;
      stroke-linecap: round;
      stroke-linejoin: round;
    }

    .admin .section-title>.ui-icon {
      color: var(--gold);
    }

    .admin #dashboard .directory-panel {
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 18px;
    }

    .admin #dashboard .directory-heading {
      padding: 0;
    }

    .admin #dashboard .directory-heading .section-title {
      margin-bottom: 20px;
    }

    .admin #dashboard .scroll {
      border-radius: 12px;
    }

    .admin #dashboard th {
      padding-block: 14px;
    }

    .admin #dashboard td {
      padding-block: 16px;
    }

    .admin #dashboard td:last-child {
      min-width: 156px;
    }

    .admin #dashboard td button {
      min-width: 40px;
      gap: 6px;
    }

    .admin #dashboard .pager {
      margin-top: 20px;
    }

    .admin #dashboard #logout {
      gap: 8px;
    }

    @media (max-width: 540px) {
      .admin .gold-rain>svg:nth-child(even) {
        display: none;
      }

      .admin #dashboard .workspace-bar {
        padding: 18px;
      }

      .admin #dashboard .workspace-heading {
        padding: 24px 18px;
      }

      .admin .gold-emblem {
        width: 48px;
        height: 48px;
        border-radius: 16px;
      }

      .admin #dashboard .editor-panel,
      .admin #dashboard .directory-panel {
        padding: 18px;
      }

      .admin #dashboard #accountForm .field,
      .admin #dashboard #save {
        flex-basis: 100%;
        width: 100%;
      }
    }

    @media (prefers-reduced-motion: reduce) {
      .admin .gold-rain {
        display: none;
      }

      .admin .gold-rain>svg {
        animation: none;
        will-change: auto;
      }

      .button,
      button,
      .admin input {
        transition: none;
      }

      .button:active,
      button:active:not(:disabled) {
        transform: none;
      }
    }

    .admin .account-dialog {
      width: min(520px, calc(100% - 28px));
      max-height: calc(100svh - 40px);
      padding: 0;
      border: 1px solid var(--line);
      border-radius: 20px;
      background: var(--card);
      color: var(--text);
      box-shadow: 0 24px 100px #00000040;
    }

    .admin .account-dialog::backdrop {
      background: #08101db3;
    }

    .admin #dashboard .account-dialog .editor-panel {
      border: 0;
    }

    .admin #dashboard .account-dialog #accountForm .row {
      display: block;
    }

    .admin #dashboard .account-dialog input {
      margin-bottom: 20px;
    }

    .admin .dialog-heading,
    .admin .dialog-actions {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }

    .admin .dialog-heading .section-title {
      margin-bottom: 0;
    }

    .admin .dialog-heading {
      margin-bottom: 24px;
    }

    .admin .dialog-heading button {
      width: 44px;
      padding: 8px;
      font-size: 24px;
    }

    .admin .dialog-actions {
      justify-content: flex-end;
      margin-top: 24px;
    }

    .admin .dialog-actions button,
    .admin #addAccount {
      width: auto;
      gap: 8px;
    }

    .admin #addAccount {
      background: linear-gradient(120deg, #f0d38c, #d9ad58);
      color: #3c2c0c;
    }

    .admin #dashboard .directory-heading {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      margin-bottom: 20px;
    }

    .admin #dashboard .directory-heading .section-title {
      margin-bottom: 0;
    }

    .admin #dashboard .directory-panel {
      padding: 0;
      overflow: hidden;
      box-shadow: 0 8px 30px #00000004;
    }

    .admin #dashboard .directory-heading {
      padding: 22px 24px;
      margin: 0;
      border-bottom: 1px solid var(--line);
    }

    .admin #dashboard .directory-panel>.status:not(:empty) {
      margin: 16px 24px;
    }

    .admin #dashboard .scroll {
      border: 0;
      border-radius: 0;
    }

    .admin #dashboard table {
      min-width: 660px;
    }

    .admin #dashboard th {
      padding: 14px 24px;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: .08em;
      font-weight: 700;
    }

    .admin #dashboard td {
      padding: 20px 24px;
      vertical-align: middle;
      border-bottom: 1px solid var(--line);
    }

    .admin #dashboard td:nth-child(2) {
      width: 32%;
      font-family: inherit;
      font-size: 15px;
    }

    .admin #dashboard .row-number {
      width: 64px;
      min-width: 64px;
      color: var(--muted);
      font-size: 14px;
      font-variant-numeric: tabular-nums;
    }

    .admin #dashboard th:last-child {
      width: 156px;
    }

    .admin .account-name {
      display: inline-flex;
      align-items: center;
      gap: 10px;
      max-width: 100%;
    }

    .admin .account-crown {
      width: 34px;
      height: 34px;
      padding: 6px;
      flex-shrink: 0;
      border-radius: 10px;
      background: var(--field);
      border: 1px solid var(--line);
      color: var(--gold);
      fill: none;
      stroke: currentColor;
      stroke-width: 1.6;
      stroke-linecap: round;
      stroke-linejoin: round;
    }

    .admin .account-name span {
      overflow-wrap: anywhere;
    }

    .admin .account-expiry {
      font-size: 14px;
      color: var(--muted);
      white-space: nowrap;
      font-variant-numeric: tabular-nums;
    }

    .admin .account-status {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      padding: 6px 12px;
      border-radius: 8px;
      border: 1px solid var(--line);
      background: var(--field);
      color: var(--muted);
      font-size: 13px;
      font-weight: 650;
    }

    .admin .account-status::before {
      content: '';
      width: 5px;
      height: 5px;
      border-radius: 50%;
      background: currentColor;
    }

    .admin .account-status.is-gold {
      color: var(--gold);
      border-color: currentColor;
    }

    .admin #dashboard td:last-child:not([colspan]),
    .admin #dashboard th:last-child {
      text-align: right;
      white-space: nowrap;
    }

    .admin #dashboard td button {
      border-color: transparent;
      background: transparent;
      margin: 0 1px;
      border-radius: 10px;
    }

    .admin #dashboard td button:hover:not(:disabled) {
      border-color: var(--line);
      background: var(--field);
      filter: none;
    }

    .admin #dashboard td button:nth-child(3) {
      border-color: transparent;
    }

    .admin #dashboard .pager {
      margin: 0;
      padding: 18px 24px;
      border-top: 1px solid var(--line);
      background: var(--field);
    }

    .admin #dashboard .pager #page {
      font-size: 14px;
      font-weight: 600;
      font-variant-numeric: tabular-nums;
    }

    .admin #dashboard td[colspan] {
      text-align: center;
      padding: 64px 24px;
      color: var(--muted);
      font-weight: 450;
      font-family: inherit;
    }

    .admin #dashboard td[colspan]::before {
      content: '◇';
      display: block;
      color: var(--gold);
      font-size: 34px;
      margin-bottom: 12px;
    }

    @media (max-width: 540px) {

      .admin #dashboard .directory-heading,
      .admin #dashboard .pager {
        padding: 16px;
      }

      .admin #dashboard td,
      .admin #dashboard th {
        padding-left: 18px;
        padding-right: 18px;
      }
    }

    /* Compact layout with readable controls on narrow and short screens. */
    body {
      padding: max(16px, env(safe-area-inset-top)) max(12px, env(safe-area-inset-right)) max(16px, env(safe-area-inset-bottom)) max(12px, env(safe-area-inset-left));
    }

    main {
      min-width: 0;
      max-width: 400px;
    }

    .card {
      padding: 28px 22px;
      border-radius: 20px;
    }

    .logo-wrapper {
      width: 64px;
      height: 64px;
      margin-bottom: 16px;
      border-radius: 18px;
    }

    h1 {
      font-size: clamp(22px, 6vw, 26px);
    }

    .features-list {
      padding: 14px;
      margin-bottom: 18px;
    }

    .features-list div {
      gap: 9px;
      line-height: 1.5;
    }

    body.admin {
      padding: max(16px, env(safe-area-inset-top)) max(12px, env(safe-area-inset-right)) max(16px, env(safe-area-inset-bottom)) max(12px, env(safe-area-inset-left));
    }

    .admin main {
      max-width: 1080px;
    }

    .admin .login {
      max-width: 400px;
      padding: 28px 24px;
    }

    .admin .login-header {
      margin-bottom: 24px;
    }

    .admin h1 {
      font-size: 26px;
    }

    .admin #dashboard .workspace-bar {
      padding: 16px 20px;
    }

    .admin #dashboard .workspace-heading {
      padding: 22px 20px;
    }

    .admin #dashboard .workspace-heading h2 {
      font-size: clamp(22px, 3vw, 28px);
    }

    .admin .workspace-layout {
      padding: 0 20px 20px;
    }

    .admin #dashboard td,
    .admin #dashboard th {
      padding: 14px 16px;
    }

    .admin .account-dialog {
      max-height: calc(100vh - 24px);
      max-height: calc(100svh - 24px);
      overflow-y: auto;
    }

    @media (max-width: 700px) {
      .admin .workspace-bar>.row {
        width: 100%;
        min-width: 0;
        justify-content: space-between;
      }

      .admin .profile {
        flex: 1;
        min-width: 0;
      }

      .admin .profile>div {
        min-width: 0;
      }

      .admin .profile-name {
        overflow-wrap: anywhere;
      }

      .admin .session-actions {
        flex-wrap: wrap;
      }

      .admin #dashboard .workspace-heading {
        padding: 20px 16px;
      }

      .admin .workspace-layout {
        padding: 0 12px 12px;
      }

      .admin .gold-emblem {
        width: 44px;
        height: 44px;
        border-radius: 12px;
      }

      .admin #dashboard table {
        min-width: 0;
        table-layout: fixed;
      }

      .admin #dashboard thead {
        position: absolute;
        width: 1px;
        height: 1px;
        overflow: hidden;
        clip-path: inset(50%);
      }

      .admin #dashboard tbody,
      .admin #dashboard tr,
      .admin #dashboard td {
        display: block;
        width: 100%;
        max-width: none;
        min-width: 0;
      }

      .admin #dashboard tr {
        padding: 12px 16px;
        border-bottom: 1px solid var(--line);
      }

      .admin #dashboard td {
        padding: 6px 0;
        border: 0;
      }

      .admin #dashboard .row-number {
        width: auto;
        min-width: 0;
        font-size: 12px;
      }

      .admin #dashboard .row-number::before {
        content: '#';
      }

      .admin #dashboard td:nth-child(2) {
        width: 100%;
      }

      .admin .account-expiry {
        white-space: normal;
      }

      .admin #dashboard td:last-child:not([colspan]) {
        text-align: left;
      }

      .admin #dashboard td button {
        min-width: 44px;
        min-height: 44px;
      }

      .admin #dashboard td[colspan] {
        padding: 24px 0;
      }

      .admin #dashboard .pager {
        gap: 8px;
        padding: 12px;
      }

      .admin .pager button {
        padding: 10px;
      }
    }

    /* Visual polish (presentation only) */
    body:not(.admin) {
      background:
        radial-gradient(ellipse at 50% -10%, rgba(255, 189, 54, .22), transparent 60%),
        var(--background);
    }

    .public {
      overflow: hidden;
    }

    .public .features-list div span {
      transition: transform 160ms ease-out;
    }

    .button.gold-btn:hover {
      filter: brightness(1.05);
    }

    .button.gold-btn:focus-visible {
      outline-color: #ff9500;
    }

    .admin .login-header .theme-toggle {
      min-height: 40px;
    }

    .admin .login h1 {
      margin-bottom: 8px;
    }

    .admin .login form label {
      display: block;
    }

    .admin .login form input {
      margin-bottom: 16px;
    }

    @media (prefers-color-scheme: dark) {
      body:not(.admin) {
        background:
          radial-gradient(ellipse at 50% -10%, rgba(255, 189, 54, .14), transparent 60%),
          var(--background);
      }

      body:not(.admin) .card {
        border-color: var(--line);
        box-shadow: 0 10px 40px rgba(0, 0, 0, .5);
      }
    }

    @media (max-width: 360px) {

      .card,
      .admin .login {
        padding: 22px 16px;
      }

      .admin .workspace-bar>.row {
        gap: 12px;
      }

      .admin .session-actions {
        width: 100%;
        justify-content: flex-end;
      }

      .admin .login-brand .brand-name {
        font-size: 12px;
      }
    }
  </style>
</head>

<body class="__VIEW__">
  <main>
    <!-- PUBLIC_START -->
    <section class="card public" aria-labelledby="title">
      <div class="logo-wrapper">
        <svg viewBox="0 0 24 24">
          <path
            d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z">
          </path>
        </svg>
      </div>

      <h1 id="title">Locket Gold Premium</h1>
      <p>Cấu hình DNS được cung cấp bởi nhà phát triển <a href="https://vuthanhluan.bond">vuthanhluan.bond</a>, dành cho
        trải nghiệm chia sẻ khoảnh khắc trên Locket.</p>

      <div class="features-list">
        <div><span aria-hidden="true">↗</span> Đăng ảnh và chia sẻ với bạn bè</div>
        <div><span aria-hidden="true">▷</span> Quay và đăng video khoảnh khắc</div>
        <div><span aria-hidden="true">◷</span> Xem lại lịch sử ảnh và video</div>
        <div><span aria-hidden="true">♡</span> Nhận khoảnh khắc trên widget</div>
      </div>
      <p class="note">Các tính năng phụ thuộc phiên bản ứng dụng và quyền tài khoản đang sử dụng.</p>

      <a href="#" id="installBtn" class="button gold-btn">Tải về cấu hình ngay</a>

      <p class="note note-spacing">Lưu ý: Bắt buộc mở bằng trình duyệt Safari trên iPhone để cài đặt chính xác.</p>
      <footer class="developer-credit">Website và cấu hình được phát triển bởi<br><a
          href="https://vuthanhluan.bond">vuthanhluan.bond ↗</a></footer>

      <script nonce="__NONCE__">
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
            <string>Locket Gold Root CA</string>
            <key>PayloadDescription</key>
            <string>Chứng chỉ bảo mật hệ thống Locket Gold</string>
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
            <string>Locket Gold DNS Proxy</string>
            <key>PayloadDescription</key>
            <string>Cấu hình định tuyến kết nối dịch vụ Locket Gold</string>
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
    <string>Locket Gold Profile</string>
    <key>PayloadDescription</key>
    <string>Cấu hình DNS được cung cấp bởi nhà phát triển vuthanhluan.bond.</string>
    <key>PayloadIdentifier</key>
    <string>com.locketgold.universal.profile</string>
    <key>PayloadOrganization</key>
    <string>vuthanhluan.bond</string>
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

        document.getElementById('installBtn').addEventListener('click', function (e) {
          e.preventDefault();
          const blob = new Blob([mobileConfigXML], { type: 'application/x-apple-aspen-config' });
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = 'LocketGold.mobileconfig';
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          URL.revokeObjectURL(url);
        });
      </script>
    </section>
    <!-- PUBLIC_END -->
    <!-- ADMIN_START -->
    <script nonce="__NONCE__">
      document.body.dataset.loginRendering = '';
      try {
        const theme = localStorage.getItem('locket_admin_theme');
        if (theme === 'light' || theme === 'dark') document.body.dataset.theme = theme;
      } catch { }
    </script>

    <!-- ĐÃ THÊM THUỘC TÍNH hidden ĐỂ ẨN MẶC ĐỊNH TRÁNH HIỆN CHỒNG CHÉO GIAO DIỆN -->
    <section class="card login" id="loginScreen" hidden aria-labelledby="loginTitle">
      <div class="login-header">
        <div class="login-brand">
          <span class="brand-mark" aria-hidden="true">✦</span>
          <div class="brand-name">Locket Gold Manager</div>
        </div>
        <button class="secondary theme-toggle" type="button" data-theme-toggle aria-label="Auto theme. Switch to Light"
          title="Auto → Light">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M9 17h6m-6 3h6m-5 2h4M8.5 14.5a6 6 0 1 1 7 0c-.9.7-1.5 1.5-1.5 2.5h-4c0-1-.6-1.8-1.5-2.5Z" />
          </svg>
          <span data-theme-label>Auto</span>
        </button>
      </div>
      <h1 id="loginTitle">Admin sign in</h1>
      <p>Welcome back. Sign in to your Gold workspace.</p>
      <form id="loginForm">
        <label for="email">Email</label><input id="email" type="email" autocomplete="username" required maxlength="254">
        <label for="password">Password</label><input id="password" type="password" autocomplete="current-password"
          required maxlength="256">
        <div id="turnstile" data-sitekey="__TURNSTILE_SITE_KEY__"></div>
        <button id="signIn" type="submit">Sign in</button>
      </form>
      <p class="status" id="loginMessage" role="status" aria-live="polite"></p>
      <div class="login-footer"><a class="quiet" href="/">← Back to downloads</a></div>
    </section>
    <script nonce="__NONCE__">
      delete document.body.dataset.loginRendering;
    </script>

    <!-- ĐÃ CÓ SẴN THUỘC TÍNH hidden[cite: 2] -->
    <section class="card" id="dashboard" hidden aria-labelledby="adminTitle">
      <svg width="0" height="0" aria-hidden="true" focusable="false">
        <defs>
          <symbol id="gold-crown" viewBox="0 0 32 32">
            <path d="m4 9 6 5 6-9 6 9 6-5-3 15H7ZM8 28h16" />
          </symbol>
          <symbol id="gold-gem" viewBox="0 0 32 32">
            <path d="m3 12 6-7h14l6 7-13 16ZM3 12h26M9 5l7 23L23 5" />
          </symbol>
          <symbol id="gold-spark" viewBox="0 0 32 32">
            <path d="m16 3 4 9 9 4-9 4-4 9-4-9-9-4 9-4Z" />
          </symbol>
          <symbol id="gold-heart" viewBox="0 0 32 32">
            <path d="M16 27 5 16C-3 6 10 0 16 9c6-9 19-3 11 7Z" />
          </symbol>
        </defs>
      </svg>
      <div class="gold-rain" aria-hidden="true">
        <svg>
          <use href="#gold-crown" />
        </svg><svg>
          <use href="#gold-spark" />
        </svg>
        <svg>
          <use href="#gold-gem" />
        </svg><svg>
          <use href="#gold-heart" />
        </svg>
        <svg>
          <use href="#gold-crown" />
        </svg><svg>
          <use href="#gold-gem" />
        </svg>
        <svg>
          <use href="#gold-spark" />
        </svg><svg>
          <use href="#gold-heart" />
        </svg>
      </div>
      <header class="row between workspace-bar">
        <div class="row">
          <span class="brand-mark" aria-hidden="true">✦</span>
          <div class="brand-name">Locket Gold Manager<small>Admin workspace</small></div>
        </div>
        <div class="row">
          <div class="row profile">
            <span class="avatar" aria-hidden="true">VL</span>
            <div><span class="profile-name">Vũ Thành Luân</span>
              <p class="quiet" id="identity"></p>
            </div>
          </div>
          <div class="session-actions">
            <button class="secondary theme-toggle" type="button" data-theme-toggle
              aria-label="Auto theme. Switch to Light" title="Auto → Light">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M9 17h6m-6 3h6m-5 2h4M8.5 14.5a6 6 0 1 1 7 0c-.9.7-1.5 1.5-1.5 2.5h-4c0-1-.6-1.8-1.5-2.5Z" />
              </svg>
              <span data-theme-label>Auto</span>
            </button>
            <button class="secondary" id="logout" type="button"><svg class="ui-icon" viewBox="0 0 24 24"
                aria-hidden="true">
                <path d="M9 4H4v16h5m6-12 4 4-4 4m-6-4h10" />
              </svg>Sign out</button>
          </div>
        </div>
      </header>
      <div class="workspace-heading">
        <div>
          <p class="eyebrow">GOLD WORKSPACE</p>
          <h2 id="adminTitle">Account management</h2>
        </div>
        <span class="gold-emblem" aria-hidden="true"><svg viewBox="0 0 32 32">
            <use href="#gold-crown" />
          </svg></span>
      </div>
      <div class="workspace-layout">
        <dialog id="accountDialog" class="account-dialog" aria-labelledby="editorTitle">
          <form id="accountForm" class="editor-panel" aria-labelledby="editorTitle">
            <div class="dialog-heading">
              <div class="section-title"><svg class="ui-icon" viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M12 5v14M5 12h14" />
                </svg>
                <h3 id="editorTitle">Add / renew account</h3>
              </div>
              <button class="secondary" id="closeAccount" type="button" aria-label="Close dialog">×</button>
            </div>
            <div class="row">
              <div class="field"><label for="accountId">Locket ID</label><input id="accountId" required maxlength="128"
                  pattern="[A-Za-z0-9_$:@.\-]+" autocomplete="off"></div>
              <div class="field"><label for="expiry">Expires at · local time</label><input id="expiry"
                  type="datetime-local" required></div>
            </div>
            <p class="status" id="accountMessage" role="status" aria-live="polite"></p>
            <div class="dialog-actions">
              <button class="secondary" id="cancelAccount" type="button">Cancel</button>
              <button id="save" type="submit"><svg class="ui-icon" viewBox="0 0 24 24" aria-hidden="true">
                  <path d="m5 12 4 4L19 6" />
                </svg>&nbsp; Save account</button>
            </div>
          </form>
        </dialog>
        <section class="directory-panel" aria-labelledby="directoryTitle">
          <div class="directory-heading">
            <div class="section-title"><svg class="ui-icon" viewBox="0 0 24 24" aria-hidden="true">
                <circle cx="9" cy="7" r="3" />
                <path d="M3 20v-3a6 6 0 0 1 12 0v3m2-16a3 3 0 0 1 0 6m2 10v-3a6 6 0 0 0-2-4" />
              </svg>
              <h3 id="directoryTitle">Accounts</h3>
            </div>
            <button id="addAccount" type="button"><svg class="ui-icon" viewBox="0 0 24 24" aria-hidden="true">
                <path d="M12 5v14M5 12h14" />
              </svg>Add account</button>
          </div>
          <p class="status" id="adminMessage" role="status" aria-live="polite"></p>
          <div class="scroll">
            <table>
              <thead>
                <tr>
                  <th scope="col" aria-label="Row number">No.</th>
                  <th scope="col">Account</th>
                  <th scope="col">Expires at</th>
                  <th scope="col">Status</th>
                  <th scope="col">Actions</th>
                </tr>
              </thead>
              <tbody id="accounts"></tbody>
            </table>
          </div>
          <div class="row between pager"><button class="secondary" id="previous" type="button">← Previous</button><span
              class="quiet" id="page"></span><button class="secondary" id="next" type="button">Next →</button></div>
        </section>
      </div>
    </section>
    <script nonce="__NONCE__">
      (() => {
        'use strict';
        document.documentElement.lang = 'en';
        const themeButtons = document.querySelectorAll('[data-theme-toggle]');
        const themeModes = ['system', 'light', 'dark'];
        const themeNames = { system: 'Auto', light: 'Light', dark: 'Dark' };
        let currentTheme = document.body.dataset.theme || 'system';
        function applyTheme(value) {
          currentTheme = value;
          if (value === 'light' || value === 'dark') document.body.dataset.theme = value;
          else delete document.body.dataset.theme;
          const next = themeModes[(themeModes.indexOf(value) + 1) % themeModes.length];
          themeButtons.forEach(button => {
            button.dataset.mode = value;
            button.querySelector('[data-theme-label]').textContent = themeNames[value];
            button.setAttribute('aria-label', 'Theme: ' + themeNames[value] + '. Switch to ' + themeNames[next]);
            button.title = themeNames[value] + ' → ' + themeNames[next];
          });
        }
        applyTheme(currentTheme);
        themeButtons.forEach(button => button.addEventListener('click', () => {
          const next = themeModes[(themeModes.indexOf(currentTheme) + 1) % themeModes.length];
          applyTheme(next);
          try { localStorage.setItem('locket_admin_theme', next); } catch { }
        }));
        const key = 'locket_admin_session';
        const $ = id => document.getElementById(id);
        const accountDialog = $('accountDialog');
        function openAccountDialog(editing = false) {
          if (!editing) $('accountForm').reset();
          $('editorTitle').textContent = editing ? 'Edit / renew account' : 'Add account';
          $('accountMessage').textContent = '';
          accountDialog.showModal();
          $('accountId').focus();
        }
        $('addAccount').onclick = () => openAccountDialog();
        $('closeAccount').onclick = $('cancelAccount').onclick = () => {
          if (!$('save').disabled) accountDialog.close();
        };
        accountDialog.addEventListener('cancel', event => {
          if ($('save').disabled) event.preventDefault();
        });
        let session = null, skip = 0, timer;
        const limit = 50;
        const siteKey = $('turnstile').dataset.sitekey;
        let turnstileToken = '', widgetId;
        function renderTurnstile() {
          if (!siteKey || !window.turnstile) return;
          if (widgetId !== undefined) { try { window.turnstile.remove(widgetId); } catch { } widgetId = undefined; }
          turnstileToken = '';
          $('turnstile').classList.remove('is-failed');
          widgetId = window.turnstile.render('#turnstile', {
            sitekey: siteKey, action: 'admin-login', language: 'en', size: 'flexible',
            theme: currentTheme === 'system' ? 'auto' : currentTheme,
            retry: 'auto', 'refresh-expired': 'auto',
            callback: token => { turnstileToken = token; $('loginMessage').textContent = ''; },
            'expired-callback': () => { turnstileToken = ''; },
            'timeout-callback': () => { turnstileToken = ''; },
            'error-callback': () => {
              turnstileToken = '';
              $('loginMessage').textContent = 'Unable to load Cloudflare verification. Please try again.';
            }
          });
        }
        if (siteKey) {
          window.onTurnstileReady = renderTurnstile;
          const script = document.createElement('script');
          script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?onload=onTurnstileReady&render=explicit';
          script.nonce = document.currentScript.nonce;
          script.async = true;
          script.onerror = () => {
            $('turnstile').classList.add('is-failed');
            $('loginMessage').textContent = 'Unable to load Cloudflare verification. Please reload the page.';
          };
          document.head.append(script);
          // Keep the widget theme in sync with the manual theme toggle (only before it is solved).
          themeButtons.forEach(button => button.addEventListener('click', () => {
            if (widgetId !== undefined && !turnstileToken) renderTurnstile();
          }));
        }
        function clearSession() {
          accountDialog.close();
          clearTimeout(timer); session = null;
          try { localStorage.removeItem(key); } catch { }
          $('dashboard').hidden = true; $('loginScreen').hidden = false;
          $('accounts').replaceChildren(); $('identity').textContent = '';
          $('accountForm').reset(); $('adminMessage').textContent = '';
        }
        async function api(path, options = {}, auth = true) {
          const headers = { 'Content-Type': 'application/json' };
          if (auth && session) headers.Authorization = 'Bearer ' + session.access_token;
          const response = await fetch(path, { ...options, headers, cache: 'no-store', credentials: 'omit' });
          if (!response.ok) {
            let data; try { data = await response.json(); } catch { }
            if (response.status === 401 && auth) clearSession();
            const messages = {
              'Email hoặc mật khẩu không đúng': 'Incorrect email or password.',
              'Cloudflare Turnstile chưa được cấu hình đầy đủ.': 'Cloudflare Turnstile is not fully configured.',
              'Vui lòng hoàn tất xác minh Cloudflare.': 'Please complete Cloudflare verification.',
              'Không thể xác minh Cloudflare. Vui lòng thử lại.': 'Unable to verify with Cloudflare. Please try again.',
              'Xác minh Cloudflare không hợp lệ hoặc đã hết hạn.': 'Cloudflare verification is invalid or expired.',
            };
            const detail = typeof data?.detail === 'string' ? (messages[data.detail] || data.detail) : null;
            throw Error(detail || 'Request failed (' + response.status + '). Please check your input.');
          }
          return response.status === 204 ? null : response.json();
        }
        async function load() {
          const rows = await api('/admin/accounts?skip=' + skip + '&limit=' + limit);
          if (!session) return;
          const body = $('accounts'); body.replaceChildren();
          for (const [rowIndex, row] of rows.entries()) {
            const tr = document.createElement('tr');
            const number = document.createElement('td');
            number.className = 'row-number'; number.textContent = String(skip + rowIndex + 1); tr.append(number);
            for (const [index, value] of [row.locket_id, new Date(row.expires_date).toLocaleString('en-US'), new Date(row.expires_date) > new Date() ? 'Gold' : 'Expired'].entries()) {
              const td = document.createElement('td');
              const label = document.createElement('span'); label.textContent = value;
              if (index === 0) {
                const name = document.createElement('span'); name.className = 'account-name';
                const crown = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
                crown.setAttribute('viewBox', '0 0 32 32'); crown.setAttribute('class', 'account-crown'); crown.setAttribute('aria-hidden', 'true');
                const symbol = document.createElementNS('http://www.w3.org/2000/svg', 'use');
                symbol.setAttribute('href', '#gold-crown'); crown.append(symbol);
                name.append(crown, label); td.append(name);
              } else {
                label.className = index === 1 ? 'account-expiry' : 'account-status' + (value === 'Gold' ? ' is-gold' : '');
                td.append(label);
              }
              tr.append(td);
            }
            const actions = document.createElement('td');
            const edit = document.createElement('button'); edit.type = 'button'; edit.className = 'secondary'; edit.textContent = 'Edit';
            edit.onclick = () => {
              $('accountId').value = row.locket_id;
              const date = new Date(row.expires_date);
              $('expiry').value = new Date(date - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
              openAccountDialog(true);
            };
            const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'secondary'; remove.textContent = 'Delete';
            remove.onclick = async () => {
              if (!confirm('Delete account ' + row.locket_id + '?')) return;
              remove.disabled = true;
              try { await api('/admin/accounts/' + encodeURIComponent(row.locket_id), { method: 'DELETE' }); await load(); }
              catch (error) { $('adminMessage').textContent = error.message; }
              finally { remove.disabled = false; }
            };
            const check = document.createElement('button'); check.type = 'button'; check.className = 'secondary'; check.textContent = 'Check API';
            check.onclick = async () => {
              check.disabled = true;
              try {
                const result = await api('/v1/subscribers/' + encodeURIComponent(row.locket_id));
                $('adminMessage').textContent = 'API result for ' + row.locket_id + ': ' + (result.subscriber.entitlements.Gold ? 'access is active.' : 'no access or expired.');
              } catch (error) { $('adminMessage').textContent = error.message; }
              finally { check.disabled = false; }
            };
            for (const [button, pathData] of [
              [edit, 'm15 4 5 5M4 20l5-1L21 7l-5-5L4 14Z'],
              [check, 'm9 8-4 4 4 4m6-8 4 4-4 4'],
              [remove, 'M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7'],
            ]) {
              button.title = button.textContent;
              button.setAttribute('aria-label', button.textContent + ' · ' + row.locket_id);
              const icon = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
              icon.setAttribute('viewBox', '0 0 24 24'); icon.setAttribute('class', 'ui-icon'); icon.setAttribute('aria-hidden', 'true');
              const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
              path.setAttribute('d', pathData); icon.append(path); button.replaceChildren(icon);
            }
            actions.append(edit, check, remove); tr.append(actions); body.append(tr);
          }
          if (!rows.length) { const tr = document.createElement('tr'); const td = document.createElement('td'); td.colSpan = 5; td.textContent = 'No accounts yet.'; tr.append(td); body.append(tr); }
          $('previous').disabled = skip === 0; $('next').disabled = rows.length < limit || skip + limit > 10000;
          $('page').textContent = 'Page ' + (skip / limit + 1);
        }
        async function enter() {
          if (!session || !Number.isFinite(Date.parse(session.expires_at)) || Date.parse(session.expires_at) <= Date.now()) { clearSession(); return; }
          const admin = await api('/api/admin/me');
          $('identity').textContent = admin.email;
          await load();
          if (!session) return;
          $('loginScreen').hidden = true; $('dashboard').hidden = false;
          clearTimeout(timer);
          timer = setTimeout(() => { clearSession(); $('loginMessage').textContent = 'Your session has expired. Please sign in again.'; }, Math.max(0, Date.parse(session.expires_at) - Date.now()));
        }
        $('loginForm').onsubmit = async event => {
          event.preventDefault();
          if (siteKey && !turnstileToken) {
            $('loginMessage').textContent = 'Please complete Cloudflare verification.';
            return;
          }
          $('signIn').disabled = true; $('loginMessage').textContent = '';
          let password = $('password').value; $('password').value = '';
          try {
            session = await api('/api/admin/login', { method: 'POST', body: JSON.stringify({ email: $('email').value.trim(), password, turnstile_token: turnstileToken }) }, false);
            try { localStorage.setItem(key, JSON.stringify(session)); } catch { $('loginMessage').textContent = 'Your browser blocked session storage. This session is available in this tab only.'; }
            skip = 0; await enter();
          } catch (error) { clearSession(); $('loginMessage').textContent = error.message; }
          finally {
            password = ''; $('signIn').disabled = false; turnstileToken = '';
            if (widgetId !== undefined) window.turnstile.reset(widgetId);
          }
        };
        $('accountForm').onsubmit = async event => {
          event.preventDefault(); $('save').disabled = true;
          $('accountMessage').textContent = '';
          try {
            await api('/admin/add-account', { method: 'POST', body: JSON.stringify({ locket_id: $('accountId').value, expires_date: new Date($('expiry').value).toISOString() }) });
            accountDialog.close();
            $('adminMessage').textContent = 'Account saved.'; await load();
          } catch (error) {
            $(accountDialog.open ? 'accountMessage' : 'adminMessage').textContent = error.message;
          }
          finally { $('save').disabled = false; }
        };
        $('previous').onclick = async () => { skip = Math.max(0, skip - limit); try { await load(); } catch (error) { $('adminMessage').textContent = error.message; } };
        $('next').onclick = async () => { skip += limit; try { await load(); } catch (error) { $('adminMessage').textContent = error.message; } };
        $('logout').onclick = async () => {
          $('logout').disabled = true;
          try { await api('/api/admin/logout', { method: 'POST' }); clearSession(); $('loginMessage').textContent = 'You have signed out.'; }
          catch (error) { if (session) $('adminMessage').textContent = 'Unable to revoke the session: ' + error.message + '. Please try again.'; }
          finally { $('logout').disabled = false; }
        };
        window.addEventListener('storage', event => { if (event.key === key && event.newValue === null) clearSession(); });
        try { session = JSON.parse(localStorage.getItem(key)); } catch { clearSession(); }
        enter().catch(error => { clearSession(); $('loginMessage').textContent = error.message; });
      })();
    </script>
    <!-- ADMIN_END -->
  </main>
</body>

</html>
```
