from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.user import router as user_router

app = FastAPI()

# Origins ที่อนุญาต (เพิ่ม http://localhost:3000 สำหรับ Next.js)
origins = [
    "http://localhost:3000",  # Frontend ของคุณ
    "http://127.0.0.1:3000",  # กรณีใช้ localhost แบบ IP
]

# เพิ่ม CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # ระบุ origins ที่อนุญาต
    allow_credentials=True,  # อนุญาตส่ง credentials (cookies, headers)
    allow_methods=["*"],  # อนุญาตทุก HTTP method
    allow_headers=["*"],  # อนุญาตทุก header
)

# Include User Router
app.include_router(user_router, prefix="/users", tags=["Users"])
