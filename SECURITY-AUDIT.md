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
