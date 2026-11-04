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
