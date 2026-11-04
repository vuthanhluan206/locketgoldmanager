from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.middleware import SecurityMiddleware
from app.routers import management
from app.locket_modifier import app as proxy_app

settings = get_settings()

app = FastAPI(
    title="Locket Management & Proxy System",
    version="1.0.0",
    docs_url=None,
    redoc_url=None
)

# Cấu hình CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Đăng ký Security Middleware (Lưu ý: Có thể middleware này đang chặn các request admin nếu không phân quyền đúng)
app.add_middleware(SecurityMiddleware)

# 1. Đăng ký các router quản lý hệ thống tài khoản (Trang Admin của bạn)
app.include_router(management.router)

# 2. Mount ứng dụng proxy modifier
# Nếu app Locket gọi trực tiếp vào domain gốc mà không có /proxy, 
# bạn nên mount trực tiếp hoặc tách route. Tuy nhiên nếu dùng app.mount thì đường dẫn bắt buộc có /proxy.
# Nếu bạn muốn bắt toàn bộ request gốc cho proxy, ta dùng Mount ở gốc hoặc cấu hình sub-app:
app.mount("/proxy", proxy_app)

@app.get("/")
async def root():
    return {
        "system": "Locket Management & Proxy System",
        "status": "active",
        "version": "1.0.0"
    }
