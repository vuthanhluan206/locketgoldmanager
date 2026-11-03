from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import lifespan
from .middleware import SecurityMiddleware
from .routes import router, admin_router
from .auth import router as auth_router

def create_app() -> FastAPI:
    # Khởi tạo ứng dụng kết nối trực tiếp với MongoDB
    app = FastAPI(lifespan=lifespan)

    # Bật hệ thống bảo vệ chống Spam và giới hạn tốc độ request
    app.add_middleware(SecurityMiddleware)

    # Cấu hình CORS mở rộng cho phép mọi nguồn gọi API
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Kết nối các đường dẫn Web, API cấp phát Gold và Trang quản trị Admin
    app.include_router(router)
    app.include_router(admin_router)
    app.include_router(auth_router)
    return app


app = create_app()
