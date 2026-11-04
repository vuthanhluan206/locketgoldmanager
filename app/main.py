from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import lifespan
from .middleware import SecurityMiddleware
from .routers.management import router as management_router, admin_router
from .routers.subscribers import router as subscriber_router
from .auth import router as auth_router

app = FastAPI(lifespan=lifespan)

# Bật bảo vệ middleware
app.add_middleware(SecurityMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Đăng ký các router đã phân tách
app.include_router(management_router)
app.include_router(admin_router)
app.include_router(subscriber_router)
app.include_router(auth_router)