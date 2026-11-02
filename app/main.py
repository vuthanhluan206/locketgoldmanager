from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError
from .database import lifespan
from .routes import admin_router, router

app = FastAPI(title='License Manager', lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware('http')
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.update({'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
                             'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY',
                             'Content-Security-Policy': "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"})
    return response


@app.exception_handler(PyMongoError)
async def database_error(request: Request, exc: PyMongoError):
    return JSONResponse(status_code=503, content={'detail': 'Database temporarily unavailable'})


app.include_router(router)
app.include_router(admin_router)
