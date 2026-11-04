from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

from app.auth import router as auth_router
from app.database import lifespan
from app.middleware import SecurityMiddleware
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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SecurityMiddleware)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse({'detail': 'Invalid request'}, status_code=422)

    @app.exception_handler(PyMongoError)
    async def database_error(request: Request, exc: PyMongoError):
        return JSONResponse({'detail': 'Database unavailable'}, status_code=503)

    app.include_router(management.router)
    app.include_router(auth_router)
    app.include_router(management.admin_router)
    app.include_router(subscribers.router)
    app.include_router(proxy_router)
    return app


app = create_app()
