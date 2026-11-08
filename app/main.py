import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import các router đã có sẵn trong hệ thống chuẩn
from app.auth import router as auth_router
from app.routers.management import router as management_router
from app.routers.subscribers import router as subscribers_router

# Import proxy router đã được làm sạch
from app.locket_modifier import router as locket_proxy_router
from app.database import lifespan

# Khởi tạo FastAPI với lifespan chuẩn của dự án (kết nối MongoDB)
app = FastAPI(
    title="Locket Gold Manager",
    description="Hệ thống quản lý và proxy phân quyền Locket Gold",
    version="2.0.0",
    lifespan=lifespan
)

# Cấu hình CORS
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

# TRỌNG TÂM: Route Catch-all (Proxy /{path:path}) BẮT BUỘC PHẢI NẠP CUỐI CÙNG
app.include_router(locket_proxy_router)