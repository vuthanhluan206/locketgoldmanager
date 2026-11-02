# Deploy FastAPI lên Vercel

Repository này có entrypoint `index.py` theo cơ chế FastAPI native của Vercel và chọn Python 3.12 qua `.python-version`. `vercel.json` chỉ định FastAPI và đặt lại Build Command/Output Directory về mặc định, tránh phục vụ riêng HTML tĩnh. Giữ nguyên backend; Vercel hỗ trợ lifespan. Không chạy Dockerfile, `uvicorn --reload` hoặc `docker compose` trong Vercel Build Command.

`pyproject.toml` khai báo tường minh `[tool.vercel] entrypoint = "app.main:app"`, tránh phụ thuộc vào việc tự dò file import lại app hoặc app được khởi tạo qua factory. Vercel cài runtime dependencies từ `[project].dependencies` trong file này; danh sách đồng bộ với `requirements.txt` cho local và Docker, có test kiểm tra không bị lệch.

## 1. Chuẩn bị database và tài khoản

- Tạo MongoDB Atlas hoặc dùng MongoDB có thể kết nối từ Vercel qua TLS. URI `localhost` của máy bạn không hoạt động trên Vercel.
- Tạo database user quyền `readWrite` chỉ trên database của ứng dụng. Cấu hình Atlas Network Access theo mạng/IP egress của môi trường deploy; không mặc định mở database cho mọi IP. Nếu cần egress cố định/private network, kiểm tra tính năng và gói nền tảng hỗ trợ trước.
- Trước khi public, đổi mật khẩu đã gửi trong hội thoại bằng lệnh local `python -m app.bootstrap`. Mật khẩu được nhập ẩn; chỉ hash có salt được lưu trong `.env`. Lấy giá trị hash từ `.env` để nhập vào Vercel; không đưa file này lên Git.
- Production và Preview nên dùng database/tài khoản admin riêng. Nếu dùng chung DB, startup của preview với cấu hình hash khác có thể thay đổi tài khoản admin production.

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

Với preview, thêm đúng hostname preview vào `ALLOWED_HOSTS` cho môi trường đó hoặc chỉ triển khai production ban đầu. Không dùng wildcard để bỏ kiểm tra Host. Một deployment URL ngẫu nhiên không nằm trong allowlist sẽ trả 400, dù production domain vẫn hoạt động.

Để `ROOT_CA_PATH` trống cho lần triển khai đầu. `.vercelignore` cố ý loại chứng chỉ và khóa; không trỏ đường dẫn `E:\...` trên cloud. Nếu cần CA sau này, phải cấp chứng chỉ công khai cho runtime theo cơ chế riêng, không đưa private key vào bundle.

Đánh dấu biến bí mật là sensitive nếu Vercel hỗ trợ trong môi trường tương ứng. Mỗi lần đổi biến môi trường phải redeploy. Không đặt cấu hình bí mật trong frontend hoặc `vercel.json`.

## 4. Bảo vệ và kiểm tra

- Nếu trang chủ hiện cả login và API trả Vercel `NOT_FOUND`: kiểm tra Settings → Build and Deployment, Root Directory phải là gốc repo (`./` hoặc để trống), không phải `web`. Framework là FastAPI; tắt override Output Directory và Build Command, không xuất riêng `web`. Sau đó tạo deployment từ commit mới nhất trên `main`. HTML thô có `__NONCE__` nghĩa là request chưa qua FastAPI.
- Nếu build báo `FASTAPI_ENTRYPOINT_NOT_FOUND`, xác nhận deployment dùng commit có `pyproject.toml` và Root Directory là gốc repository. Không redeploy mã cũ chỉ có cấu hình tự dò.
- Nếu runtime báo `ModuleNotFoundError: No module named 'fastapi'` sau dòng build `Installing required dependencies from pyproject.toml`, phải deploy commit có `[project].dependencies` đầy đủ. File chỉ khai báo `[tool.vercel]` không đủ để cài dependencies khi Vercel chọn pyproject thay requirements.

- Thiết lập rate limit chung tại Vercel Firewall/WAF hoặc dịch vụ edge cho `POST /api/admin/login` theo khả năng gói của bạn. Limiter hiện có nằm trong từng instance và không chống được brute-force phân tán trên nhiều instance.
- Xác minh HTTPS scheme/IP proxy thực tế; không tùy tiện tin `X-Forwarded-For` từ client. Nếu gặp 400, kiểm tra detail trong JSON và log: phân biệt lỗi Host với `HTTPS is required`; không tắt các kiểm tra một cách mặc định.
- Sau deploy, kiểm tra `/`, `/admin`, đăng nhập, thêm/gia hạn một ID thử, tải profile, đăng xuất và thử gọi lại với token cũ.
- Kiểm tra MongoDB có `admins`, `sessions`, `accounts` và index TTL trên `sessions.expires_at`.
- Không đưa `.env`, `.venv`, token, password hash hoặc log request vào Git. `.vercelignore` và `.gitignore` đã loại các file runtime/bí mật.

Chưa deploy Vercel bằng tài khoản của bạn trong phiên này. Tài liệu chính thức: [FastAPI on Vercel](https://vercel.com/docs/frameworks/backend/fastapi), [Python runtime](https://vercel.com/docs/functions/runtimes/python).
