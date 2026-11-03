import secrets

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

from .database import lifespan
from .middleware import SecurityMiddleware, security_headers
from .routes import router, admin_router
from .auth import router as auth_router

def create_app() -> FastAPI:
    # Khởi tạo ứng dụng kết nối trực tiếp với MongoDB
    app = FastAPI(lifespan=lifespan)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        # Validation errors may contain passwords in both input and error context.
        return JSONResponse({'detail': 'Invalid request data'}, status_code=422)

    @app.exception_handler(PyMongoError)
    async def database_unavailable(request: Request, exc: PyMongoError):
        return JSONResponse({'detail': 'Database temporarily unavailable'}, status_code=503)

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        # This handler runs outside SecurityMiddleware, so apply its headers here.
        headers = security_headers(
            getattr(request.state, 'csp_nonce', secrets.token_urlsafe(24)),
            request.url.scheme == 'https',
        )
        return JSONResponse({'detail': 'Internal server error'}, status_code=500, headers=headers)

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
