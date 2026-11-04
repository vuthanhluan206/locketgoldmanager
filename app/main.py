from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.middleware import SecurityMiddleware
from app.routers import management
from app.locket_modifier import app as proxy_app

settings = get_settings()

app = FastAPI(
    title="Locket Management & Proxy System",
    version="1.0.0",
    docs_url=None,  # Tắt docs công khai nếu cần bảo mật
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

# Đăng ký Security Middleware tùy chỉnh của hệ thống
app.add_middleware(SecurityMiddleware)

# Đăng ký các router quản lý hệ thống tài khoản hiện tại
app.include_router(management.router)

# Mount ứng dụng proxy locket_modifier vào đường dẫn /proxy
app.mount("/proxy", proxy_app)

@app.get("/")
async def root():
    return {
        "system": "Locket Management & Proxy System",
        "status": "active",
        "version": "1.0.0"
    }