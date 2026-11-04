from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

from app.auth import router as auth_router
from app.database import lifespan
from app.middleware import SecurityMiddleware, security_headers
from app.routers import management, subscribers
from app.locket_modifier import router as proxy_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Locket Management & Proxy System",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.add_middleware(SecurityMiddleware)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse({'detail': 'Invalid request'}, status_code=422)

    @app.exception_handler(PyMongoError)
    async def database_error(request: Request, exc: PyMongoError):
        return JSONResponse({'detail': 'Database unavailable'}, status_code=503)

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, exc: Exception):
        return JSONResponse(
            {'detail': 'Internal server error'}, status_code=500,
            headers=security_headers(request.state.csp_nonce, request.url.scheme == 'https'),
        )

    # Đăng ký đầy đủ router quản lý (trang chủ, admin, profile), auth, subscriber và proxy
    app.include_router(management.router)
    app.include_router(auth_router)
    app.include_router(management.admin_router)
    app.include_router(subscribers.router)
    app.include_router(proxy_router)
    return app


app = create_app()
