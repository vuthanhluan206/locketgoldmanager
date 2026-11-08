import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.middleware import SecurityMiddleware 

from app.auth import router as auth_router
# ĐÃ SỬA CHỖ NÀY: Import thêm admin_router
from app.routers.management import router as management_router, admin_router
from app.routers.subscribers import router as subscribers_router
from app.locket_modifier import router as locket_proxy_router
from app.database import lifespan

app = FastAPI(
    title="Locket Gold Manager",
    description="Hệ thống quản lý và proxy phân quyền Locket Gold",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(SecurityMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(management_router)
# ĐÃ SỬA CHỖ NÀY: Nạp admin_router để mở khóa các API /admin/...
app.include_router(admin_router)
app.include_router(subscribers_router)

# Proxy luôn phải nằm cuối cùng
app.include_router(locket_proxy_router)