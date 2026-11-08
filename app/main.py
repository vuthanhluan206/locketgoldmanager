import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Bổ sung SecurityMiddleware bị thiếu
from app.middleware import SecurityMiddleware 

from app.auth import router as auth_router
from app.routers.management import router as management_router
from app.routers.subscribers import router as subscribers_router
from app.locket_modifier import router as locket_proxy_router
from app.database import lifespan

app = FastAPI(
    title="Locket Gold Manager",
    description="Hệ thống quản lý và proxy phân quyền Locket Gold",
    version="2.0.0",
    lifespan=lifespan
)

# 1. BẮT BUỘC PHẢI CÓ SECURITY MIDDLEWARE (Cung cấp csp_nonce cho HTML và chặn IP)
app.add_middleware(SecurityMiddleware)

# 2. Cấu hình CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Nạp các API Quản trị và Authentication TRƯỚC
app.include_router(auth_router)
app.include_router(management_router)
app.include_router(subscribers_router)

# Route Catch-all (Proxy) BẮT BUỘC PHẢI NẠP CUỐI CÙNG
app.include_router(locket_proxy_router)