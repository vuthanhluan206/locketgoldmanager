import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient

# Import router từ file locket_modifier mà chúng ta vừa hoàn thiện
from app.locket_modifier import router as locket_router

# ================= QUẢN LÝ KẾT NỐI MONGODB (DÀNH CHO SERVERLESS) =================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Quản lý vòng đời của ứng dụng.
    Mở kết nối Database khi Vercel boot máy chủ ảo lên, và đóng lại khi xử lý xong.
    """
    # Đảm bảo bạn đã cấu hình biến môi trường MONGODB_URI trên Vercel
    mongodb_uri = os.getenv("MONGODB_URI")
    
    if mongodb_uri:
        # Khởi tạo client kết nối tới MongoDB Atlas
        client = AsyncIOMotorClient(mongodb_uri)
        app.state.db_client = client
        
        # Lấy database (Nếu URI của bạn không có tên DB mặc định, nó sẽ dùng 'locket_db')
        db = client.get_default_database("locket_db")
        
        # Gán collection 'accounts' vào app.state để locket_modifier.py có thể gọi
        app.state.accounts = db["accounts"]
        
        # (Collection 'admins' sẽ được locket_modifier.py tự động gọi qua accounts.database["admins"])
    else:
        print("[CẢNH BÁO] Chưa cấu hình biến môi trường MONGODB_URI")
        app.state.accounts = None

    yield  # Ứng dụng chạy tại đây

    # Đóng kết nối khi máy chủ ảo của Vercel tắt (tránh treo memory)
    if hasattr(app.state, "db_client"):
        app.state.db_client.close()
# ===============================================================================

# Khởi tạo FastAPI
app = FastAPI(
    title="Locket Gold Universal Proxy",
    description="Hệ thống cấp quyền Locket Gold và Xử lý Ảnh AI",
    version="2.0.0",
    lifespan=lifespan
)

# Cấu hình CORS để giao diện Admin (fetch API) không bị chặn
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Bạn có thể thay "*" bằng tên miền thật để bảo mật hơn
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Tích hợp toàn bộ API Quản trị và Proxy từ file locket_modifier.py
app.include_router(locket_router)

# Route phụ để kiểm tra server có đang sống không (Ping test)
@app.get("/")
async def root_health_check():
    return {"status": "Locket Proxy is running mượt mà 🚀"}