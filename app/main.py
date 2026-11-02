from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError
import logging

from .database import lifespan
from .middleware import SecurityMiddleware, security_headers
from .routes import admin_router, router
from .auth import router as auth_router

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="License Manager", lifespan=lifespan,
        docs_url=None, redoc_url=None, openapi_url=None,
    )
    app.add_middleware(SecurityMiddleware)

    @app.exception_handler(PyMongoError)
    async def database_error(request: Request, exc: PyMongoError):
        logger.error('DATABASE_REQUEST_FAILED: %s', type(exc).__name__)
        return JSONResponse(status_code=503, content={"detail": "Database temporarily unavailable"})

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Do not echo arbitrary input or internal exception context.
        errors = [{"loc": error["loc"], "type": error["type"]} for error in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": errors})

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        logger.error('UNEXPECTED_REQUEST_FAILED: %s', type(exc).__name__)
        return JSONResponse(
            status_code=500, content={"detail": "Internal server error"},
            headers=security_headers(
                getattr(request.state, "csp_nonce", ""), request.url.scheme == "https",
            ),
        )

    app.include_router(router)
    app.include_router(admin_router)
    app.include_router(auth_router)
    return app


app = create_app()
